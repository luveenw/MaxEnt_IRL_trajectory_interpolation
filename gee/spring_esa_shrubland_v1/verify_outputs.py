"""Offline complete-cache inventory verification; never submits cloud work."""
from pathlib import Path
import hashlib
import json
import numpy as np
from jaguar_irl.data.pantanal_checkpoint import file_hash
from jaguar_irl.training.shared_storage import read,write
from jaguar_irl.training.terrain_roughness import verify_bundle
ROOT=Path(__file__).resolve().parents[2];BUNDLE=Path(__file__).resolve().parent/'jobs'
DATA=ROOT/'data/pantanal_covariates/spring_esa_shrubland_v1'
p=verify_bundle(BUNDLE);a=read(DATA/'acquisition.json');config=read(DATA/'cloud_setup.json')
assert set(a['groups'])==set(p['groups'])
assert file_hash(Path(p['checkpoint'])/'checkpoint.json')==p['checkpoint_sha256']
assert file_hash(Path(p['checkpoint'])/'grids.json')==p['grids_sha256']
result={}
for key,j in p['groups'].items():
    product=DATA/'products'/j['group_id']/str(j['year'])
    for name,sha in read(product/'checksums.json').items():
        assert Path(name).name==name and file_hash(product/name)==sha
    v=read(product/'validation.json');arr=np.load(product/'shrubland_fraction.npy',allow_pickle=False)
    assert arr.shape==(j['grid']['rows'],j['grid']['cols']) and arr.dtype==np.float32
    assert np.isfinite(arr).all() and (arr>=0).all() and (arr<=1).all()
    assert v['product_key']==j['product_key'] and v['year']==j['year']
    assert v['source_snapshot']==p['source_snapshot']
    t=read(DATA/'tasks'/f'{key}.json');assert t['status']=='COMPLETED' and t['product_key']==j['product_key']
    tif=DATA/'downloads'/(j['export_prefix']+'.tif');d=read(tif.with_name(tif.name+'.drive.json'))
    assert config['drive_leaf']['id'] in d['parents']
    assert hashlib.md5(tif.read_bytes()).hexdigest()==d['md5Checksum']
    assert file_hash(tif)==v['source_tif_sha256']
    identity=dict(group_id=j['group_id'],year=j['year'],shape=list(arr.shape),npy_sha256=file_hash(product/'shrubland_fraction.npy'),drive_file_id=d['id'])
    if t.get('acquisition_kind')=='gee_direct_download':
        assert 'task_id' not in t and t['online_eecu_usage_seconds'] is None
        assert t['request_graph_sha256'] and t['request_parameters']['dimensions']==[j['grid']['cols'],j['grid']['rows']]
        assert t['drive_file']['id']==d['id'] and t['download_sha256']==file_hash(tif)
        identity.update(acquisition_kind='gee_direct_download',request_graph_sha256=t['request_graph_sha256'])
    else:identity.update(acquisition_kind='gee_batch_export',task_id=t['task_id'])
    result[key]=identity
report=dict(schema='verified_shrubland_candidate_cache/1',jobs=result,job_count=len(result),group_count=p['group_count'],
            output_cells=p['total_output_cells'],batch_eecu_usage_seconds=a['batch_eecu_usage_seconds'],direct_job_count=a['direct_job_count'],online_eecu_usage_measured=False,
            plan_sha256=file_hash(BUNDLE/'plan.json'),source_fingerprint=p['source_snapshot']['asset_fingerprint'],
            epoch_role='Candidate-year cache; no training representative years selected',
            status='All pinned inputs, classes, complete grids, numerical bounds, checksums and Drive identities verified',
            scientific_validation='not established')
write(DATA/'verification.json',report)
print(json.dumps({k:v for k,v in report.items() if k!='jobs'},indent=2))
