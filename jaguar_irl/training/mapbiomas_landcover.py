"""Pinned MapBiomas natural grassland and narrow wetland candidate-year caches."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import numpy as np
from jaguar_irl.data.pantanal_checkpoint import digest,file_hash
from .shared_storage import locked,read,write,sync_dir
from .terrain_roughness import sync_files,verify_bundle
from .shrubland import make_plan as spring_plan

SOURCES={
 'brazil':'projects/mapbiomas-public/assets/brazil/lulc/collection11/mapbiomas_brazil_collection11_coverage_v3',
 'paraguay':'projects/mapbiomas-public/assets/paraguay/lulc/collection3/mapbiomas_paraguay_collection3_coverage_v1',
 'bolivia':'projects/mapbiomas-public/assets/bolivia/lulc/collection4/mapbiomas_bolivia_collection4_coverage_v1',
 'chaco':'projects/mapbiomas-public/assets/chaco/lulc/collection5/mapbiomas_chaco_collection5_integration_v2'}
# Scoped to the full native-source class audit over all Spring grids/years. A new
# class cannot fall through to a lower-priority country; it fails source QA.
KNOWN={'brazil':[3,4,7,11,12,15,21,25,29,33,39,41],
       'paraguay':[3,6,11,15,25,33], 'bolivia':[3,11,12,33], 'chaco':[26]}
SOURCE_IDS={'brazil':1,'paraguay':2,'bolivia':3,'chaco':4}
BANDS=['grassland_fraction','flooded_habitat_fraction','valid_fraction',
       'source_brazil_fraction','source_paraguay_fraction','source_bolivia_fraction','chaco_fallback_fraction']
RECIPE=dict(id='mapbiomas_natural_grass_narrow_wetland_area_fraction_v1',sources=SOURCES,
            source_priority=['brazil','paraguay','bolivia','chaco_gap_only'],source_ids=SOURCE_IDS,
            known_classes=KNOWN,invalid_codes=[0,27],
            features={'grassland':{'code':12,'name':'Natural grass-dominated vegetation; Bolivia includes shrub vegetation; managed pasture excluded'},
                      'flooded_habitat':{'code':11,'name':'Flood-influenced herbaceous/shrubby vegetation; flooded forest, flooded savanna and open water excluded'}},
            chaco_rule='Only class26 Water bodies where all national sources unavailable; contributes zero to both target indicators',
            aggregation='Choose highest-priority available source class, derive native categorical indicators, then overlap-area-weighted mean',
            grid_alignment='native Brazil angular grid; nearest categorical alignment, compatible integer-offset country grids',
            smoothing=None,units='classified area fraction (0-1)',export_bands=BANDS,nodata=-9999,
            mask_policy='Complete coverage; unknown selected-source class is invalid and never falls through')


def choose_pixel(values):
    """Scalar reference of class selection used for meaningful priority tests."""
    for country in ('brazil','paraguay','bolivia'):
        value=values.get(country)
        if value is not None and value not in (0,27):
            return country,value,value in KNOWN[country]
    value=values.get('chaco')
    return ('chaco',26,True) if value==26 else (None,value,False)


def make_plan(checkpoint,collection='SPR-C01',source_snapshot=None):
    base=spring_plan(checkpoint,collection)
    jobs={}
    for key,job in base['groups'].items():
        if not 1985<=job['year']<=2023:raise ValueError('Required year outside common national/Chaco coverage')
        job=dict(job)
        job['source_band']=f"classification_{job['year']}"
        product=digest(dict(grid=job['grid'],recipe=RECIPE,year=job['year'],source_fingerprint=(source_snapshot or {}).get('asset_fingerprint')))
        job.update(product_key=product,export_prefix=f"{collection}_{key}_mapbiomas_{product[:12]}")
        jobs[key]=job
    base.update(schema='pantanal_mapbiomas_landcover_cache_plan/1',recipe=RECIPE,groups=jobs,default_pilot_job='G115_2005' if 'G115_2005' in jobs else base['default_pilot_job'],
                source_snapshot=source_snapshot,software_sha256=file_hash(__file__))
    return base


def native_mosaic(ee,year):
    """Return original selected code, source ID and validity on the native lattice."""
    band=f'classification_{year}';base=ee.Image(SOURCES['brazil']).select(band).projection()
    chosen=ee.Image.constant(0).toInt16().reproject(base)
    sid=ee.Image.constant(0).toUint8().reproject(base)
    known_by_source={}
    for country in ('chaco','bolivia','paraguay','brazil'):
        src=ee.Image(SOURCES[country]).select(band).reproject(base)
        present=src.mask().gt(0).And(src.neq(0)).And(src.neq(27)).unmask(0,False)
        if country=='chaco':present=present.And(src.eq(26).unmask(0,False))
        chosen=chosen.where(present,src.unmask(0,False))
        sid=sid.where(present,SOURCE_IDS[country])
        known_by_source[country]=src.remap(KNOWN[country],[1]*len(KNOWN[country]),0).unmask(0,False)
    valid=sid.gt(0)
    for country in SOURCE_IDS:
        valid=valid.And(sid.neq(SOURCE_IDS[country]).Or(known_by_source[country].eq(1)))
    valid=valid.toDouble().setDefaultProjection(base)
    return chosen.rename('selected_class'),sid.rename('source_id'),valid.rename('valid'),base


def build_ee_image(ee,job):
    chosen,sid,valid,base=native_mosaic(ee,job['year'])
    target=ee.Projection(job['grid']['crs'],job['crs_transform'])
    def aggregate(im):
        return im.toDouble().setDefaultProjection(base).reduceResolution(ee.Reducer.mean(),bestEffort=False,maxPixels=1024).reproject(target)
    coverage=aggregate(valid).rename('valid_fraction')
    complete=coverage.gte(1-1e-9)
    grass=aggregate(chosen.eq(12).And(valid)).updateMask(complete).rename(BANDS[0]).unmask(-9999,False)
    wet=aggregate(chosen.eq(11).And(valid)).updateMask(complete).rename(BANDS[1]).unmask(-9999,False)
    result=grass.addBands(wet).addBands(coverage)
    for country,out in zip(('brazil','paraguay','bolivia','chaco'),BANDS[3:]):
        result=result.addBands(aggregate(sid.eq(SOURCE_IDS[country]).And(valid)).rename(out))
    return result.toFloat()


JS=r'''// Natural grass-dominated vegetation12; Flooded herbaceous/shrubby vegetation11.
// Managed pasture15, flooded forest6, flooded savanna7 and open water excluded from targets.
// Highest-priority valid source selected FIRST. Unknown selected classes fail QA.
var DRIVE_FOLDER='pantanal_spring_mapbiomas_landcover_v1';
var JOB_IDS=[PLAN.default_pilot_job], MAX_TASKS=1;
if(!JOB_IDS.length||JOB_IDS.length>MAX_TASKS) throw new Error('Task bound exceeded');
var seen={};
JOB_IDS.forEach(function(id){
 if(!PLAN.groups[id]||seen[id]) throw new Error('Unknown/duplicate job'); seen[id]=true;
 var j=PLAN.groups[id],r=PLAN.recipe,base=ee.Image(r.sources.brazil).select(j.source_band).projection();
 var chosen=ee.Image.constant(0).toInt16().reproject(base),sid=ee.Image.constant(0).toUint8().reproject(base),known={};
 ['chaco','bolivia','paraguay','brazil'].forEach(function(c){
  var x=ee.Image(r.sources[c]).select(j.source_band).reproject(base);
  var present=x.mask().gt(0).and(x.neq(0)).and(x.neq(27)).unmask(0,false);
  if(c==='chaco') present=present.and(x.eq(26).unmask(0,false));
  chosen=chosen.where(present,x.unmask(0,false));sid=sid.where(present,r.source_ids[c]);
  known[c]=x.remap(r.known_classes[c],r.known_classes[c].map(function(){return 1;}),0).unmask(0,false);
 });
 var valid=sid.gt(0);
 ['brazil','paraguay','bolivia','chaco'].forEach(function(c){valid=valid.and(sid.neq(r.source_ids[c]).or(known[c].eq(1)));});
 valid=valid.toDouble().setDefaultProjection(base);
 var target=ee.Projection(j.grid.crs,j.crs_transform);
 function agg(x){return x.toDouble().setDefaultProjection(base).reduceResolution({reducer:ee.Reducer.mean(),bestEffort:false,maxPixels:1024}).reproject(target);}
 var coverage=agg(valid).rename('valid_fraction'),complete=coverage.gte(1-1e-9);
 var out=agg(chosen.eq(12).and(valid)).updateMask(complete).rename('grassland_fraction').unmask(-9999,false)
  .addBands(agg(chosen.eq(11).and(valid)).updateMask(complete).rename('flooded_habitat_fraction').unmask(-9999,false)).addBands(coverage);
 ['brazil','paraguay','bolivia','chaco'].forEach(function(c,i){out=out.addBands(agg(sid.eq(r.source_ids[c]).and(valid)).rename(r.export_bands[i+3]));});
 Export.image.toDrive({image:out.toFloat(),description:j.export_prefix,folder:DRIVE_FOLDER,fileNamePrefix:j.export_prefix,
  region:ee.Geometry.Rectangle(j.grid.bounds,j.grid.crs,false),crs:j.grid.crs,crsTransform:j.crs_transform,
  maxPixels:j.output_cells*7,fileFormat:'GeoTIFF',formatOptions:{cloudOptimized:true,noData:-9999}});
});
'''


def prepare(checkpoint,output,collection='SPR-C01',source_snapshot=None):
    plan=make_plan(checkpoint,collection,read(source_snapshot) if source_snapshot else None)
    script='var PLAN = '+json.dumps(plan,sort_keys=True)+';\n'+JS;output=Path(output).resolve()
    with locked(output.parent):
        if output.exists():
            if verify_bundle(output)!=plan:raise ValueError('Bundle differs; choose new version')
            return output
        temp=Path(tempfile.mkdtemp(prefix='.pending-mapbiomas-',dir=output.parent))
        try:
            write(temp/'plan.json',plan);(temp/'extract_landcover.js').write_text(script)
            write(temp/'bundle.json',dict(schema='mapbiomas_landcover_export_bundle/1',plan_id=digest(plan),files={p.name:file_hash(p) for p in temp.iterdir()}))
            sync_files(temp);sync_dir(temp);os.rename(temp,output);sync_dir(output.parent)
        finally:
            if temp.exists():shutil.rmtree(temp)
    return output


def check_pixels(data,masks):
    if not masks.all() or not np.isfinite(data).all():raise ValueError('Missing/nonfinite values')
    if np.any(data<0) or np.any(data>1):raise ValueError('Fractions outside unit interval')
    if np.any(data[2]<1-1e-6):raise ValueError('Incomplete source coverage')
    if not np.allclose(data[3:].sum(axis=0),data[2],atol=1e-6,rtol=0):raise ValueError('Source fractions do not sum to coverage')
    if np.any(data[0]+data[1]+data[6]>1+1e-6):raise ValueError('Exclusive class/fallback fractions exceed one')


def convert(bundle,job_id,tif,output):
    import rasterio
    from affine import Affine
    bundle,tif,output=map(lambda p:Path(p).resolve(),(bundle,tif,output));plan=verify_bundle(bundle);job=plan['groups'][job_id]
    if tif.name!=job['export_prefix']+'.tif':raise ValueError('Unexpected filename')
    with rasterio.open(tif) as ds:
        g=job['grid']
        if ds.crs!=rasterio.crs.CRS.from_user_input(g['crs']):raise ValueError('CRS mismatch')
        if ds.shape!=(g['rows'],g['cols']) or ds.count!=7:raise ValueError('Shape/bands mismatch')
        if not np.allclose(tuple(ds.transform),tuple(Affine(*job['crs_transform'])),atol=1e-7,rtol=0):raise ValueError('Transform mismatch')
        if not np.allclose(tuple(ds.bounds),g['bounds'],atol=1e-7,rtol=0):raise ValueError('Bounds mismatch')
        data=ds.read();check_pixels(data,ds.read_masks()>0)
    names=['grassland_fraction','flooded_habitat_fraction']
    state=dict(schema='validated_mapbiomas_landcover_cache_product/1',job_id=job_id,group_id=job['group_id'],year=job['year'],grid_key=job['grid_key'],product_key=job['product_key'],grid=g,recipe=RECIPE,source_snapshot=plan.get('source_snapshot'),plan_sha256=file_hash(bundle/'plan.json'),script_sha256=file_hash(bundle/'extract_landcover.js'),source_tif_sha256=file_hash(tif),statistics={n:dict(minimum=float(data[i].min()),maximum=float(data[i].max()),mean=float(data[i].mean())) for i,n in enumerate(names)},fallback_fraction_max=float(data[6].max()),fallback_fraction_mean=float(data[6].mean()),fallback_cells=int(np.count_nonzero(data[6]>1e-6)),fallback_projected_area_m2=float(data[6].astype(np.float64).sum()*g['cell_size_m']**2),epoch_role='candidate cache; not chosen representative year',quality='software spatial/coverage/numerical checks passed; ecological validation pending')
    with locked(output.parent):
        if output.exists():
            if read(output/'validation.json')!=state or file_hash(output/'source.tif')!=state['source_tif_sha256']:raise ValueError('Existing product differs')
            for i,n in enumerate(names):
                if not np.array_equal(np.load(output/(n+'.npy'),allow_pickle=False),data[i]):raise ValueError('Existing NPY differs')
            return output
        temp=Path(tempfile.mkdtemp(prefix='.pending-mapbiomas-product-',dir=output.parent))
        try:
            shutil.copyfile(tif,temp/'source.tif')
            for i,n in enumerate(names):
                with (temp/(n+'.npy')).open('wb') as f:np.save(f,data[i].astype(np.float32),allow_pickle=False);f.flush();os.fsync(f.fileno())
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
