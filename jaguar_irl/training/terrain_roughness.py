"""Static SRTM roughness jobs, exact-grid GEE exports and validated local products.

No trajectories or year choices are used. Cloud submission is deliberately separate.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from jaguar_irl.data.pantanal_checkpoint import (
    digest, file_hash, load_selection_checkpoint, read_table,
)
from .shared import group_lookup, selected_groups
from .shared_storage import locked, read, sync_dir, write

RECIPE = dict(
    id='srtm_90m_population_variance_area_mean_v1',
    source='USGS/SRTMGL1_003', band='elevation', source_units='m',
    source_epoch='2000-02-11/2000-02-22; void-filled V3 compilation',
    temporal_filter=None, feature='roughness', output_units='m2',
    working_crs='EPSG:32721', working_transform=[30, 0, 0, 0, -30, 10000000],
    elevation_resampling='bilinear', neighborhood_cells=3,
    neighborhood_full_width_m=90, variance='population; mean(z^2)-mean(z)^2',
    aggregation='overlap-area-weighted mean of fine-grid local variance',
    mask_policy='complete 3x3 neighborhoods and complete target coverage',
    halo_policy='source is not clipped; crop only after neighborhood and aggregation',
    export_bands=['roughness_var_m2', 'valid_fraction'], nodata=-9999,
)


def sync_files(root):
    for path in Path(root).iterdir():
        if path.is_file():
            with path.open('rb') as handle:
                os.fsync(handle.fileno())


def make_plan(checkpoint, collection='SPR-C01'):
    checkpoint = Path(checkpoint).resolve()
    cp = load_selection_checkpoint(checkpoint)
    groups = selected_groups(checkpoint, None, collection)
    lookup = group_lookup(cp)
    members = {r['group_id'] for r in read_table(checkpoint/'collection_members.csv')
               if r['collection_id'] == collection and r['selection_status'] == 'selected'}
    if set(groups) != members:
        raise ValueError('Collection group list differs from canonical selected membership')
    jobs = {}
    for group in groups:
        grid = cp['grids'][lookup[group]['grid_key']]
        if grid['crs'] != RECIPE['working_crs'] or grid['cell_size_m'] != 500:
            raise ValueError('This recipe supports only saved EPSG:32721 / 500 m grids')
        xmin, ymin, xmax, ymax = grid['bounds']
        if (xmax-xmin != grid['cols']*500 or ymax-ymin != grid['rows']*500):
            raise ValueError('Grid shape and bounds disagree')
        product_key = digest(dict(grid=grid, recipe=RECIPE))
        jobs[group] = dict(group_id=group, grid_key=grid['grid_key'], grid=grid,
                           crs_transform=[500, 0, xmin, 0, -500, ymax],
                           product_key=product_key,
                           export_prefix=f'{collection}_{group}_roughness_{product_key[:12]}',
                           output_cells=grid['rows']*grid['cols'])
    pilot = min(jobs, key=lambda g: (jobs[g]['output_cells'], g))
    return dict(schema='pantanal_static_terrain_plan/1', checkpoint=str(checkpoint),
                checkpoint_sha256=file_hash(checkpoint/'checkpoint.json'),
                grids_sha256=file_hash(checkpoint/'grids.json'),
                software_sha256=file_hash(__file__), collection=collection,
                recipe=RECIPE, groups=jobs, default_pilot_group=pilot,
                representative_year=None, trajectory_year_filter=None,
                scope='all canonical collection grids, including test coverage',
                cloud_execution='not submitted; manual Code Editor tasks or separate client',
                total_output_cells=sum(j['output_cells'] for j in jobs.values()))


def build_ee_image(ee, job):
    """Return two-band exact-grid image; caller controls initialization/submission.

    Elevation stays unclipped so interpolation and the 3x3 neighborhood see halos.
    Invalid input is made explicit before coarse reduction; missing pixels cannot
    disappear from the validity denominator.
    """
    recipe = RECIPE
    work = ee.Projection(recipe['working_crs'], recipe['working_transform'])
    src = ee.Image(recipe['source']).select(recipe['band'])
    z = src.resample('bilinear').reproject(work).toDouble().subtract(100)
    valid = (src.mask().unmask(0, False).resample('bilinear').reproject(work)
             .gte(1-1e-9))
    kernel = ee.Kernel.square(radius=1, units='pixels', normalize=False)
    full = valid.reduceNeighborhood(ee.Reducer.min(), kernel, skipMasked=False)
    mean = z.reduceNeighborhood(ee.Reducer.mean(), kernel)
    second = z.pow(2).reduceNeighborhood(ee.Reducer.mean(), kernel)
    variance = second.subtract(mean.pow(2)).max(0).updateMask(full)
    target = ee.Projection(job['grid']['crs'], job['crs_transform'])
    coverage = (full.unmask(0, False).toDouble()
                .reduceResolution(ee.Reducer.mean(), bestEffort=False, maxPixels=1024)
                .reproject(target).rename('valid_fraction'))
    roughness = (variance.unmask(0, False)
                 .reduceResolution(ee.Reducer.mean(), bestEffort=False, maxPixels=1024)
                 .reproject(target).updateMask(coverage.gte(1-1e-9))
                 .rename('roughness_var_m2').unmask(recipe['nodata'], False))
    return roughness.addBands(coverage).toFloat()


JS = r'''// Generated exact-grid SRTM roughness. No telemetry uploads or date filtering.
// Select your EE Cloud project in Code Editor. Task creation is not task execution.
// Launch the single pilot, download and validate it before creating further tasks.
// Drive folder must be a UNIQUE existing folder name; duplicate names are ambiguous.
var DRIVE_FOLDER = 'SET_UNIQUE_EXISTING_DRIVE_FOLDER';
var GROUP_IDS = [PLAN.default_pilot_group];
var MAX_TASKS = 1; // Deliberate bounded batch. Increase only after pilot review.
var JOBS = PLAN.groups;
if (DRIVE_FOLDER.indexOf('SET_') === 0) throw new Error('Set DRIVE_FOLDER first');
if (!GROUP_IDS.length || GROUP_IDS.length > MAX_TASKS || MAX_TASKS > 13)
  throw new Error('Batch exceeds configured task count');
var seen = {};
GROUP_IDS.forEach(function(id) {
  if (!JOBS[id] || seen[id]) throw new Error('Unknown or duplicate group: ' + id);
  seen[id] = true;
});
var work = ee.Projection(PLAN.recipe.working_crs, PLAN.recipe.working_transform);
var src = ee.Image(PLAN.recipe.source).select(PLAN.recipe.band);
var z = src.resample('bilinear').reproject(work).toDouble().subtract(100);
// Separate validity surface prevents averaging only the surviving pixels.
var valid = src.mask().unmask(0, false).resample('bilinear').reproject(work).gte(1-1e-9);
var kernel = ee.Kernel.square({radius: 1, units: 'pixels', normalize: false});
var full = valid.reduceNeighborhood({reducer: ee.Reducer.min(), kernel: kernel,
                                    skipMasked: false});
var mean = z.reduceNeighborhood({reducer: ee.Reducer.mean(), kernel: kernel});
var second = z.pow(2).reduceNeighborhood({reducer: ee.Reducer.mean(), kernel: kernel});
var variance = second.subtract(mean.pow(2)).max(0).updateMask(full);
GROUP_IDS.forEach(function(id) {
  var job = JOBS[id], grid = job.grid;
  var target = ee.Projection(grid.crs, job.crs_transform);
  var region = ee.Geometry.Rectangle(grid.bounds, grid.crs, false);
  var coverage = full.unmask(0, false).toDouble()
    .reduceResolution({reducer: ee.Reducer.mean(), bestEffort: false, maxPixels: 1024})
    .reproject(target).rename('valid_fraction');
  var roughness = variance.unmask(0, false)
    .reduceResolution({reducer: ee.Reducer.mean(), bestEffort: false, maxPixels: 1024})
    .reproject(target).updateMask(coverage.gte(1-1e-9))
    .rename('roughness_var_m2').unmask(PLAN.recipe.nodata, false);
  var output = roughness.addBands(coverage).toFloat();
  Map.addLayer(roughness.updateMask(coverage.gte(1-1e-9)),
    {min: 0, max: 100}, id + ' roughness m2'); // Display limits are not truncation.
  Map.addLayer(coverage, {min: 0, max: 1}, id + ' validity', false);
  Export.image.toDrive({image: output, description: job.export_prefix,
    folder: DRIVE_FOLDER, fileNamePrefix: job.export_prefix,
    region: region, crs: grid.crs, crsTransform: job.crs_transform,
    maxPixels: job.output_cells * 2, fileFormat: 'GeoTIFF',
    formatOptions: {cloudOptimized: true, noData: PLAN.recipe.nodata}});
  print('Record task ID/status/output link for', id, job.export_prefix);
});
Map.centerObject(ee.Geometry.Rectangle(JOBS[GROUP_IDS[0]].grid.bounds,
                                     JOBS[GROUP_IDS[0]].grid.crs, false));
print('Plan identity', PLAN_ID);
print('No exact compute/storage guarantee: verify quota and Drive space before launch.');
'''


def verify_bundle(bundle):
    """Reject incomplete or locally changed job bundles before trusting the plan."""
    bundle=Path(bundle).resolve()
    manifest=read(bundle/'bundle.json')
    for name, expected in manifest['files'].items():
        path=(bundle/name).resolve()
        if path.parent != bundle or not path.is_file() or file_hash(path) != expected:
            raise ValueError('Job bundle file missing or hash differs: '+name)
    plan=read(bundle/'plan.json')
    if digest(plan) != manifest['plan_id']:
        raise ValueError('Job bundle plan identity differs')
    return plan


def prepare(checkpoint, output, collection='SPR-C01'):
    plan = make_plan(checkpoint, collection)
    script = ('var PLAN = '+json.dumps(plan, sort_keys=True)+';\nvar PLAN_ID = '+
              json.dumps(digest(plan))+';\n'+JS)
    output = Path(output).resolve()
    with locked(output.parent):
        if output.exists():
            verify_bundle(output)
            if read(output/'plan.json') != plan or (output/'extract_roughness.js').read_text() != script:
                raise ValueError('Existing bundle differs; use a new versioned output path')
            return output
        temp = Path(tempfile.mkdtemp(prefix='.pending-terrain-', dir=output.parent))
        try:
            write(temp/'plan.json', plan)
            (temp/'extract_roughness.js').write_text(script)
            (temp/'task_log_template.csv').write_text(
                'group_id,product_key,export_prefix,task_id,status,output_url,notes\n'+
                ''.join(f"{g},{j['product_key']},{j['export_prefix']},,not_submitted,,\n"
                        for g,j in plan['groups'].items()))
            write(temp/'bundle.json',dict(schema='terrain_export_bundle/1', plan_id=digest(plan),
                                         files={p.name:file_hash(p) for p in temp.iterdir()}))
            sync_files(temp)
            sync_dir(temp)
            os.rename(temp,output)
            sync_dir(output.parent)
        finally:
            if temp.exists(): shutil.rmtree(temp)
    return output


def check_pixels(roughness, coverage, masks):
    if (not np.isfinite(roughness).all() or not np.isfinite(coverage).all()
            or not masks.all()):
        raise ValueError('Raster contains missing/nonfinite pixels')
    if np.any(coverage < 1-1e-6) or np.any(coverage > 1+1e-6):
        raise ValueError('Incomplete or invalid neighborhood coverage')
    if np.any(roughness < 0):
        raise ValueError('Variance must be nonnegative')


def convert(bundle, group, tif, output):
    """Validate one complete two-band export, retaining TIFF and immutable provenance."""
    try:
        import rasterio
        from affine import Affine
    except ImportError as exc:
        raise RuntimeError('Conversion requires rasterio (install in an isolated environment)') from exc
    bundle, tif, output = map(lambda p:Path(p).resolve(), (bundle,tif,output))
    plan=verify_bundle(bundle)
    job=plan['groups'][group]
    if tif.name != job['export_prefix']+'.tif':
        raise ValueError('TIFF filename must match the planned product; do not mix recipes')
    with rasterio.open(tif) as ds:
        grid=job['grid']
        expected=Affine(*job['crs_transform'])
        if ds.crs != rasterio.crs.CRS.from_user_input(grid['crs']):
            raise ValueError('CRS differs from saved grid')
        if ds.shape != (grid['rows'],grid['cols']) or ds.count != 2:
            raise ValueError('Require exact shape and two planned export bands')
        if not np.allclose(tuple(ds.transform),tuple(expected),rtol=0,atol=1e-7):
            raise ValueError('Raster transform differs from saved grid')
        if not np.allclose(tuple(ds.bounds),grid['bounds'],rtol=0,atol=1e-7):
            raise ValueError('Raster bounds differ from saved grid')
        roughness, coverage=ds.read()
        check_pixels(roughness,coverage,ds.read_masks()>0)
    state=dict(schema='validated_terrain_product/1', group_id=group, grid_key=job['grid_key'],
               product_key=job['product_key'],plan_sha256=file_hash(bundle/'plan.json'),
               script_sha256=file_hash(bundle/'extract_roughness.js'), source_tif_sha256=file_hash(tif),
               grid=job['grid'],recipe=plan['recipe'],units='m2',
               minimum=float(roughness.min()),maximum=float(roughness.max()),
               mean=float(roughness.mean()),quality='software spatial/coverage checks passed; scientific review pending')
    with locked(output.parent):
        if output.exists():
            old=read(output/'validation.json')
            if old != state or file_hash(output/'source.tif') != state['source_tif_sha256']:
                raise ValueError('Existing product differs; use new immutable output path')
            if not np.array_equal(np.load(output/'roughness.npy',allow_pickle=False),roughness):
                raise ValueError('Existing NPY differs from validated TIFF')
            return output
        temp=Path(tempfile.mkdtemp(prefix='.pending-terrain-product-',dir=output.parent))
        try:
            shutil.copyfile(tif,temp/'source.tif')
            with (temp/'roughness.npy').open('wb') as handle:
                np.save(handle,roughness.astype(np.float32),allow_pickle=False)
                handle.flush(); os.fsync(handle.fileno())
            write(temp/'validation.json',state)
            write(temp/'checksums.json',{p.name:file_hash(p) for p in temp.iterdir()})
            sync_files(temp)
            sync_files(temp)
            sync_dir(temp)
            os.rename(temp,output); sync_dir(output.parent)
        finally:
            if temp.exists(): shutil.rmtree(temp)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare')
    p.add_argument('--checkpoint',required=True)
    p.add_argument('--collection',default='SPR-C01')
    p.add_argument('--output',required=True)
    p=sub.add_parser('convert')
    p.add_argument('--bundle',required=True); p.add_argument('--group',required=True)
    p.add_argument('--tif',required=True); p.add_argument('--output',required=True)
    a=vars(parser.parse_args()); command=a.pop('command')
    print(prepare(**a) if command=='prepare' else convert(**a))


if __name__=='__main__':
    main()
