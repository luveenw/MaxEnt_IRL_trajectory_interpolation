"""MapBiomas 3+4 classified-area fraction; shared, split-independent Spring cache."""
import copy,json,os,shutil,tempfile
from pathlib import Path
import numpy as np
from jaguar_irl.data.pantanal_checkpoint import digest,file_hash
from .shared_storage import read,write,locked,sync_dir
from .terrain_roughness import verify_bundle,sync_files
from .mapbiomas_landcover import SOURCES,SOURCE_IDS,KNOWN,native_mosaic,make_plan as base_plan
from .mapbiomas_temporal_repair import native_repair,APPROVAL

BANDS=['forest_savanna_fraction','valid_fraction','source_brazil_fraction','source_paraguay_fraction',
       'source_bolivia_fraction','chaco_fallback_fraction','observed_valid_fraction','temporal_imputed_fraction']
RECIPE=dict(id='mapbiomas_forest_savanna_3_4_area_fraction_v1',sources=SOURCES,source_ids=SOURCE_IDS,
 known_classes=KNOWN,source_priority=['brazil','paraguay','bolivia','chaco26_gap_only'],selected_classes=[3,4],
 excluded_flooded_woody_classes=[6,7],feature='forest_savanna_fraction',units='classified area fraction (0-1)',
 meaning='Forest/closed woodland3 and savanna/open woodland4; includes tree/shrub mixtures; not continuous canopy closure or a height threshold',
 aggregation='Native categorical binary membership, overlap-area-weighted mean on exact saved 500m EPSG32721 cells',
 smoothing=None,export_bands=BANDS,nodata=-9999,
 temporal_repair=dict(job_id='G316_2011',native_col=60974,native_row=86248,previous_year=2010,next_year=2012,
  guard='Only source-unavailable exact pixel; both actual adjacent Brazil years observed and equal4; retrieved2010 class used',
  contribution='Class4 contributes one to forest/savanna membership'),
 coverage_policy='effective=observed+temporal; source fractions are observed current-year support only',
 temporal_scope='Annual map applied throughout Spring Aug15-Nov14; no sub-season observations; all candidate years cached')


def make_plan(checkpoint,snapshot):
    plan=base_plan(checkpoint,source_snapshot=snapshot)
    plan.update(schema='pantanal_mapbiomas_wooded_cover_cache_plan/1',recipe=RECIPE,
      software_sha256=file_hash(__file__),dependencies_sha256={p.name:file_hash(p) for p in
      [Path(__file__).with_name('mapbiomas_landcover.py'),Path(__file__).with_name('mapbiomas_temporal_repair.py')]},
      approval_sha256=file_hash(APPROVAL),approval=read(APPROVAL))
    for key,j in plan['groups'].items():
        product=digest(dict(grid=j['grid'],year=j['year'],recipe=RECIPE,source_fingerprint=snapshot['asset_fingerprint'],approval_sha256=plan['approval_sha256']))
        j.update(product_key=product,export_prefix=f'SPR-C01_{key}_wooded_{product[:12]}')
    return plan


def build_ee_image(ee,job):
    if job['group_id']=='G316' and job['year']==2011:
        chosen,sid,observed,patch,_,_,base=native_repair(ee)
    else:
        chosen,sid,observed,base=native_mosaic(ee,job['year'])
        patch=ee.Image.constant(0).toDouble().reproject(base)
    effective=observed.add(patch).min(1)
    target=ee.Projection(job['grid']['crs'],job['crs_transform'])
    def agg(x):return x.toDouble().setDefaultProjection(base).reduceResolution(ee.Reducer.mean(),bestEffort=False,maxPixels=1024).reproject(target)
    coverage=agg(effective).rename(BANDS[1]);complete=coverage.gte(1-1e-9)
    # The repaired class4 pixel contributes one here (unlike grassland/wetland).
    wooded=chosen.eq(3).Or(chosen.eq(4)).And(effective)
    out=agg(wooded).updateMask(complete).rename(BANDS[0]).unmask(-9999,False).addBands(coverage)
    for c,name in zip(('brazil','paraguay','bolivia','chaco'),BANDS[2:6]):out=out.addBands(agg(sid.eq(SOURCE_IDS[c]).And(observed)).rename(name))
    return out.addBands(agg(observed).rename(BANDS[6])).addBands(agg(patch).rename(BANDS[7])).toFloat()


