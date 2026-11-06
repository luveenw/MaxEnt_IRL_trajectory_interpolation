"""Pin the live source and create only this run's Drive leaf folder."""
from pathlib import Path
raise RuntimeError('Superseded Hansen draft: user selected annual MapBiomas wooded-class proxy; do not execute')

import ee
from googleapiclient.discovery import build
from jaguar_irl.data.pantanal_checkpoint import digest
from jaguar_irl.training.shared_storage import write,read
from jaguar_irl.training.tree_cover import SOURCE
ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/pantanal_covariates/spring_hansen_tree_cover_v1'
ee.Initialize(project='perceptive-ivy-780')
metadata=ee.data.getAsset(SOURCE)
snapshot=dict(asset_id=SOURCE,asset_metadata=metadata,asset_fingerprint=digest(metadata),
              bands=ee.Image(SOURCE).bandNames().getInfo(),projection=ee.Image(SOURCE).select('treecover2000').projection().getInfo(),
              source_epoch=2000, validation_limit='Native canopy/land-water validity checked on each complete target grid; ecological accuracy unvalidated')
p=DATA/'source_snapshot.json'
if p.exists():
 if read(p)!=snapshot:raise ValueError('Live source snapshot changed; investigate')
else:write(p,snapshot)
drive=build('drive','v3',credentials=ee.data.get_persistent_credentials(),cache_discovery=False)
parent='17WLeDACa4h01TSs42w00AYsiJGa_AfwK';name='pantanal_spring_hansen_tree_cover_v1'
q=f"trashed=false and mimeType='application/vnd.google-apps.folder' and name='{name}' and '{parent}' in parents"
found=drive.files().list(q=q,fields='files(id,name,parents)').execute()['files']
if len(found)>1:raise ValueError('Duplicate Drive leaf')
item=found[0] if found else drive.files().create(body={'name':name,'mimeType':'application/vnd.google-apps.folder','parents':[parent]},fields='id,name,parents').execute()
write(DATA/'cloud_setup.json',dict(project='perceptive-ivy-780',drive_leaf=item,drive_path='columbia_ma_thesis/jaguar_irl/seasonal_covariates/'+name,drive_quota=drive.about().get(fields='storageQuota').execute()))
print('Pinned source fingerprint',snapshot['asset_fingerprint'],'Drive folder',item['id'])
