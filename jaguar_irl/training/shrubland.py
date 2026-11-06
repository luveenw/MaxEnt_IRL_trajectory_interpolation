"""ESA CCI classified shrubland area fractions, cached by Spring grid and year."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import numpy as np
from jaguar_irl.data.pantanal_checkpoint import digest,file_hash,load_selection_checkpoint,read_table
from .shared import group_lookup,selected_groups
from .shared_storage import locked,read,write,sync_dir
from .terrain_roughness import sync_files,verify_bundle

SOURCE='users/geflanddegradation/toolbox_datasets/lcov_esacc_1992_2022'
ALLOWED=[10,11,12,20,30,40,50,60,61,62,70,71,72,80,81,82,90,100,110,120,121,122,130,140,150,151,152,153,160,170,180,190,200,201,202,210,220]
RECIPE=dict(id='esa_cci_shrubland_area_fraction_v1',source=SOURCE,
            classes={'120':'Shrubland','121':'Evergreen shrubland','122':'Deciduous shrubland'},
            allowed_classes=ALLOWED,units='fraction (0-1) of area classified as shrubland, not canopy cover',
            aggregation='native class indicator followed by overlap-area-weighted mean',
            extra_smoothing=None,mask_policy='complete target coverage; reject unknown/NoData source classes',
            target_crs='EPSG:32721',cell_size_m=500,export_bands=['shrubland_fraction','valid_fraction'],nodata=-9999)


def make_plan(checkpoint,collection='SPR-C01',source_snapshot=None):
    checkpoint=Path(checkpoint).resolve();cp=load_selection_checkpoint(checkpoint)
    groups=selected_groups(checkpoint,None,collection);lookup=group_lookup(cp)
    members=[r for r in read_table(checkpoint/'collection_members.csv') if r['collection_id']==collection and r['selection_status']=='selected']
    if set(groups)!={r['group_id'] for r in members}: raise ValueError('Canonical membership mismatch')
    jobs={}
    for group in groups:
        grid=cp['grids'][lookup[group]['grid_key']]
        if grid['crs']!='EPSG:32721' or grid['cell_size_m']!=500: raise ValueError('Unsupported grid')
        years=sorted({int(r['window_start'][:4]) for r in members if r['group_id']==group})
        for year in years:
            if not 1992<=year<=2022: raise ValueError('Year unavailable in pinned mirror')
            key=f'{group}_{year}';product=digest(dict(grid=grid,recipe=RECIPE,year=year,source_fingerprint=(source_snapshot or {}).get('asset_fingerprint')))
            jobs[key]=dict(job_id=key,group_id=group,year=year,source_band=f'y{year}',grid=grid,
                           grid_key=grid['grid_key'],crs_transform=[500,0,grid['bounds'][0],0,-500,grid['bounds'][3]],
                           product_key=product,export_prefix=f'{collection}_{key}_shrubland_{product[:12]}',
                           output_cells=grid['rows']*grid['cols'])
    pilot=min(jobs,key=lambda k:(jobs[k]['output_cells'],k))
    return dict(schema='pantanal_shrubland_cache_plan/1',checkpoint=str(checkpoint),
                checkpoint_sha256=file_hash(checkpoint/'checkpoint.json'),grids_sha256=file_hash(checkpoint/'grids.json'),
                software_sha256=file_hash(__file__),collection=collection,recipe=RECIPE,source_snapshot=source_snapshot,groups=jobs,
                default_pilot_job=pilot,group_count=len(groups),job_count=len(jobs),
                total_output_cells=sum(j['output_cells'] for j in jobs.values()),
                year_policy='cache observed selected-member Spring years; choose training-only representative years later',
                representative_years=None,trajectory_year_filter=None,
                scientific_validation='not established; independent data-source classes can overlap other predictors')


def build_ee_image(ee,job):
    src=ee.Image(SOURCE).select(job['source_band'])
    known=src.remap(ALLOWED,[1]*len(ALLOWED),0)
    valid=src.mask().gt(0).And(known.eq(1)).unmask(0,False).toDouble()
    indicator=src.remap([120,121,122],[1,1,1],0).unmask(0,False).toDouble().multiply(valid)
    target=ee.Projection(job['grid']['crs'],job['crs_transform'])
    def aggregate(im):
        return im.reduceResolution(ee.Reducer.mean(),bestEffort=False,maxPixels=1024).reproject(target)
    coverage=aggregate(valid).rename('valid_fraction')
    fraction=aggregate(indicator).updateMask(coverage.gte(1-1e-9)).rename('shrubland_fraction').unmask(-9999,False)
    return fraction.addBands(coverage).toFloat()


JS=r'''// ESA CCI classified-area fractions. Codes120/121/122 = Shrubland/Evergreen/Deciduous shrubland.
// Candidate-year cache, NOT production representative-year assignments. No extra smoothing.
var DRIVE_FOLDER='pantanal_spring_esa_shrubland_v1';
var JOB_IDS=[PLAN.default_pilot_job];
var MAX_TASKS=1;
if(!JOB_IDS.length || JOB_IDS.length>MAX_TASKS) throw new Error('Task bound exceeded');
var seen={};
JOB_IDS.forEach(function(id){
 if(!PLAN.groups[id]||seen[id]) throw new Error('Unknown or duplicate job'); seen[id]=true;
 var j=PLAN.groups[id], src=ee.Image(PLAN.recipe.source).select(j.source_band);
 var known=src.remap(PLAN.recipe.allowed_classes,PLAN.recipe.allowed_classes.map(function(){return 1;}),0);
 var valid=src.mask().gt(0).and(known.eq(1)).unmask(0,false).toDouble();
 var indicator=src.remap([120,121,122],[1,1,1],0).unmask(0,false).toDouble().multiply(valid);
 var target=ee.Projection(j.grid.crs,j.crs_transform);
 function aggregate(x){return x.reduceResolution({reducer:ee.Reducer.mean(),bestEffort:false,maxPixels:1024}).reproject(target);}
 var coverage=aggregate(valid).rename('valid_fraction');
 var fraction=aggregate(indicator).updateMask(coverage.gte(1-1e-9)).rename('shrubland_fraction').unmask(-9999,false);
 var region=ee.Geometry.Rectangle(j.grid.bounds,j.grid.crs,false);
 Export.image.toDrive({image:fraction.addBands(coverage).toFloat(),description:j.export_prefix,
  folder:DRIVE_FOLDER,fileNamePrefix:j.export_prefix,region:region,crs:j.grid.crs,crsTransform:j.crs_transform,
  maxPixels:j.output_cells*2,fileFormat:'GeoTIFF',formatOptions:{cloudOptimized:true,noData:-9999}});
 Map.addLayer(fraction.updateMask(coverage.gte(1-1e-9)),{min:0,max:1},id+' shrubland classified-area fraction');
});
'''


def prepare(checkpoint,output,collection='SPR-C01',source_snapshot=None):
    snapshot=read(source_snapshot) if source_snapshot is not None else None
    plan=make_plan(checkpoint,collection,snapshot);script='var PLAN = '+json.dumps(plan,sort_keys=True)+';\n'+JS
    output=Path(output).resolve()
    with locked(output.parent):
        if output.exists():
            if verify_bundle(output)!=plan: raise ValueError('Bundle differs; use new version')
            return output
        temp=Path(tempfile.mkdtemp(prefix='.pending-shrub-',dir=output.parent))
        try:
            write(temp/'plan.json',plan);(temp/'extract_shrubland.js').write_text(script)
            write(temp/'bundle.json',dict(schema='shrubland_export_bundle/1',plan_id=digest(plan),files={p.name:file_hash(p) for p in temp.iterdir()}))
            sync_files(temp);sync_dir(temp);os.rename(temp,output);sync_dir(output.parent)
        finally:
            if temp.exists():shutil.rmtree(temp)
    return output


def check_pixels(fraction,coverage,masks):
    if not masks.all() or not np.isfinite(fraction).all() or not np.isfinite(coverage).all():raise ValueError('Missing or nonfinite values')
    if np.any(coverage<1-1e-6) or np.any(coverage>1+1e-6):raise ValueError('Incomplete source coverage')
    if np.any(fraction<0) or np.any(fraction>1):raise ValueError('Fraction outside unit interval')


def convert(bundle,job_id,tif,output):
    import rasterio
    from affine import Affine
    bundle,tif,output=map(lambda p:Path(p).resolve(),(bundle,tif,output));plan=verify_bundle(bundle);job=plan['groups'][job_id]
    if tif.name!=job['export_prefix']+'.tif':raise ValueError('Unexpected product filename')
    with rasterio.open(tif) as ds:
        g=job['grid']
        if ds.crs!=rasterio.crs.CRS.from_user_input(g['crs']):raise ValueError('CRS mismatch')
        if ds.shape!=(g['rows'],g['cols']) or ds.count!=2:raise ValueError('Shape/bands mismatch')
        if not np.allclose(tuple(ds.transform),tuple(Affine(*job['crs_transform'])),atol=1e-7,rtol=0):raise ValueError('Transform mismatch')
        if not np.allclose(tuple(ds.bounds),g['bounds'],atol=1e-7,rtol=0):raise ValueError('Bounds mismatch')
        fraction,coverage=ds.read();check_pixels(fraction,coverage,ds.read_masks()>0)
    state=dict(schema='validated_shrubland_cache_product/1',job_id=job_id,group_id=job['group_id'],year=job['year'],
               grid_key=job['grid_key'],product_key=job['product_key'],grid=g,recipe=RECIPE,source_snapshot=plan.get('source_snapshot'),
               plan_sha256=file_hash(bundle/'plan.json'),script_sha256=file_hash(bundle/'extract_shrubland.js'),source_tif_sha256=file_hash(tif),
               minimum=float(fraction.min()),maximum=float(fraction.max()),mean=float(fraction.mean()),
               epoch_role='candidate cache; not selected representative year',quality='spatial/coverage/numerical checks passed; ecological validation pending')
    with locked(output.parent):
        if output.exists():
            if read(output/'validation.json')!=state or file_hash(output/'source.tif')!=state['source_tif_sha256'] or not np.array_equal(np.load(output/'shrubland_fraction.npy',allow_pickle=False),fraction):raise ValueError('Existing product changed')
            return output
        temp=Path(tempfile.mkdtemp(prefix='.pending-shrub-product-',dir=output.parent))
        try:
            shutil.copyfile(tif,temp/'source.tif')
            with (temp/'shrubland_fraction.npy').open('wb') as f:np.save(f,fraction.astype(np.float32),allow_pickle=False);f.flush();os.fsync(f.fileno())
            write(temp/'validation.json',state);write(temp/'checksums.json',{p.name:file_hash(p) for p in temp.iterdir()})
            sync_files(temp);sync_dir(temp);os.rename(temp,output);sync_dir(output.parent)
        finally:
            if temp.exists():shutil.rmtree(temp)
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('prepare');a.add_argument('--checkpoint',required=True);a.add_argument('--output',required=True);a.add_argument('--collection',default='SPR-C01');a.add_argument('--source-snapshot')
    a=s.add_parser('convert');a.add_argument('--bundle',required=True);a.add_argument('--job-id',required=True);a.add_argument('--tif',required=True);a.add_argument('--output',required=True)
    args=vars(p.parse_args());command=args.pop('command');print(prepare(**args) if command=='prepare' else convert(**args))

if __name__=='__main__':main()
