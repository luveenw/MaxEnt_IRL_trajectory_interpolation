"""Read-only public-source availability and class-presence probe; run from repo root."""
from pathlib import Path
import json
import ee
ROOT=Path(__file__).resolve().parent
plan=json.loads(Path('data/pantanal_covariates/spring_srtm_roughness_v1/jobs/plan.json').read_text())
ee.Initialize(project='perceptive-ivy-780')
regions=[ee.Geometry.Rectangle(j['grid']['bounds'],j['grid']['crs'],False) for j in plan['groups'].values()]
region=ee.FeatureCollection([ee.Feature(g) for g in regions]).geometry()
years=[2005,2006,2008,2009,2010,2011,2012,2013,2014,2015]
report={'scope':'union of13Springrectangles; no source selected or export','sources':{}}
for asset in ['MODIS/061/MCD12Q1','ESA/WorldCover/v100','ESA/WorldCover/v200','projects/sat-io/open-datasets/GLC-FCS30D/annual','ESA/CCI/LC']:
 try:
  meta=ee.data.getAsset(asset)
  entry={'asset':asset,'type':meta['type']}
  col=ee.ImageCollection(asset).filterBounds(region)
  entry['size']=col.size().getInfo()
  first=ee.Image(col.first())
  entry['first']=first.getInfo()
  if 'MODIS' in asset:
   entry['available_years']=col.aggregate_array('system:time_start').getInfo()
   entry['histograms']={}
   for y in years:
    z=ee.Image(col.filterDate(f'{y}-01-01',f'{y+1}-01-01').first()).select('LC_Type1')
    entry['histograms'][str(y)]=z.reduceRegion(ee.Reducer.frequencyHistogram(),region,scale=500,maxPixels=1000000).getInfo()
  elif 'GLC-FCS' in asset:
   entry['histograms']={}
   for y in years:
    z=col.mosaic().select('b'+str(y-1999))
    entry['histograms'][str(y)]=z.reduceRegion(ee.Reducer.frequencyHistogram(),region,scale=30,maxPixels=100000000).getInfo()
  report['sources'][asset]=entry
 except Exception as exc:
  report['sources'][asset]={'asset':asset,'error':str(exc)}
 (ROOT/'probe.json').write_text(json.dumps(report,indent=2))
 print(asset, {k:v for k,v in report['sources'][asset].items() if k not in ('first','histograms','available_years')},flush=True)
