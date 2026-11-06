"""Read-only independent raw-source comparison of the production native selector."""
from pathlib import Path
import json
import ee
from jaguar_irl.training.mapbiomas_landcover import SOURCES,SOURCE_IDS,native_mosaic,choose_pixel
from jaguar_irl.training.shared_storage import read,write
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT/'data/pantanal_covariates/spring_mapbiomas_landcover_v1'
plan=read(Path(__file__).resolve().parent/'jobs/plan.json');j=plan['groups']['G115_2005']
ee.Initialize(project='perceptive-ivy-780')
chosen,sid,valid,base=native_mosaic(ee,2005)
out=chosen.addBands(sid).addBands(valid).addBands(sid.multiply(1000).add(chosen).rename('source_class'))
for country,asset in SOURCES.items():out=out.addBands(ee.Image(asset).select('classification_2005').reproject(base).unmask(0,False).rename(country))
region=ee.Geometry.Rectangle(j['grid']['bounds'],j['grid']['crs'],False)
samples=out.stratifiedSample(numPoints=1,classBand='source_class',region=region,projection=base,seed=19,geometries=True,tileScale=2).getInfo()
for f in samples['features']:
    p=f['properties'];c,code,ok=choose_pixel({country:p[country] for country in SOURCES})
    assert p['selected_class']==code and p['source_id']==SOURCE_IDS[c] and bool(p['valid'])==ok,p
assert any(f['properties']['source_id']==4 and f['properties']['selected_class']==26 for f in samples['features'])
write(DATA/'native_priority_probe.json',dict(status='Production EE native selector matches independent raw-source scalar rule at every sampled source/class stratum',sample_count=len(samples['features']),group='G115',year=2005,features=samples['features']))
print('Verified',len(samples['features']),'source/class strata including Chaco water fallback')
