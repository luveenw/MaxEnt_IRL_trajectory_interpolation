"""Read-only Chaco replacement coverage audit; no exports or source mutations.

Queries each annual validity separately, unmasking missing values to zero BEFORE
aggregation. Coverage is optimistic: any observed nonzero/non27 class counts,
without assuming a thematic crosswalk. Failures therefore rule out replacement.
"""
import hashlib,json,time
from pathlib import Path
import ee
import numpy as np
from jaguar_irl.training.mapbiomas_landcover import SOURCES

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/pantanal_covariates/mapbiomas_chaco_review_20261103'
PLAN=ROOT/'gee/spring_mapbiomas_landcover_v1/jobs/plan.json'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def main():
 ee.Initialize(project='perceptive-ivy-780'); ee.data.setDeadline(180000)
 plan=json.loads(PLAN.read_text());imgs={k:ee.Image(v)for k,v in SOURCES.items()};base=imgs['brazil'].select(0).projection()
 metadata={k:ee.data.getAsset(v)for k,v in SOURCES.items()}
 write(OUT/'asset_metadata.json',metadata)
 projections=ee.Dictionary({k:im.select(0).projection()for k,im in imgs.items()}).getInfo()
 write(OUT/'projections.json',projections)
 inputs={'project':'perceptive-ivy-780','sources':SOURCES,'plan_sha256':sha(PLAN),'script_sha256':sha(Path(__file__)),
         'class_validity':'mask>0 and code not 0 or 27; optimistic coverage before thematic crosswalk',
         'current_mosaic':'national union plus Chaco only class26, before G3162011 temporal repair',
         'queries':'interactive read-only computeValue; no export tasks; EECU unmeasured'}
 write(OUT/'inputs.json',inputs)
 allresults={}
 groupids=sorted({j['group_id']for j in plan['groups'].values()},key=lambda g:(g not in ('G115','G316'),g))
 for group in groupids:
  jobs=sorted([j for j in plan['groups'].values()if j['group_id']==group],key=lambda j:j['year']);job=jobs[0];g=job['grid']
  dest=OUT/(group+'_coverage.json')
  if dest.exists() and json.loads(dest.read_text()).get("complete"):
   allresults[group]=json.loads(dest.read_text())['summary'];print(group,'cached',flush=True);continue
  target=ee.Projection(g['crs'],job['crs_transform']);region=ee.Geometry.Rectangle(g['bounds'],g['crs'],False)
  summaries={};arrays={}
  for j in jobs:
   y=j['year'];classes={k:im.select(f'classification_{y}').reproject(base)for k,im in imgs.items()}
   valid={k:z.mask().gt(0).And(z.neq(0)).And(z.neq(27)).unmask(0,False).rename('valid').setDefaultProjection(base)for k,z in classes.items()}
   nat=valid['brazil'].max(valid['paraguay']).max(valid['bolivia'])
   current=nat.max(valid['chaco'].And(classes['chaco'].unmask(0,False).eq(26)))
   candidates={'chaco':valid['chaco'],'brazil_chaco':valid['brazil'].max(valid['chaco']),'national':nat,'current_before_temporal':current}
   names=list(candidates)
   bands=[im.toDouble().setDefaultProjection(base).reduceResolution(ee.Reducer.mean(),bestEffort=False,maxPixels=1024).reproject(target).rename(name)for name,im in candidates.items()]
   stack=ee.Image.pixelCoordinates(target).addBands(ee.Image.cat(bands))
   start=time.monotonic()
   response=stack.reduceRegion(ee.Reducer.toList(6),region,crs=g['crs'],crsTransform=j['crs_transform'],maxPixels=j["output_cells"]*6).getInfo()
   values=np.array(response['list'],dtype=float)
   assert values.shape==(j['output_cells'],6),values.shape
   xx,yy=values[:,:2].astype(int).T
   assert len(set(zip(xx,yy)))==j['output_cells'] and xx.min()==0 and yy.min()==0 and xx.max()==g['cols']-1 and yy.max()==g['rows']-1
   result={}
   for i,name in enumerate(names):
    a=np.zeros((g['rows'],g['cols']),dtype=np.float64);a[yy,xx]=values[:,i+2]
    assert np.isfinite(a).all() and a.min()>=-1e-9 and a.max()<=1+1e-9
    result[name]={'mean':float(a.mean()),'minimum':float(a.min()),'maximum':float(a.max()),'incomplete_cells':int((a<1-1e-6).sum()),'zero_cells':int((a<1e-9).sum()),'covered_projected_km2':float(a.sum()*.25),'missing_projected_km2':float((1-a).sum()*.25)}
    arrays[f'{y}_{name}']=a
   summaries[str(y)]=result
   np.savez_compressed(OUT/(group+'_coverage.npz'),**arrays)
   write(dest,{'grid':g,'years':[x['year']for x in jobs],'summary':summaries,'completed_years':list(summaries),'complete':len(summaries)==len(jobs)})
   print(group,y,'seconds',round(time.monotonic()-start,2),'chaco_mean',result['chaco']['mean'],'brazil_chaco_mean',result['brazil_chaco']['mean'],flush=True)
  allresults[group]=summaries
 write(OUT/'coverage_summary.json',allresults)
 # Requery exact problem locations using native Brazil pixel centers, one request.
 d=json.loads((ROOT/'data/pantanal_covariates/mapbiomas_gap_diagnosis_20261103/diagnosis.json').read_text())
 points=[ee.Feature(ee.Geometry.Point([f['properties']['longitude'],f['properties']['latitude']]),{'point_index':i,'group':'G115'})for i,f in enumerate(d['native_gap_samples']['features'])]
 points.append(ee.Feature(ee.Geometry.Point([-57.58843266634279,-17.83771184946872]),{'point_index':96,'group':'G316'}))
 bands=[]
 for y in (2005,2006,2010,2011,2012):
  for k,im in imgs.items():
   z=im.select(f'classification_{y}').reproject(base)
   bands.extend([z.unmask(-9999,False).rename(f'{k}_{y}_class'),z.mask().gt(0).unmask(0,False).rename(f'{k}_{y}_mask')])
 native=ee.Image.cat(bands).sampleRegions(ee.FeatureCollection(points),properties=['point_index','group'],projection=base,geometries=True).getInfo()
 assert len(native['features'])==97
 write(OUT/'exact_gap_pixels.json',native)
 print('COMPLETE',len(allresults),'groups',sum(map(len,allresults.values())),'groupyears;97gapcenters',flush=True)
if __name__=='__main__':main()
