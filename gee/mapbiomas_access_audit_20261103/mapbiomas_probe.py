from pathlib import Path
REPO = next(p for p in Path(__file__).resolve().parents if (p/'jaguar_irl').is_dir() and (p/'data').is_dir())
DATA_ROOT = REPO/'data/pantanal_covariates/mapbiomas_access_audit_20261103'
SCRIPT_ROOT = REPO/'gee/mapbiomas_access_audit_20261103'
import ee,json
from pathlib import Path
from datetime import datetime,timezone
ee.Initialize(project='perceptive-ivy-780')
assets={
 'brazil':'projects/mapbiomas-public/assets/brazil/lulc/collection11/mapbiomas_brazil_collection11_coverage_v3',
 'bolivia':'projects/mapbiomas-public/assets/bolivia/lulc/collection4/mapbiomas_bolivia_collection4_coverage_v1',
 'paraguay':'projects/mapbiomas-public/assets/paraguay/lulc/collection3/mapbiomas_paraguay_collection3_coverage_v1'}
inputs=json.loads((DATA_ROOT/'mapbiomas_coverage_inputs.json').read_text())
years=inputs['spring_years']
report={'checked_utc':datetime.now(timezone.utc).isoformat(),'inputs':inputs,'assets':{},'grid_probes':{}}
valid=[]
for country,asset in assets.items():
 try:
  img=ee.Image(asset); names=img.bandNames().getInfo()
  missing=['classification_'+y for y in years if 'classification_'+y not in names]
  report['assets'][country]={'id':asset,'band_count':len(names),'first_band':names[0],'last_band':names[-1],'missing_spring_bands':missing}
  print(country,report['assets'][country],flush=True)
  if missing: raise ValueError('Missing required band')
  chosen=img.select(['classification_'+y for y in years])
  v=chosen.mask().gt(0).And(chosen.neq(0)).And(chosen.neq(27)).reduce(ee.Reducer.min()).unmask(0,False).rename(country)
  valid.append(v)
 except Exception as exc:
  report['assets'][country]={'id':asset,'error':str(exc)}
  print(country,str(exc),flush=True)
(DATA_ROOT/'mapbiomas_probe_metadata.json').write_text(json.dumps(report,indent=2))
if len(valid)!=3: raise RuntimeError('Resolve inaccessible asset before probing')
# Set projection explicitly after combining sources; the countries use Landsat angular grids.
union=ee.ImageCollection([v.rename('valid') for v in valid]).max().setDefaultProjection(ee.Image(assets['brazil']).select(0).projection()).rename('union')
plan=json.loads((REPO/'gee/spring_srtm_roughness_v1/jobs/plan.json').read_text())
for group,job in plan['groups'].items():
 grid=job['grid']; region=ee.Geometry.Rectangle(grid['bounds'],grid['crs'],False)
 stats={}
 for country,v in list(zip(assets,valid))+[('union',union)]:
  coarse=v.toFloat().reduceResolution(ee.Reducer.mean(),bestEffort=False,maxPixels=1024).reproject(crs=grid['crs'],crsTransform=job['crs_transform'])
  stats[country]=coarse.reduceRegion(ee.Reducer.min().combine(ee.Reducer.mean(),sharedInputs=True),geometry=region,crs=grid['crs'],crsTransform=job['crs_transform'],maxPixels=job['output_cells']*2)
 report['grid_probes'][group]=ee.Dictionary(stats).getInfo()
 (DATA_ROOT/'mapbiomas_coverage_probe.json').write_text(json.dumps(report,indent=2))
 print(group,report['grid_probes'][group],flush=True)