JS=r'''// Forest/savanna CLASSIFIED AREA fraction, not measured tree-canopy percentage.
// Selected native classes3+4; exclude separately mapped flooded woody classes6/7.
// Shared cache products: no animal split is applied during acquisition.
var JOB_IDS=[PLAN.default_pilot_job],MAX_TASKS=1;
if(!JOB_IDS.length||JOB_IDS.length>MAX_TASKS)throw new Error('Task bound exceeded');
var seen={};JOB_IDS.forEach(function(id){
 if(!PLAN.groups[id]||seen[id])throw new Error('Unknown/duplicate job');seen[id]=true;
 var j=PLAN.groups[id],r=PLAN.recipe,base=ee.Image(r.sources.brazil).select(j.source_band).projection();
 var chosen=ee.Image.constant(0).toInt16().reproject(base),sid=ee.Image.constant(0).toUint8().reproject(base),known={};
 ['chaco','bolivia','paraguay','brazil'].forEach(function(c){
  var x=ee.Image(r.sources[c]).select(j.source_band).reproject(base);
  var present=x.mask().gt(0).and(x.neq(0)).and(x.neq(27)).unmask(0,false);
  if(c==='chaco')present=present.and(x.eq(26).unmask(0,false));
  chosen=chosen.where(present,x.unmask(0,false));sid=sid.where(present,r.source_ids[c]);
  known[c]=x.remap(r.known_classes[c],r.known_classes[c].map(function(){return 1;}),0).unmask(0,false);
 });
 var observed=sid.gt(0);['brazil','paraguay','bolivia','chaco'].forEach(function(c){observed=observed.and(sid.neq(r.source_ids[c]).or(known[c].eq(1)));});
 observed=observed.toDouble().setDefaultProjection(base);var patch=ee.Image.constant(0).toDouble().reproject(base);
 if(id==='G316_2011'){
  // Approved exact-pixel repair: retrieve ACTUAL adjacent years and require
  // observed2010==observed2012==4, original source unavailable, col60974,row86248.
  // This is not general interpolation. Retrieved2010 class4 contributes ONE
  // to this wooded indicator, unlike the grassland/narrow-wetland covariates.
  var previous=ee.Image(r.sources.brazil).select('classification_2010').reproject(base);
  var following=ee.Image(r.sources.brazil).select('classification_2012').reproject(base);
  var xy=ee.Image.pixelCoordinates(base);
  var scope=xy.select('x').floor().eq(60974).and(xy.select('y').floor().eq(86248));
  var agree=previous.mask().gt(0).and(following.mask().gt(0)).and(previous.eq(following)).and(previous.eq(4)).unmask(0,false);
  patch=scope.and(sid.eq(0)).and(observed.eq(0)).and(agree).toDouble().setDefaultProjection(base);
  chosen=chosen.where(patch,previous.unmask(0,false));
 }
 var effective=observed.add(patch).min(1),target=ee.Projection(j.grid.crs,j.crs_transform);
 function agg(x){return x.toDouble().setDefaultProjection(base).reduceResolution({reducer:ee.Reducer.mean(),bestEffort:false,maxPixels:1024}).reproject(target);}
 var coverage=agg(effective).rename(r.export_bands[1]),complete=coverage.gte(1-1e-9);
 var out=agg(chosen.eq(3).or(chosen.eq(4)).and(effective)).updateMask(complete).rename(r.export_bands[0]).unmask(-9999,false).addBands(coverage);
 ['brazil','paraguay','bolivia','chaco'].forEach(function(c,i){out=out.addBands(agg(sid.eq(r.source_ids[c]).and(observed)).rename(r.export_bands[i+2]));});
 out=out.addBands(agg(observed).rename(r.export_bands[6])).addBands(agg(patch).rename(r.export_bands[7]));
 Export.image.toDrive({image:out.toFloat(),description:j.export_prefix,folder:'pantanal_spring_mapbiomas_wooded_cover_v1',fileNamePrefix:j.export_prefix,
 region:ee.Geometry.Rectangle(j.grid.bounds,j.grid.crs,false),crs:j.grid.crs,crsTransform:j.crs_transform,maxPixels:j.output_cells*8,
 fileFormat:'GeoTIFF',formatOptions:{cloudOptimized:true,noData:-9999}});
});'''


