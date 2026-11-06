"""Read source identities and create only the requested Drive destination folders."""
from pathlib import Path
import json
import ee
from googleapiclient.discovery import build
from jaguar_irl.data.pantanal_checkpoint import digest
from jaguar_irl.training.mapbiomas_landcover import SOURCES
from jaguar_irl.training.shared_storage import write,read

repo=Path(__file__).resolve().parents[2]
root=repo/'data/pantanal_covariates/spring_mapbiomas_wooded_cover_v1';root.mkdir(parents=True,exist_ok=True)
ee.Initialize(project='perceptive-ivy-780')
assets={c:ee.data.getAsset(a) for c,a in SOURCES.items()}
projections={c:ee.Image(a).select('classification_2005').projection().getInfo() for c,a in SOURCES.items()}
snapshot=dict(schema='mapbiomas_source_snapshot/1',assets=assets,asset_fingerprint=digest(assets),projections=projections)
p=root/'source_snapshot.json'
if p.exists() and read(p)!=snapshot:raise ValueError('Source snapshot changed; investigate before replacing')
if not p.exists():write(p,snapshot)
drive=build('drive','v3',credentials=ee.data.get_persistent_credentials(),cache_discovery=False)
parent='root';chain=[]
for name in ['columbia_ma_thesis','jaguar_irl','seasonal_covariates','pantanal_spring_mapbiomas_wooded_cover_v1']:
    matches=drive.files().list(q=f"trashed=false and mimeType='application/vnd.google-apps.folder' and name='{name}' and '{parent}' in parents",fields='files(id,name,parents)',pageSize=100).execute()['files']
    if len(matches)>1:raise ValueError('Duplicate folder names')
    folder=matches[0] if matches else drive.files().create(body={'name':name,'mimeType':'application/vnd.google-apps.folder','parents':[parent]},fields='id,name,parents').execute()
    chain.append(folder);parent=folder['id']
allnamed=drive.files().list(q="trashed=false and mimeType='application/vnd.google-apps.folder' and name='pantanal_spring_mapbiomas_wooded_cover_v1'",fields='files(id)',pageSize=100).execute()['files']
if len(allnamed)!=1:raise ValueError('Leaf Drive name must be unique for EE exports')
config=dict(project='perceptive-ivy-780',drive_leaf_id=parent,drive_leaf_name=chain[-1]['name'],drive_folders=chain,drive_quota=drive.about().get(fields='storageQuota').execute()['storageQuota'],earth_engine_config=ee.data.getProjectConfig())
write(root/'cloud_setup.json',config)
print(json.dumps({'source_fingerprint':snapshot['asset_fingerprint'],'drive_folder_id':parent,'project':config['project']},indent=2))
