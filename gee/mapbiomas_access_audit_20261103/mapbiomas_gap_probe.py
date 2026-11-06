from pathlib import Path
REPO = next(p for p in Path(__file__).resolve().parents if (p/'jaguar_irl').is_dir() and (p/'data').is_dir())
DATA_ROOT = REPO/'data/pantanal_covariates/mapbiomas_access_audit_20261103'
SCRIPT_ROOT = REPO/'gee/mapbiomas_access_audit_20261103'
import ee,json
from pathlib import Path
ee.Initialize(project='perceptive-ivy-780')
r=json.loads((DATA_ROOT/'mapbiomas_coverage_probe.json').read_text())
assets={k:v['id'] for k,v in r['assets'].items()};years=r['inputs']['spring_years']
p=json.loads((REPO/'gee/spring_srtm_roughness_v1/jobs/plan.json').read_text());j=p['groups']['G115'];g=j['grid'];region=ee.Geometry.Rectangle(g['bounds'],g['crs'],False);target=ee.Projection(g['crs'],j['crs_transform']);proj=ee.Image(assets['brazil']).select(0).projection()
cover=[]
for y in years:
 v=[]
 for asset in assets.values():
  z=ee.Image(asset).select('classification_'+y)
  v.append(z.mask().gt(0).And(z.neq(0)).And(z.neq(27)).unmask(0,False).rename('valid'))
 u=ee.ImageCollection(v).max().setDefaultProjection(proj)
 cover.append(u.reduceResolution(ee.Reducer.mean(),bestEffort=False,maxPixels=1024).reproject(target).rename('year_'+y))
stack=ee.Image.cat(cover)
results={'group':'G115','grid_cells':j['output_cells'],'per_year':stack.reduceRegion(ee.Reducer.min().combine(ee.Reducer.mean(),sharedInputs=True),region,crs=g['crs'],crsTransform=j['crs_transform'],maxPixels=100000).getInfo()}
worst=stack.reduce(ee.Reducer.min()).rename('coverage')
results['incomplete_cells']=worst.addBands(ee.Image.pixelCoordinates(target)).updateMask(worst.lt(1-1e-6)).sample(region=region,projection=target,geometries=True).getInfo()
chaco='projects/mapbiomas-public/assets/chaco/lulc/collection5/mapbiomas_chaco_collection5_integration_v2'
try:
 z=ee.Image(chaco).select(['classification_'+y for y in years]);v=z.mask().gt(0).And(z.neq(0)).And(z.neq(27)).reduce(ee.Reducer.min()).unmask(0,False)
 coarse=v.reduceResolution(ee.Reducer.mean(),bestEffort=False,maxPixels=1024).reproject(target)
 results['chaco_G115_coverage']=coarse.reduceRegion(ee.Reducer.min().combine(ee.Reducer.mean(),sharedInputs=True),region,crs=g['crs'],crsTransform=j['crs_transform'],maxPixels=100000).getInfo()
except Exception as exc: results['chaco_error']=str(exc)
(DATA_ROOT/'mapbiomas_gap_probe.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
