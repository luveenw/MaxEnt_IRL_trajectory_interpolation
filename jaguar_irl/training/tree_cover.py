"""Static Hansen 2000 continuous canopy percent on exact checkpoint grids."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import numpy as np
from jaguar_irl.data.pantanal_checkpoint import digest, file_hash
from .shared_storage import locked, read, write, sync_dir
from .terrain_roughness import make_plan as terrain_plan, sync_files, verify_bundle

SOURCE='UMD/hansen/global_forest_change_2025_v1_13'
RECIPE=dict(id='hansen_2000_canopy_percent_area_mean_v1',source=SOURCE,band='treecover2000',
 source_epoch=2000,output_units='percent canopy closure (0-100)',tree_definition='vegetation taller than 5m',
 aggregation='overlap-area-weighted mean of native canopy percentages over full target cell',
 threshold=None,smoothing=None,loss_gain_adjustment=None,temporal_filter=None,
 mask_policy='mapped land requires valid canopy; permanent water is zero canopy; true NoData invalid',
 export_bands=['tree_cover_percent','valid_fraction','permanent_water_fraction','water_nonzero_canopy_fraction'],nodata=-9999)

def make_plan(checkpoint,collection='SPR-C01',source_snapshot=None):
 p=terrain_plan(checkpoint,collection)
 for key,j in p['groups'].items():
  product=digest(dict(grid=j['grid'],recipe=RECIPE,source_fingerprint=(source_snapshot or {}).get('asset_fingerprint')))
  j.update(product_key=product,source_band='treecover2000',source_epoch=2000,export_prefix=f'{collection}_{key}_tree_cover_2000_{product[:12]}')
 p.update(schema='pantanal_static_tree_cover_plan/1',recipe=RECIPE,source_snapshot=source_snapshot,
  software_sha256=file_hash(__file__),group_count=len(p['groups']),job_count=len(p['groups']),
  default_pilot_job=p['default_pilot_group'],temporal_role='Fixed year-2000 baseline; no season-year compositing or representative-year dependence')
 return p

def build_ee_image(ee,job):
 src=ee.Image(SOURCE);tc=src.select('treecover2000');dm=src.select('datamask');base=tc.projection()
 # Explicit validity avoids excluding water/zero canopy from a target denominator.
 water=dm.eq(2).And(dm.mask().gt(0)).unmask(0,False)
 land=dm.eq(1).And(dm.mask().gt(0)).And(tc.mask().gt(0)).And(tc.gte(0)).And(tc.lte(100)).unmask(0,False)
 valid=land.Or(water).toDouble().setDefaultProjection(base)
 canopy=tc.unmask(0,False).where(water,0).multiply(valid).toDouble().setDefaultProjection(base)
 target=ee.Projection(job['grid']['crs'],job['crs_transform'])
 def agg(x):return x.toDouble().setDefaultProjection(base).reduceResolution(ee.Reducer.mean(),bestEffort=False,maxPixels=1024).reproject(target)
 coverage=agg(valid).rename('valid_fraction')
 out=agg(canopy).updateMask(coverage.gte(1-1e-9)).rename('tree_cover_percent').unmask(-9999,False)
 return out.addBands(coverage).addBands(agg(water).rename('permanent_water_fraction')).addBands(agg(water.And(tc.unmask(0,False).neq(0))).rename('water_nonzero_canopy_fraction')).toFloat()

JS=r'''// Hansen treecover2000: continuous canopy closure percent for vegetation taller than 5m.
// Fixed 2000 baseline. No threshold, smoothing, or loss/gain adjustment.
var DRIVE_FOLDER='pantanal_spring_hansen_tree_cover_v1';
var GROUP_IDS=[PLAN.default_pilot_job],MAX_TASKS=1;
if(!GROUP_IDS.length||GROUP_IDS.length>MAX_TASKS)throw new Error('Bounded task count exceeded');
var seen={};
GROUP_IDS.forEach(function(id){
 if(!PLAN.groups[id]||seen[id])throw new Error('Unknown/duplicate group');seen[id]=true;
 var j=PLAN.groups[id],src=ee.Image(PLAN.recipe.source),tc=src.select('treecover2000'),dm=src.select('datamask'),base=tc.projection();
 // Keep valid zero cover and permanent water in full-cell area denominator; true NoData fails coverage QA.
 var water=dm.eq(2).and(dm.mask().gt(0)).unmask(0,false);
 var land=dm.eq(1).and(dm.mask().gt(0)).and(tc.mask().gt(0)).and(tc.gte(0)).and(tc.lte(100)).unmask(0,false);
 var valid=land.or(water).toDouble().setDefaultProjection(base);
 var canopy=tc.unmask(0,false).where(water,0).multiply(valid).toDouble().setDefaultProjection(base);
 var target=ee.Projection(j.grid.crs,j.crs_transform);
 function agg(x){return x.toDouble().setDefaultProjection(base).reduceResolution({reducer:ee.Reducer.mean(),bestEffort:false,maxPixels:1024}).reproject(target);}
 var coverage=agg(valid).rename('valid_fraction');
 var out=agg(canopy).updateMask(coverage.gte(1-1e-9)).rename('tree_cover_percent').unmask(-9999,false)
  .addBands(coverage).addBands(agg(water).rename('permanent_water_fraction'))
  .addBands(agg(water.and(tc.unmask(0,false).neq(0))).rename('water_nonzero_canopy_fraction')).toFloat();
 Export.image.toDrive({image:out,description:j.export_prefix,folder:DRIVE_FOLDER,fileNamePrefix:j.export_prefix,
 region:ee.Geometry.Rectangle(j.grid.bounds,j.grid.crs,false),crs:j.grid.crs,crsTransform:j.crs_transform,
 maxPixels:j.output_cells*4,fileFormat:'GeoTIFF',formatOptions:{cloudOptimized:true,noData:-9999}});
});
'''

def prepare(checkpoint,output,collection='SPR-C01',source_snapshot=None):
 p=make_plan(checkpoint,collection,read(source_snapshot) if source_snapshot else None);output=Path(output).resolve()
 with locked(output.parent):
  if output.exists():
   if verify_bundle(output)!=p:raise ValueError('Bundle differs; choose new version')
   return output
  temp=Path(tempfile.mkdtemp(prefix='.pending-tree-bundle-',dir=output.parent))
  try:
   write(temp/'plan.json',p);(temp/'extract_tree_cover.js').write_text('var PLAN = '+json.dumps(p,sort_keys=True)+';\n'+JS)
   write(temp/'bundle.json',dict(schema='hansen_tree_cover_bundle/1',plan_id=digest(p),files={f.name:file_hash(f) for f in temp.iterdir()}))
   sync_files(temp);sync_dir(temp);os.rename(temp,output);sync_dir(output.parent)
  finally:
   if temp.exists():shutil.rmtree(temp)
 return output

def check_pixels(data,masks):
 if data.shape[0]!=4 or not masks.all() or not np.isfinite(data).all():raise ValueError('Missing/nonfinite values or wrong bands')
 tc,valid,water,conflict=data
 if np.any(tc<0) or np.any(tc>100):raise ValueError('Canopy outside percent range')
 if np.any(valid<1-1e-6) or np.any(valid>1):raise ValueError('Incomplete source coverage')
 if np.any(water<0) or np.any(water>valid+1e-6):raise ValueError('Invalid water fraction')
 if np.any(conflict!=0):raise ValueError('Source water contains nonzero canopy; investigate')
 if np.any(tc>100*(1-water)+1e-4):raise ValueError('Canopy exceeds nonwater area')

def convert(bundle,job_id,tif,output):
 import rasterio
 from affine import Affine
 bundle,tif,output=map(lambda p:Path(p).resolve(),(bundle,tif,output));p=verify_bundle(bundle);j=p['groups'][job_id];g=j['grid']
 if tif.name!=j['export_prefix']+'.tif':raise ValueError('Unexpected filename')
 with rasterio.open(tif) as ds:
  if ds.crs!=rasterio.crs.CRS.from_user_input(g['crs']) or ds.shape!=(g['rows'],g['cols']) or ds.count!=4:raise ValueError('Grid CRS/shape/bands mismatch')
  if not np.allclose(tuple(ds.transform),tuple(Affine(*j['crs_transform'])),atol=1e-7,rtol=0) or not np.allclose(tuple(ds.bounds),g['bounds'],atol=1e-7,rtol=0):raise ValueError('Transform/bounds mismatch')
  data=ds.read();check_pixels(data,ds.read_masks()>0)
 v=dict(schema='validated_static_hansen_tree_cover/1',group_id=j['group_id'],grid_key=j['grid_key'],grid=g,product_key=j['product_key'],source_epoch=2000,units=RECIPE['output_units'],recipe=RECIPE,source_snapshot=p['source_snapshot'],plan_sha256=file_hash(bundle/'plan.json'),script_sha256=file_hash(bundle/'extract_tree_cover.js'),source_tif_sha256=file_hash(tif),minimum=float(data[0].min()),maximum=float(data[0].max()),mean=float(data[0].mean()),water_fraction_mean=float(data[2].mean()),water_fraction_maximum=float(data[2].max()),valid_fraction_minimum=float(data[1].min()),quality='Exact-grid/full-coverage/range/water QA passed; ecological accuracy unvalidated')
 with locked(output.parent):
  if output.exists():
   if read(output/'validation.json')!=v or file_hash(output/'source.tif')!=v['source_tif_sha256'] or not np.array_equal(np.load(output/'tree_cover.npy',allow_pickle=False),data[0]):raise ValueError('Existing product changed')
   return output
  temp=Path(tempfile.mkdtemp(prefix='.pending-tree-product-',dir=output.parent))
  try:
   shutil.copyfile(tif,temp/'source.tif');np.save(temp/'tree_cover.npy',data[0].astype(np.float32),allow_pickle=False)
   write(temp/'validation.json',v);write(temp/'checksums.json',{f.name:file_hash(f) for f in temp.iterdir()})
   sync_files(temp);sync_dir(temp);os.rename(temp,output);sync_dir(output.parent)
  finally:
   if temp.exists():shutil.rmtree(temp)
 return output

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--checkpoint',required=True);p.add_argument('--output',required=True);p.add_argument('--source-snapshot',required=True)
 print(prepare(**vars(p.parse_args())))
