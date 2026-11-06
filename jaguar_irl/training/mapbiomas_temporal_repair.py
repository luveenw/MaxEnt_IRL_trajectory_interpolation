"""User-approved, exact one-pixel 2011 temporal consensus repair; no general imputer."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import numpy as np
from jaguar_irl.data.pantanal_checkpoint import digest,file_hash
from .shared_storage import read,write,locked,sync_dir
from .terrain_roughness import verify_bundle,sync_files
from .mapbiomas_landcover import SOURCES,SOURCE_IDS,RECIPE as BASE_RECIPE,native_mosaic

ROOT=Path(__file__).resolve().parents[2]
ORIGINAL_BUNDLE=ROOT/'gee/spring_mapbiomas_landcover_v1/jobs'
DATA=ROOT/'data/pantanal_covariates/spring_mapbiomas_landcover_v1'
APPROVAL=DATA/'approved_G316_temporal_repair.json'
HERE=ROOT/'gee/spring_mapbiomas_landcover_v1/repairs/G316_2011_temporal_consensus_v1'
REPAIR_DATA=DATA/'repairs/G316_2011_temporal_consensus_v1'
BANDS=['grassland_fraction','flooded_habitat_fraction','valid_fraction',
       'source_brazil_fraction','source_paraguay_fraction','source_bolivia_fraction',
       'chaco_fallback_fraction','observed_valid_fraction','temporal_imputed_fraction']
RECIPE=copy.deepcopy(BASE_RECIPE)
RECIPE.update(id='mapbiomas_grass_wet_G316_2011_exact_temporal_consensus_v1',export_bands=BANDS,
              temporal_repair={'year':2011,'previous_year':2010,'next_year':2012,'source_native_col':60974,'source_native_row':86248,
              'condition':'Exact native pixel only; original source unavailable and both adjacent Brazil years observed and class4',
              'assigned_value':'Retrieved 2010 class after equality with retrieved 2012 and class4 guards',
              'approved_class':4,'class_name':'Savanna formation; non-target for both features'},
              coverage_policy='valid_fraction is effective supported coverage = observed_valid_fraction + temporal_imputed_fraction; country fractions are observed current-year support only',
              no_generalization='This does not authorize neighboring-pixel, other-year or other-class imputation')


def make_plan():
    old=verify_bundle(ORIGINAL_BUNDLE);original=old['groups']['G316_2011'];job=copy.deepcopy(original)
    approval=read(APPROVAL)
    product=digest(dict(original_product_key=original['product_key'],recipe=RECIPE,approval_sha256=file_hash(APPROVAL),source_fingerprint=old['source_snapshot']['asset_fingerprint']))
    job.update(product_key=product,export_prefix=f'SPR-C01_G316_2011_mapbiomas_temporal_{product[:12]}')
    return dict(schema='mapbiomas_exact_temporal_repair_plan/1',groups={'G316_2011':job},job_count=1,group_count=1,
                recipe=RECIPE,source_snapshot=old['source_snapshot'],software_sha256=file_hash(__file__),
                original_bundle=str(ORIGINAL_BUNDLE),original_plan_sha256=file_hash(ORIGINAL_BUNDLE/'plan.json'),
                original_product_key=original['product_key'],original_failed_ledger=str(DATA/'tasks/G316_2011.json'),
                original_failed_tif_sha256=read(DATA/'tasks/G316_2011.json')['download_sha256'],
                approval=approval,approval_sha256=file_hash(APPROVAL),checkpoint=old['checkpoint'],
                checkpoint_sha256=old['checkpoint_sha256'],grids_sha256=old['grids_sha256'],
                epoch_role='candidate-year cache; final representative year remains unselected')


def native_repair(ee):
    chosen,sid,observed,base=native_mosaic(ee,2011)
    brazil=ee.Image(SOURCES['brazil'])
    previous=brazil.select('classification_2010').reproject(base)
    following=brazil.select('classification_2012').reproject(base)
    xy=ee.Image.pixelCoordinates(base)
    scope=xy.select('x').floor().eq(60974).And(xy.select('y').floor().eq(86248))
    # User-approved consensus is checked against real neighboring-year GEE data.
    # Only this exact missing 2011 native pixel may inherit their shared class.
    # Class4 is savanna, so it contributes zero to both requested feature indicators.
    agree=(previous.mask().gt(0).And(following.mask().gt(0))
           .And(previous.eq(following)).And(previous.eq(4)).unmask(0,False))
    patch=scope.And(sid.eq(0)).And(observed.eq(0)).And(agree).toDouble().setDefaultProjection(base)
    repaired=chosen.where(patch,previous.unmask(0,False))
    return repaired,sid,observed,patch,previous,following,base


def build_ee_image(ee,job):
    if job['year']!=2011 or job['group_id']!='G316':raise ValueError('Repair scope must be exactly G316_2011')
    chosen,sid,observed,patch,_,_,base=native_repair(ee)
    effective=observed.add(patch).min(1)
    target=ee.Projection(job['grid']['crs'],job['crs_transform'])
    def aggregate(image):return image.toDouble().setDefaultProjection(base).reduceResolution(ee.Reducer.mean(),bestEffort=False,maxPixels=1024).reproject(target)
    coverage=aggregate(effective).rename(BANDS[2]);complete=coverage.gte(1-1e-9)
    result=aggregate(chosen.eq(12).And(effective)).updateMask(complete).rename(BANDS[0]).unmask(-9999,False)
    result=result.addBands(aggregate(chosen.eq(11).And(effective)).updateMask(complete).rename(BANDS[1]).unmask(-9999,False)).addBands(coverage)
    for country,name in zip(('brazil','paraguay','bolivia','chaco'),BANDS[3:7]):result=result.addBands(aggregate(sid.eq(SOURCE_IDS[country]).And(observed)).rename(name))
    return result.addBands(aggregate(observed).rename(BANDS[7])).addBands(aggregate(patch).rename(BANDS[8])).toFloat()


JS=r'''// USER-APPROVED EXACT ONE-PIXEL REPAIR, not a general temporal interpolation.
// Read the actual 2010 and 2012 MapBiomas Brazil classes at runtime.
// Repair only source pixel col60974,row86248 in the missing G316 2011 image,
// and only if BOTH adjacent years are observed, agree, and equal class4 Savanna.
// The retrieved class is used, rather than assigning a value without retrieval.
var j=PLAN.groups.G316_2011,r=PLAN.recipe,src=r.sources;
var current=ee.Image(src.brazil).select('classification_2011'),base=current.projection();
var chosen=ee.Image.constant(0).toInt16().reproject(base),sid=ee.Image.constant(0).toUint8().reproject(base),known={};
['chaco','bolivia','paraguay','brazil'].forEach(function(c){
 var x=ee.Image(src[c]).select('classification_2011').reproject(base);
 var present=x.mask().gt(0).and(x.neq(0)).and(x.neq(27)).unmask(0,false);
 if(c==='chaco')present=present.and(x.eq(26).unmask(0,false));
 chosen=chosen.where(present,x.unmask(0,false));sid=sid.where(present,r.source_ids[c]);
 known[c]=x.remap(r.known_classes[c],r.known_classes[c].map(function(){return 1;}),0).unmask(0,false);
});
var observed=sid.gt(0);
['brazil','paraguay','bolivia','chaco'].forEach(function(c){observed=observed.and(sid.neq(r.source_ids[c]).or(known[c].eq(1)));});
observed=observed.toDouble().setDefaultProjection(base);
var previous=ee.Image(src.brazil).select('classification_2010').reproject(base);
var following=ee.Image(src.brazil).select('classification_2012').reproject(base);
var xy=ee.Image.pixelCoordinates(base);
var scope=xy.select('x').floor().eq(60974).and(xy.select('y').floor().eq(86248));
var agree=previous.mask().gt(0).and(following.mask().gt(0)).and(previous.eq(following)).and(previous.eq(4)).unmask(0,false);
var patch=scope.and(sid.eq(0)).and(observed.eq(0)).and(agree).toDouble().setDefaultProjection(base);
chosen=chosen.where(patch,previous.unmask(0,false));
var effective=observed.add(patch).min(1),target=ee.Projection(j.grid.crs,j.crs_transform);
function agg(x){return x.toDouble().setDefaultProjection(base).reduceResolution({reducer:ee.Reducer.mean(),bestEffort:false,maxPixels:1024}).reproject(target);}
var coverage=agg(effective).rename(r.export_bands[2]),complete=coverage.gte(1-1e-9);
var out=agg(chosen.eq(12).and(effective)).updateMask(complete).rename(r.export_bands[0]).unmask(-9999,false)
 .addBands(agg(chosen.eq(11).and(effective)).updateMask(complete).rename(r.export_bands[1]).unmask(-9999,false)).addBands(coverage);
['brazil','paraguay','bolivia','chaco'].forEach(function(c,i){out=out.addBands(agg(sid.eq(r.source_ids[c]).and(observed)).rename(r.export_bands[i+3]));});
out=out.addBands(agg(observed).rename(r.export_bands[7])).addBands(agg(patch).rename(r.export_bands[8]));
Map.addLayer(out.select('temporal_imputed_fraction'),{min:0,max:.004},'Explicit temporal-imputation fraction');
Export.image.toDrive({image:out.toFloat(),description:j.export_prefix,folder:'pantanal_spring_mapbiomas_landcover_v1',fileNamePrefix:j.export_prefix,
 region:ee.Geometry.Rectangle(j.grid.bounds,j.grid.crs,false),crs:j.grid.crs,crsTransform:j.crs_transform,maxPixels:j.output_cells*9,
 fileFormat:'GeoTIFF',formatOptions:{cloudOptimized:true,noData:-9999}});
'''


def prepare():
    plan=make_plan();output=HERE/'jobs';script='var PLAN = '+json.dumps(plan,sort_keys=True)+';\n'+JS
    with locked(output.parent):
        if output.exists():
            if verify_bundle(output)!=plan:raise ValueError('Existing repair plan differs')
            return output
        temp=Path(tempfile.mkdtemp(prefix='.pending-repair-',dir=output.parent))
        try:
            write(temp/'plan.json',plan);(temp/'extract_landcover_temporal_repair.js').write_text(script)
            write(temp/'bundle.json',dict(schema='mapbiomas_exact_repair_bundle/1',plan_id=digest(plan),files={p.name:file_hash(p) for p in temp.iterdir()}))
            sync_files(temp);sync_dir(temp);os.rename(temp,output);sync_dir(output.parent)
        finally:
            if temp.exists():shutil.rmtree(temp)
    return output


def check_pixels(data,masks):
    if not masks.all() or not np.isfinite(data).all():raise ValueError('Missing/nonfinite repair values')
    if np.any(data<0) or np.any(data>1):raise ValueError('Repair fractions outside unit interval')
    if np.any(data[2]<1-1e-6):raise ValueError('Effective coverage incomplete')
    if not np.allclose(data[3:7].sum(axis=0),data[7],atol=1e-6,rtol=0):raise ValueError('Observed source fractions do not sum to observed coverage')
    if not np.allclose(data[7]+data[8],data[2],atol=1e-6,rtol=0):raise ValueError('Observed and imputed fractions do not sum to effective coverage')
    if np.any(data[0]+data[1]+data[6]+data[8]>1+1e-6):raise ValueError('Targets overlap water/imputed savanna')
    cells=np.argwhere(data[8]>1e-6)
    if cells.tolist()!=[[20,13]]:raise ValueError('Imputation escaped the exact approved target cell')
    if not .0034<float(data[8,20,13])<.00342:raise ValueError('Imputation area differs from one native pixel')
    if not np.allclose(data[2]-data[7],data[8],atol=1e-6,rtol=0):raise ValueError('Observed coverage was overwritten')


def convert(bundle,tif,output):
    import rasterio
    from affine import Affine
    bundle,tif,output=map(lambda p:Path(p).resolve(),(bundle,tif,output));plan=verify_bundle(bundle);job=plan['groups']['G316_2011'];g=job['grid']
    if tif.name!=job['export_prefix']+'.tif':raise ValueError('Repair filename mismatch')
    with rasterio.open(tif) as ds:
        if ds.crs!=rasterio.crs.CRS.from_user_input(g['crs']) or ds.shape!=(g['rows'],g['cols']) or ds.count!=9:raise ValueError('Repair CRS/shape/bands mismatch')
        if not np.allclose(tuple(ds.transform),tuple(Affine(*job['crs_transform'])),rtol=0,atol=1e-7):raise ValueError('Repair transform mismatch')
        if not np.allclose(tuple(ds.bounds),g['bounds'],rtol=0,atol=1e-7):raise ValueError('Repair bounds mismatch')
        data=ds.read();check_pixels(data,ds.read_masks()>0)
    state=dict(schema='validated_mapbiomas_temporal_repair_product/1',job_id='G316_2011',group_id='G316',year=2011,
               grid_key=g['grid_key'],product_key=job['product_key'],grid=g,recipe=RECIPE,source_snapshot=plan['source_snapshot'],
               plan_sha256=file_hash(bundle/'plan.json'),script_sha256=file_hash(bundle/'extract_landcover_temporal_repair.js'),
               software_sha256=file_hash(__file__),source_tif_sha256=file_hash(tif),original_plan_sha256=plan['original_plan_sha256'],
               original_product_key=plan['original_product_key'],approval_sha256=plan['approval_sha256'],
               statistics={n:dict(minimum=float(data[i].min()),maximum=float(data[i].max()),mean=float(data[i].mean())) for i,n in enumerate(BANDS[:2])},
               imputed_cells=1,imputed_projected_area_m2=float(data[8].astype(np.float64).sum()*250000),
               observed_coverage_min=float(data[7].min()),effective_coverage_min=float(data[2].min()),
               fallback_fraction_max=float(data[6].max()),fallback_cells=int(np.count_nonzero(data[6]>1e-6)),
               quality='User-approved exact temporal consensus; observed/imputed support distinguished; ecological validation pending',
               epoch_role='candidate cache; final representative year not selected')
    with locked(output.parent):
        if output.exists():
            if read(output/'validation.json')!=state or file_hash(output/'source.tif')!=state['source_tif_sha256']:raise ValueError('Existing repair product changed')
            for i,n in enumerate(BANDS[:2]):
                if not np.array_equal(np.load(output/(n+'.npy'),allow_pickle=False),data[i]):raise ValueError('Existing repair NPY changed')
            return output
        temp=Path(tempfile.mkdtemp(prefix='.pending-repair-product-',dir=output.parent))
        try:
            shutil.copyfile(tif,temp/'source.tif')
            for i,n in enumerate(BANDS[:2]):
                with (temp/(n+'.npy')).open('wb') as f:np.save(f,data[i].astype(np.float32),allow_pickle=False);f.flush();os.fsync(f.fileno())
            write(temp/'validation.json',state);write(temp/'checksums.json',{p.name:file_hash(p) for p in temp.iterdir()})
            sync_files(temp);sync_dir(temp);os.rename(temp,output);sync_dir(output.parent)
        finally:
            if temp.exists():shutil.rmtree(temp)
    return output

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare']);p.parse_args();print(prepare())
