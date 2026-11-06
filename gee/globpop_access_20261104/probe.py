"""Read-only GlobPOP pilot and metadata audit; no production exports."""
import json,hashlib,time
from pathlib import Path
import ee
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/pantanal_covariates/globpop_access_20261104'
def write(n,x):(OUT/n).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
ee.Initialize(project='perceptive-ivy-780');ee.data.setDeadline(180000)
sources={k:'projects/sat-io/open-datasets/GLOBPOP_'+k.upper() for k in ['density','count']}
metadata={};collections={}
for k,s in sources.items():
 c=ee.ImageCollection(s);collections[k]=c
 metadata[k]={'asset':ee.data.getAsset(s),'size':c.size().getInfo(),'indices':c.aggregate_array('system:index').getInfo(),'times':c.aggregate_array('system:time_start').getInfo(),'first_image':c.first().getInfo()}
write('metadata.json',metadata)
print({k:v['size'] for k,v in metadata.items()},flush=True)
planpath=ROOT/'gee/spring_mapbiomas_landcover_v1/jobs/plan.json'
plan=json.loads(planpath.read_text());pilots={}
for group,year in [('G115',2005),('G316',2011),('G312',2015)]:
 job=next(j for j in plan['groups'].values()if j['group_id']==group and j['year']==year);g=job['grid'];region=ee.Geometry.Rectangle(g['bounds'],g['crs'],False)
 result={'group':group,'year':year,'season_start':f'{year}-08-15','season_end_exclusive':f'{year}-11-15','grid':g,'crs_transform':job['crs_transform'],'source':{}}
 for kind,c in collections.items():
  season_filter_count=c.filterDate(result['season_start'],result['season_end_exclusive']).size().getInfo()
  selected=c.filterDate(f'{year}-01-01',f'{year+1}-01-01');im=ee.Image(selected.first()).rename(kind);proj=im.projection();info=im.getInfo()
  stats=im.reduceRegion(ee.Reducer.minMax().combine(ee.Reducer.mean(),sharedInputs=True).combine(ee.Reducer.count(),sharedInputs=True),region,crs=proj,maxPixels=100000).getInfo()
  mask=im.mask().gt(0).unmask(0,False)
  # Nearest assignment is ONLY a target-center mask diagnostic, never a density resampling recipe.
  maskstats=mask.reduceRegion(ee.Reducer.minMax().combine(ee.Reducer.sum(),sharedInputs=True),region,crs=g['crs'],crsTransform=job['crs_transform'],maxPixels=job['output_cells']*2).getInfo()
  result['source'][kind]={'annual_filtered_images':selected.size().getInfo(),'spring_date_filter_count':season_filter_count,'image':info,'native_statistics':stats,'target_center_validity_nearest_only':maskstats,'projection':proj.getInfo(),'nominal_scale_m':proj.nominalScale().getInfo()}
 pilots[f'{group}_{year}']=result;write('pilots.json',pilots);print(group,year,kind,stats,maskstats,flush=True)
write('inputs.json',{'status':'read-only pilot, not production extraction; no tasks or exports','project':'perceptive-ivy-780','sources':sources,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'plan_sha256':hashlib.sha256(planpath.read_bytes()).hexdigest(),'eecu':'interactive compute unmeasured','target_mask_method':'Nearest target centers diagnostic only; full overlap validity remains a production QA requirement.'})
