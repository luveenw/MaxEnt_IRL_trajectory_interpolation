"""Primary GPW land/water diagnostics and adjacent-year NaN checks; no filling."""
from pathlib import Path
import json,numpy as np
import ee
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/pantanal_covariates/globpop_production_review_20261104'
ee.Initialize(project='perceptive-ivy-780');ee.data.setDeadline(180000)
gaps=json.loads((OUT/'finite_gap_pixels.json').read_text());unique={}
for key,ps in gaps.items():
 for p in ps:unique[(p['source_col'],p['source_row'])]=p
points=ee.FeatureCollection([ee.Feature(ee.Geometry.Point([p['longitude'],p['latitude']]),{'source_col':p['source_col'],'source_row':p['source_row']}) for p in unique.values()]);images=[];metadata={}
for suffix,band in [('Land_Area','land_area'),('Water_Area','water_area'),('Water_Mask','water_mask')]:
 im=ee.ImageCollection('CIESIN/GPWv411/GPW_'+suffix).first().select(band);metadata[suffix]=im.getInfo();images.append(im.unmask(-9999,False).rename(band))
im=images[0].addBands(images[1]).addBands(images[2]);r=im.sampleRegions(points,properties=['source_col','source_row'],projection=images[0].projection(),geometries=True).getInfo();(OUT/'gpw_gap_context.json').write_text(json.dumps({'metadata':metadata,'samples':r},indent=2)+'\n');print('gpw gap samples',len(r['features']),flush=True)
pilot=json.loads((ROOT/'data/pantanal_covariates/globpop_access_20261104/pilots.json').read_text())['G316_2011'];g=pilot['grid'];region=ee.Geometry.Rectangle(g['bounds'],g['crs'],False);res={}
for y in [2009,2010,2011,2012,2013]:
 im=ee.ImageCollection('projects/sat-io/open-datasets/GLOBPOP_DENSITY').filterDate(f'{y}-01-01',f'{y+1}-01-01').first().select('b1').toDouble();raw=im.sampleRectangle(region,defaultValue=-9999).getInfo()['properties']['b1'];a=np.array(raw,float);np.save(OUT/f'G316_{y}_adjacent.npy',a);res[str(y)]={'nonfinite_local_indices':np.argwhere(~np.isfinite(a)).tolist(),'gap_values':['NaN'if not np.isfinite(a[rr,cc])else float(a[rr,cc])for rr,cc in [(1,17),(8,21),(11,21)]]};print(y,res[str(y)],flush=True)
(OUT/'adjacent_year_finite_values.json').write_text(json.dumps(res,indent=2)+'\n')
