"""Bounded read-only histograms only where Chaco overlaps our Spring domains."""
from pathlib import Path
import ee,json,hashlib
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/pantanal_covariates/mapbiomas_chaco_review_20261103'
ee.Initialize(project='perceptive-ivy-780');ee.data.setDeadline(180000)
p=json.loads((ROOT/'gee/spring_mapbiomas_landcover_v1/jobs/plan.json').read_text());asset=p['recipe']['sources']['chaco'];im=ee.Image(asset);queries={}
for key in ['G115_2005','G115_2006','G203_2010']:
 j=p['groups'][key];g=j['grid'];region=ee.Geometry.Rectangle(g['bounds'],g['crs'],False);z=im.select(f"classification_{j['year']}");proj=z.projection()
 queries[key]=z.updateMask(z.neq(0).And(z.neq(27))).reduceRegion(ee.Reducer.frequencyHistogram(),region,crs=proj,maxPixels=5000000)
result=ee.Dictionary(queries).getInfo();(OUT/'chaco_observed_classes.json').write_text(json.dumps({'source':asset,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'counts_are_weighted_native_pixel_equivalents':True,'histograms':result},indent=2)+'\n');print(json.dumps(result,indent=2))
