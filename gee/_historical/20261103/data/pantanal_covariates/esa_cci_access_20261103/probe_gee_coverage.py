import json,ee,requests,hashlib
from pathlib import Path
r=Path(__file__).resolve().parent;repo=r.parents[2]
ee.Initialize(project='perceptive-ivy-780')
asset='users/geflanddegradation/toolbox_datasets/lcov_esacc_1992_2022'
z=ee.Image(asset).select('y2005');valid=z.mask().gt(0).And(z.neq(0)).And(z.neq(9999)).unmask(0,False).rename('coverage')
shrub=z.eq(120).Or(z.eq(121)).Or(z.eq(122)).updateMask(valid).unmask(0,False).rename('shrub_fraction')
p=json.loads((repo/'data/pantanal_covariates/spring_srtm_roughness_v1/jobs/plan.json').read_text())
result={'asset':asset,'pilot_year':2005,'required_spring_bands':['y'+str(y) for y in (2005,2006,2008,2009,2010,2011,2012,2013,2014,2015)],'available_bands':ee.Image(asset).bandNames().getInfo(),'groups':{}}
for group,j in p['groups'].items():
 g=j['grid'];region=ee.Geometry.Rectangle(g['bounds'],g['crs'],False)
 coarse=valid.addBands(shrub).toFloat().reduceResolution(ee.Reducer.mean(),bestEffort=False,maxPixels=64).reproject(crs=g['crs'],crsTransform=j['crs_transform'])
 result['groups'][group]=coarse.reduceRegion(ee.Reducer.min().combine(ee.Reducer.mean(),sharedInputs=True).combine(ee.Reducer.max(),sharedInputs=True),region,crs=g['crs'],crsTransform=j['crs_transform'],maxPixels=j['output_cells']*2).getInfo()
 (r/'gee_coverage.json').write_text(json.dumps(result,indent=2));print(group,result['groups'][group],flush=True)
u='https://api.github.com/repos/ConservationInternational/trends.earth/commits'
resp=requests.get(u,params={'path':'LDMP/data/gee_datasets.jsonc','per_page':1},timeout=30);resp.raise_for_status();commit=resp.json()[0]['sha']
f=r/'trends_LDMP_data_gee_datasets.jsonc';raw=requests.get(f'https://raw.githubusercontent.com/ConservationInternational/trends.earth/{commit}/LDMP/data/gee_datasets.jsonc',timeout=30);raw.raise_for_status();f.write_bytes(raw.content)
(r/'mirror_provenance.json').write_text(json.dumps(dict(repository='ConservationInternational/trends.earth',commit=commit,path='LDMP/data/gee_datasets.jsonc',raw_url=raw.url,sha256=hashlib.sha256(raw.content).hexdigest(),caveat='Config includes stale description/sourcecitation; pilot fidelity independently checked againstofficial CEDA v2.0.7'),indent=2))
