"""Read-only native-grid diagnosis; run from repository root with EE environment."""
import ee,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
prior=ROOT/'data/pantanal_covariates/mapbiomas_access_audit_20261103'
r=json.loads((prior/'mapbiomas_coverage_probe.json').read_text())
plan=json.loads((ROOT/'data/pantanal_covariates/spring_srtm_roughness_v1/jobs/plan.json').read_text());job=plan['groups']['G115'];g=job['grid']
ee.Initialize(project='perceptive-ivy-780')
assets={k:v['id'] for k,v in r['assets'].items()};images={k:ee.Image(v) for k,v in assets.items()}
proj=images['brazil'].select(0).projection();target=ee.Projection(g['crs'],job['crs_transform']);region=ee.Geometry.Rectangle(g['bounds'],g['crs'],False)
def union(seq):return ee.ImageCollection([i.rename('u') for i in seq]).max().setDefaultProjection(proj)
result={'assets':assets,'native_projections':{k:i.select(0).projection().getInfo() for k,i in images.items()},'stages':{}}
raw=[];nz=[];obs=[];bands=[]
for c,i in images.items():
 z=i.select('classification_2005')
 m=z.mask().gt(0).unmask(0,False)
 raw.append(m);nz.append(m.And(z.unmask(0,False).neq(0)));obs.append(m.And(z.unmask(0,False).neq(0)).And(z.unmask(0,False).neq(27)))
 bands.extend([z.unmask(-999,False).rename(c+'_class'),m.rename(c+'_mask')])
for name,v in [('raw_mask',union(raw)),('nonzero',union(nz)),('observed',union(obs))]:
 coarse=v.reduceResolution(ee.Reducer.mean(),maxPixels=1024).reproject(target)
 result['stages'][name]=coarse.reduceRegion(ee.Reducer.min().combine(ee.Reducer.mean(),sharedInputs=True),region,crs=g['crs'],crsTransform=job['crs_transform'],maxPixels=10000).getInfo()
print('Stages',result['stages'],flush=True)
bad=union(obs).eq(0)
chaco=ee.Image('projects/mapbiomas-public/assets/chaco/lulc/collection5/mapbiomas_chaco_collection5_integration_v2').select('classification_2005')
bands.extend([chaco.unmask(-999,False).rename('chaco_class')])
samples=ee.Image.cat(bands).addBands(ee.Image.pixelLonLat()).updateMask(bad).sample(region=region,projection=proj,geometries=False,tileScale=2,dropNulls=True)
result['native_gap_samples']=samples.getInfo()
result['native_gap_count']=samples.size().getInfo()
# Source coverage at gap only; values are all on common native grid.
result['gap_class_histograms']={c:ee.Image.cat(bands).select(c+'_class').updateMask(bad).reduceRegion(ee.Reducer.frequencyHistogram(),region,crs=proj,maxPixels=5000000).getInfo() for c in [*images,'chaco']}
(OUT/'diagnosis.json').write_text(json.dumps(result,indent=2))
print('Native gaps',result['native_gap_count'],'histograms',result['gap_class_histograms'],flush=True)
