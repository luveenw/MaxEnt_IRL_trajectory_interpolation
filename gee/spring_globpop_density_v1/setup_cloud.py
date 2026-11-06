"""Pin sources, approval and candidate grids; create the approved Drive destination."""
from pathlib import Path
import json,copy
import ee
from googleapiclient.discovery import build
from jaguar_irl.data.pantanal_checkpoint import digest,file_hash
from jaguar_irl.training.shared_storage import read,write
from jaguar_irl.training.globpop_density import DENSITY,LANDSCAN,RECIPE
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;DATA=ROOT/'data/pantanal_covariates/spring_globpop_density_v1';BUNDLE=HERE/'jobs'
DATA.mkdir(exist_ok=True);BUNDLE.mkdir(exist_ok=True)
ee.Initialize(project='perceptive-ivy-780')
base=read(ROOT/'gee/spring_mapbiomas_landcover_v1/jobs/plan.json');approval=read(ROOT/'data/pantanal_covariates/globpop_landscan_fallback_decision_20261104.json');gaps=read(ROOT/approval['allowed_footprints'])
if file_hash(ROOT/approval['allowed_footprints'])!=approval['allowed_footprints_sha256']:raise ValueError('Approval footprint hash mismatch')
years=sorted({j['year'] for j in base['groups'].values()});assets={};projections={}
for year in years:
 im=ee.ImageCollection(DENSITY).filterDate(f'{year}-01-01',f'{year+1}-01-01')
 if im.size().getInfo()!=1:raise ValueError('Expected one annual density image')
 ident=ee.Image(im.first()).get('system:id').getInfo();assets[ident]=ee.data.getAsset(ident);projections[ident]=ee.Image(ident).projection().getInfo()
for year in sorted({int(k.split('_')[1])for k in gaps}):
 ident=f'{LANDSCAN}/landscan-global-{year}';assets[ident]=ee.data.getAsset(ident);projections[ident]=ee.Image(ident).projection().getInfo()
zenodo=json.loads((ROOT/'data/pantanal_covariates/globpop_production_review_20261104/zenodo_latest.txt').read_text());files={f['key']:f['checksum']for f in zenodo['files']if f['key'].startswith('GlobPOP_Density_')and int(f['key'].split('_')[3])in years}
snapshot=dict(schema='globpop_landscan_source_snapshot/1',assets=assets,projections=projections,asset_fingerprint=digest(assets),
 official_reference=dict(record='https://zenodo.org/records/11179644',doi='10.5281/zenodo.11179644',metadata_version=zenodo['metadata']['version'],files=files,scope='Official archive reference; only G3162011 bounded440pixel window previously compared exactly, not global equivalence'))
for name,obj in [('source_snapshot.json',snapshot),('approval.json',approval),('approved_gap_footprints.json',gaps)]:
 p=BUNDLE/name
 if p.exists()and read(p)!=obj:raise ValueError('Frozen input differs: '+name)
 if not p.exists():write(p,obj)
prior={}
for directory in ['spring_srtm_roughness_v1','spring_mapbiomas_landcover_v1','spring_esa_shrubland_v1','spring_mapbiomas_wooded_cover_v1']:
 for p in (ROOT/'data/pantanal_covariates'/directory/'products').rglob('*'):
  if p.is_file():prior[str(p.relative_to(ROOT))]=file_hash(p)
p=DATA/'prior_product_hashes.json'
if p.exists()and read(p)!=prior:raise ValueError('Existing product archive changed')
if not p.exists():write(p,prior)
jobs={}
for key,j in base['groups'].items():
 j=copy.deepcopy(j);j['product_key']=digest(dict(grid=j['grid'],year=j['year'],recipe=RECIPE,source=snapshot['asset_fingerprint'],approval=digest(approval)))
 j['export_prefix']=f'SPR-C01_{key}_population_{j["product_key"][:12]}';j['approved_missing_pixels']=[[p['source_col'],p['source_row']]for p in gaps.get(key,[])];j['density_asset']=next(a for a in assets if a.startswith(DENSITY+'/')and f'_{j["year"]}_'in a)
 j['landscan_asset']=f'{LANDSCAN}/landscan-global-{j["year"]}'if key in gaps else None;jobs[key]=j
plan=dict(schema='pantanal_globpop_density_candidate_plan/1',recipe=RECIPE,groups=jobs,job_count=len(jobs),group_count=len({j['group_id']for j in jobs.values()}),default_pilot_job='G057_2013',
 source_snapshot=snapshot,approval_sha256=file_hash(BUNDLE/'approval.json'),gaps_sha256=file_hash(BUNDLE/'approved_gap_footprints.json'),software_sha256=file_hash(ROOT/'jaguar_irl/training/globpop_density.py'),
 source_plan_sha256=file_hash(ROOT/'gee/spring_mapbiomas_landcover_v1/jobs/plan.json'),epoch_role='all candidate years; split independent',checkpoint=base['checkpoint'])
p=BUNDLE/'plan.json'
if p.exists()and read(p)!=plan:raise ValueError('Frozen plan differs')
if not p.exists():write(p,plan)
drive=build('drive','v3',credentials=ee.data.get_persistent_credentials(),cache_discovery=False);parent='17WLeDACa4h01TSs42w00AYsiJGa_AfwK';name='pantanal_spring_globpop_density_v1'
matches=drive.files().list(q=f"trashed=false and mimeType='application/vnd.google-apps.folder' and name='{name}' and '{parent}' in parents",fields='files(id,name,parents)',pageSize=100).execute()['files']
if len(matches)>1:raise ValueError('Duplicate Drive folder')
folder=matches[0]if matches else drive.files().create(body={'name':name,'mimeType':'application/vnd.google-apps.folder','parents':[parent]},fields='id,name,parents').execute()
write(DATA/'cloud_setup.json',dict(project='perceptive-ivy-780',drive_leaf_id=folder['id'],drive_leaf_name=name,drive_parent=parent))
print(json.dumps({'source_fingerprint':snapshot['asset_fingerprint'],'drive_folder_id':folder['id'],'jobs':len(jobs),'prior_files':len(prior)},indent=2))
