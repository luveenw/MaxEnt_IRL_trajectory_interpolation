"""Independent direct EE weighted-sum corroboration of native GHSL zero findings."""
import ee,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/pantanal_covariates/globpop_ghsl_comparison_20261104';gaps=json.loads((ROOT/'data/pantanal_covariates/globpop_production_review_20261104/finite_gap_pixels.json').read_text());ee.Initialize(project='perceptive-ivy-780');ee.data.setDeadline(180000);out={}
for key,epoch in [('G057_2013',2010),('G057_2013',2015),('G286_2010',2010),('G316_2011',2010)]:
 im=ee.Image(f'JRC/GHSL/P2023A/GHS_POP/{epoch}').select('population_count');fs=[]
 for p in gaps[key]:
  w=-180+p['source_col']/120;n=90-p['source_row']/120;fs.append(ee.Feature(ee.Geometry.Rectangle([w,n-1/120,w+1/120,n],'EPSG:4326',False),{'source_col':p['source_col'],'source_row':p['source_row']}))
 raw=im.reduceRegions(collection=ee.FeatureCollection(fs),reducer=ee.Reducer.sum(),crs=im.projection(),maxPixelsPerRegion=1000).getInfo();out[f'{key}_epoch{epoch}']=raw;(OUT/'ee_zero_corroboration.json').write_text(json.dumps(out,indent=2)+'\n');print(key,epoch,max(f['properties']['sum']for f in raw['features']),flush=True)