def prepare(checkpoint,output,snapshot):
    plan=make_plan(checkpoint,read(snapshot));output=Path(output)
    if output.exists():
        if verify_bundle(output)!=plan:raise ValueError('Existing frozen bundle differs')
        return output
    output.mkdir(parents=True)
    write(output/'plan.json',plan);(output/'extract_wooded_cover.js').write_text('var PLAN = '+json.dumps(plan,sort_keys=True)+';\n'+JS)
    write(output/'bundle.json',dict(schema='mapbiomas_wooded_cover_bundle/1',plan_id=digest(plan),files={p.name:file_hash(p) for p in output.iterdir()}))
    return output


def check_pixels(data,masks,job_id):
    if not masks.all() or not np.isfinite(data).all():raise ValueError('Missing/nonfinite data')
    if np.any(data<0) or np.any(data>1):raise ValueError('Fraction outside0-1')
    if np.any(data[1]<1-1e-6):raise ValueError('Incomplete effective source coverage')
    if not np.allclose(data[2:6].sum(axis=0),data[6],atol=1e-6,rtol=0):raise ValueError('Source fractions differ from observed coverage')
    if not np.allclose(data[6]+data[7],data[1],atol=1e-6,rtol=0):raise ValueError('Observed/imputed do not sum to effective')
    if np.any(data[0]+data[5]>1+1e-6):raise ValueError('Wooded and Chaco water fractions overlap')
    nz=np.argwhere(data[7]>1e-8)
    if job_id=='G316_2011':
        if nz.tolist()!=[[20,13]] or not np.isclose(data[7,20,13],.003405881,atol=1e-6):raise ValueError('Repair footprint differs from approved one cell')
        if data[0,20,13]+1e-6<data[7,20,13]:raise ValueError('Repaired class4 omitted from wooded fraction')
    elif len(nz):raise ValueError('Unexpected temporal imputation')


def convert(bundle,job_id,tif,output):
    import rasterio
    from affine import Affine
    bundle,tif,output=map(lambda x:Path(x).resolve(),(bundle,tif,output));plan=verify_bundle(bundle);job=plan['groups'][job_id];g=job['grid']
    if tif.name!=job['export_prefix']+'.tif':raise ValueError('Unexpected filename')
    with rasterio.open(tif) as ds:
        if ds.crs!=rasterio.crs.CRS.from_user_input(g['crs']) or ds.shape!=(g['rows'],g['cols']) or ds.count!=8:raise ValueError('CRS/shape/bands mismatch')
        if not np.allclose(tuple(ds.transform),tuple(Affine(*job['crs_transform'])),atol=1e-7,rtol=0) or not np.allclose(tuple(ds.bounds),g['bounds'],atol=1e-7,rtol=0):raise ValueError('Transform/bounds mismatch')
        data=ds.read();check_pixels(data,ds.read_masks()>0,job_id)
    state=dict(schema='validated_mapbiomas_wooded_cover_product/1',job_id=job_id,group_id=job['group_id'],year=job['year'],product_key=job['product_key'],grid_key=job['grid_key'],grid=g,recipe=RECIPE,
      source_snapshot=plan['source_snapshot'],plan_sha256=file_hash(bundle/'plan.json'),script_sha256=file_hash(bundle/'extract_wooded_cover.js'),source_tif_sha256=file_hash(tif),
      statistics=dict(minimum=float(data[0].min()),maximum=float(data[0].max()),mean=float(data[0].mean())),
      observed_coverage_min=float(data[6].min()),effective_coverage_min=float(data[1].min()),imputed_cells=int(np.count_nonzero(data[7])),
      imputed_projected_area_m2=float(data[7].astype(float).sum()*250000),fallback_cells=int(np.count_nonzero(data[5])),
      epoch_role='shared split-independent candidate cache; representative year not selected',quality='software coverage/grid/numerical QA passed; ecological accuracy not established')
    with locked(output.parent):
        if output.exists():
            if read(output/'validation.json')!=state:raise ValueError('Existing product differs')
            checks=read(output/'checksums.json')
            if any(file_hash(output/name)!=sha for name,sha in checks.items()):raise ValueError('Existing product checksum mismatch')
            return output
        temp=Path(tempfile.mkdtemp(prefix='.pending-wooded-',dir=output.parent))
        try:
            shutil.copyfile(tif,temp/'source.tif');np.save(temp/'forest_savanna_fraction.npy',data[0].astype(np.float32),allow_pickle=False)
            write(temp/'validation.json',state);write(temp/'checksums.json',{p.name:file_hash(p) for p in temp.iterdir()})
            sync_files(temp);sync_dir(temp);os.rename(temp,output);sync_dir(output.parent)
        finally:
            if temp.exists():shutil.rmtree(temp)
    return output
