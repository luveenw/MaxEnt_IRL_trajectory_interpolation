"""Read-only annual WorldPop coverage over audited native GlobPOP gaps; no fills."""
import json,hashlib
from pathlib import Path
import ee
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/pantanal_covariates/globpop_component_audit_20261104'
ee.Initialize(project='perceptive-ivy-780');ee.data.setDeadline(180000)
gaps=json.loads((ROOT/'data/pantanal_covariates/globpop_production_review_20261104/finite_gap_pixels.json').read_text());results={}
collection=ee.ImageCollection('WorldPop/GP/100m/pop')
for key in ['G057_2013','G057_2014','G057_2015','G286_2010','G316_2011']:
 year=int(key.split('_')[1]);ims=[];meta=[]
 for country in ['BOL','PRY','BRA']:
  subset=collection.filter(ee.Filter.eq('year',year)).filter(ee.Filter.eq('country',country))
  ids=subset.aggregate_array('system:id').getInfo();meta.append({'country':country,'ids':ids})
  if ids:ims.append(subset.mosaic().select('population'))
 if not ims:results[key]={'error':'No country/year images','source_images':meta};continue
 im=ee.ImageCollection.fromImages(ims).mosaic().rename('population_count_per_native_pixel');projection=ee.Image(collection.filter(ee.Filter.eq('year',year)).filter(ee.Filter.eq('country','BRA')).first()).select('population').projection()
 feats=[]
 for p in gaps[key]:
  col,row=p['source_col'],p['source_row'];x=-180+col/120;y=90-row/120
  feats.append(ee.Feature(ee.Geometry.Rectangle([x,y-1/120,x+1/120,y],'EPSG:4326',False),{'source_col':col,'source_row':row}))
 # Range predicate excludes NaN/Inf/negative values; preserve unknown as0 only
 # in this QA coverage indicator, never in the actual population surface.
 finite=im.gte(0).And(im.lt(1e20)).unmask(0,False).rename('finite_nonnegative_coverage')
 diagnostic=finite.addBands(im.rename('raw_count'))
 reducer=ee.Reducer.mean().combine(ee.Reducer.minMax(),sharedInputs=True)
 raw=diagnostic.reduceRegions(ee.FeatureCollection(feats),reducer,crs=projection,scale=projection.nominalScale(),tileScale=2,maxPixelsPerRegion=20000).getInfo()
 props=[r['properties'] for r in raw['features']];cover=[p['finite_nonnegative_coverage_mean'] for p in props]
 results[key]={'source_images':meta,'projection':projection.getInfo(),'native_gap_footprints':len(props),'complete_finite_footprints':sum(v>=1-1e-6 for v in cover),'zero_finite_footprints':sum(v==0 for v in cover),'minimum_finite_fraction':min(cover),'maximum_finite_fraction':max(cover),'footprints':props,'semantics':'Native count means are diagnostic people/native100m pixel, NOTdensity. Coverage is EE overlap-weighted native-pixel predicate mean; not final exact500m integration.'}
 (OUT/'worldpop_gap_coverage.json').write_text(json.dumps(results,indent=2)+'\n')
 print(key,{k:results[key][k] for k in ['native_gap_footprints','complete_finite_footprints','zero_finite_footprints','minimum_finite_fraction']},flush=True)
(OUT/'worldpop_provenance.json').write_text(json.dumps({'project':'perceptive-ivy-780','script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'read-only coverage; no imputation or production','asset':'WorldPop/GP/100m/pop'},indent=2)+'\n')
