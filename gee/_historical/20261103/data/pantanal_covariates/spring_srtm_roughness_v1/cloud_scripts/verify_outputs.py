"""Verify the completed pinned run offline; never submits cloud work."""
import hashlib
import json
from pathlib import Path
import numpy as np
from jaguar_irl.data.pantanal_checkpoint import file_hash
from jaguar_irl.training.terrain_roughness import verify_bundle
from jaguar_irl.training.shared_storage import read,write

root=Path(__file__).resolve().parent.parent
plan=verify_bundle(root/'jobs'); run=read(root/'acquisition.json')
assert set(run['groups'])==set(plan['groups'])
assert file_hash(Path(plan['checkpoint'])/'checkpoint.json')==plan['checkpoint_sha256']
assert file_hash(Path(plan['checkpoint'])/'grids.json')==plan['grids_sha256']
report={'schema':'spring_terrain_inventory_verification/1','groups':{},
        'plan_sha256':file_hash(root/'jobs/plan.json'),
        'acquisition_driver_sha256':file_hash(root/'cloud_scripts/acquire_run.py')}
for group,job in plan['groups'].items():
    product=root/'products'/group
    validation=read(product/'validation.json')
    for name,expected in read(product/'checksums.json').items():
        assert Path(name).name==name
        assert file_hash(product/name)==expected
    arr=np.load(product/'roughness.npy',allow_pickle=False)
    assert arr.shape==(job['grid']['rows'],job['grid']['cols'])
    assert arr.dtype==np.float32 and np.isfinite(arr).all() and (arr>=0).all()
    assert validation['product_key']==job['product_key']
    assert validation['plan_sha256']==report['plan_sha256']
    ledger=read(root/'tasks'/f'{group}.json')
    assert ledger['status']=='COMPLETED'
    assert ledger['product_key']==job['product_key']
    tif=root/'downloads'/(job['export_prefix']+'.tif')
    remote=read(tif.with_name(tif.name+'.drive.json'))
    assert read(root/'cloud_setup.json')['drive_leaf_id'] in remote['parents']
    assert hashlib.md5(tif.read_bytes()).hexdigest()==remote['md5Checksum']
    assert file_hash(tif)==validation['source_tif_sha256']
    report['groups'][group]={'shape':list(arr.shape),'npy_sha256':file_hash(product/'roughness.npy'),
                            'drive_file_id':remote['id'],'task_id':ledger['task_id']}
report.update(group_count=len(report['groups']),output_cells=sum(j['output_cells'] for j in plan['groups'].values()),
              downloaded_tiff_bytes=sum(p.stat().st_size for p in (root/'downloads').glob('*.tif')),
              batch_eecu_usage_seconds=run['batch_eecu_usage_seconds'],
              status='all input identities, output checksums, groups, shapes and Drive destinations verified',
              scientific_validation='not established by these software checks')
write(root/'verification.json',report)
print(json.dumps({k:v for k,v in report.items() if k!='groups'},indent=2))
