"""Categorical land-cover evidence over exact native GlobPOP gap footprints."""
import json
from pathlib import Path
import ee
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/pantanal_covariates/globpop_production_review_20261104';ee.Initialize(project='perceptive-ivy-780');ee.data.setDeadline(180000)
gaps=json.loads((OUT/'finite_gap_pixels.json').read_text());im=ee.Image('projects/mapbiomas-public/assets/brazil/lulc/collection11/mapbiomas_brazil_collection11_coverage_v3');out={}
for key in ['G316_2011','G057_2013','G286_2010']:
 yr=int(key.split('_')[1]);features=[]
 for p in gaps[key]:
  c=p['source_col'];r=p['source_row'];x0=-180+c/120;y1=90-r/120;geom=ee.Geometry.Rectangle([x0,y1-1/120,x0+1/120,y1],ee.Projection('EPSG:4326'),False)
  features.append(ee.Feature(geom,{'source_col':c,'source_row':r}))
 lc=im.select(f'classification_{yr}');image=lc.eq(33).rename('water33').addBands(lc.eq(11).rename('wetland11')).addBands(lc.eq(3).Or(lc.eq(4)).rename('forest_savanna34')).addBands(lc.mask().rename('valid'))
 result=image.reduceRegions(collection=ee.FeatureCollection(features),reducer=ee.Reducer.mean(),crs=lc.projection(),tileScale=2,maxPixelsPerRegion=10000).getInfo();out[key]=result;(OUT/'mapbiomas_gap_footprints.json').write_text(json.dumps(out,indent=2)+'\n');print(key,len(result['features']),flush=True)
