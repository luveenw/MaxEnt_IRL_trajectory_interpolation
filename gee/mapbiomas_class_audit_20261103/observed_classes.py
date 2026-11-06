"""Read-only histogram audit of all required Spring years and grids."""
from pathlib import Path
REPO = next(p for p in Path(__file__).resolve().parents if (p/'jaguar_irl').is_dir() and (p/'data').is_dir())
DATA_ROOT = REPO/'data/pantanal_covariates/mapbiomas_class_audit_20261103'
SCRIPT_ROOT = REPO/'gee/mapbiomas_class_audit_20261103'
import ee,json
from pathlib import Path
root=REPO
out=DATA_ROOT
metadata=json.loads((root/'data/pantanal_covariates/mapbiomas_access_audit_20261103/asset_metadata.json').read_text())
plan=json.loads((root/'gee/spring_srtm_roughness_v1/jobs/plan.json').read_text())
years=[2005,2006,2008,2009,2010,2011,2012,2013,2014,2015]
ee.Initialize(project='perceptive-ivy-780')
regions=[ee.Feature(ee.Geometry.Rectangle(j['grid']['bounds'],j['grid']['crs'],False)) for j in plan['groups'].values()]
region=ee.FeatureCollection(regions).geometry()
images={};report={'years':years,'country_priority':['brazil','paraguay','bolivia'],'results':{}}
for country in ('brazil','paraguay','bolivia'):
 img=ee.Image(metadata[country]['id']).select(['classification_'+str(y) for y in years])
 images[country]=img.updateMask(img.neq(0).And(img.neq(27)))
proj=images['brazil'].select(0).projection()
images['priority_mosaic']=ee.ImageCollection([images['bolivia'],images['paraguay'],images['brazil']]).mosaic().setDefaultProjection(proj)
for country,img in images.items():
 hist=img.reduceRegion(ee.Reducer.frequencyHistogram(),geometry=region,crs=proj,maxPixels=100000000,tileScale=4).getInfo()
 codes=sorted({int(code) for band in hist.values() if band for code in band})
 report['results'][country]={'observed_codes':codes,'histograms':hist}
 (out/'observed_classes.json').write_text(json.dumps(report,indent=2)+'\n')
 print(country,codes,flush=True)
