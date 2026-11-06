"""Probe nearest GPW epoch at missing native centers, without filling."""
import json
from pathlib import Path
import ee
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/pantanal_covariates/globpop_production_review_20261104';ee.Initialize(project='perceptive-ivy-780');ee.data.setDeadline(180000);gaps=json.loads((OUT/'finite_gap_pixels.json').read_text());out={}
for key,epoch in [('G316_2011',2010),('G057_2013',2015),('G286_2010',2010)]:
 im=ee.ImageCollection('CIESIN/GPWv411/GPW_Population_Density').filterDate(f'{epoch}-01-01',f'{epoch+1}-01-01').first().select('population_density');ps=ee.FeatureCollection([ee.Feature(ee.Geometry.Point([p['longitude'],p['latitude']]),{'source_col':p['source_col'],'source_row':p['source_row']})for p in gaps[key]])
 result=im.unmask(-9999,False).sampleRegions(ps,properties=['source_col','source_row'],projection=im.projection(),geometries=True).getInfo();out[key]={'epoch':epoch,'samples':result};(OUT/'gpw_fallback_probe.json').write_text(json.dumps(out,indent=2)+'\n');print(key,len(result['features']),flush=True)
