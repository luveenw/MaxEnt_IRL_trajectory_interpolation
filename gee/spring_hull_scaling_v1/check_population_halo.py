"""Check boundary-native pixels cannot exceed the attained hull maximum."""
from pathlib import Path
import ee
from jaguar_irl.training.shared_storage import read,write
from jaguar_irl.data.pantanal_checkpoint import file_hash
ROOT=Path(__file__).resolve().parents[2];out=ROOT/'data/pantanal_covariates/spring_hull_scaling_v1'
ee.Initialize(project='perceptive-ivy-780');ee.data.setDeadline(180000)
d=read(out/'domain.json');m=read(out/'maxima.json');region=ee.Geometry(d['geometry'],proj=d['crs'],geodesic=False).buffer(2000)
results={}
for year in m['population_years']:
    p=read(out/f'population_{year}.json');im=ee.Image(p['asset']).select('b1');im=im.updateMask(im.gte(0).And(im.lt(1e30)))
    maximum=im.reduceRegion(ee.Reducer.max(),region,crs=im.projection(),maxPixels=2000000,tileScale=4).getInfo()['b1']
    results[str(year)]=maximum
    print(year,maximum,flush=True)
if max(results.values())>m['population_upper']:raise ValueError('Boundary halo contains larger values: inspect exact hull candidate cells')
write(out/'population_boundary_check.json',dict(halo_m=2000,maxima=results,upper_bound=m['population_upper'],passed=True,
    proof='The 2km halo includes every ~1km native pixel intersecting hull; none exceeds the attained interior maximum',domain_sha256=file_hash(out/'domain.json'),software_sha256=file_hash(__file__)))
