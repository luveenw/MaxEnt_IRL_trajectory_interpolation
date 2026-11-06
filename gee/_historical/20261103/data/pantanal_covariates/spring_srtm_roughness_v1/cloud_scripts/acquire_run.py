"""Resume this pinned Spring terrain run, one export at a time; no auto resubmission."""
import json
from pathlib import Path
import time
import sys
import ee
from jaguar_irl.training.run_terrain_gee import load_bundle, submit, status, save_record
from jaguar_irl.training.terrain_drive import download
from jaguar_irl.training.terrain_roughness import convert
from jaguar_irl.training.shared_storage import read, locked

root=Path(__file__).resolve().parent.parent
bundle=root/'jobs'
_,plan=load_bundle(bundle)
config=read(root/'cloud_setup.json')
completed={}
# This is a submission guard on observed completed-task usage, not a hard running quota.
usage_limit_seconds=1000
for group in [plan['default_pilot_group']]+[g for g in plan['groups'] if g!=plan['default_pilot_group']]:
    ledger=root/'tasks'/f'{group}.json'
    usage=sum(read(p).get('cloud_status',{}).get('batch_eecu_usage_seconds',0)
              for p in (root/'tasks').glob('*.json'))
    if not ledger.exists():
        if usage>=usage_limit_seconds:
            raise RuntimeError('Observed compute submission guard reached; no further tasks submitted')
        record=submit(ee,bundle,config['project'],'pantanal_spring_srtm_roughness_v1',ledger,
                      group=group,validated_pilot=root/'products'/plan['default_pilot_group'])
        print(group,'submitted',record['task_id'],flush=True)
    started=time.monotonic()
    while True:
        record=status(ee,ledger)
        if record['status']=='COMPLETED': break
        if record['status'] in ('FAILED','CANCELLED'):
            raise RuntimeError(f"{group}: {record.get('cloud_status')}")
        if time.monotonic()-started>1200:
            raise RuntimeError(f'{group}: still running after 20min; resume using existing ledger')
        time.sleep(10)
    tif=download(bundle,group,config['drive_leaf_id'],root/'downloads')
    product=convert(bundle,group,tif,root/'products'/group)
    validation=read(product/'validation.json')
    completed[group]=dict(product_key=validation['product_key'],
                          grid_key=validation['grid_key'],
                          tif=str(tif),npy=str(product/'roughness.npy'),
                          minimum=validation['minimum'],maximum=validation['maximum'],
                          task_id=record['task_id'],
                          eecu_seconds=record['cloud_status'].get('batch_eecu_usage_seconds'))
    summary=dict(schema='spring_terrain_acquisition/1',project=config['project'],
                 drive_folder_id=config['drive_leaf_id'],groups=completed,
                 completed_groups=len(completed),expected_groups=len(plan['groups']),
                 output_cells=sum(plan['groups'][g]['output_cells'] for g in completed),
                 batch_eecu_usage_seconds=sum(v['eecu_seconds'] or 0 for v in completed.values()),
                 submission_usage_guard_seconds=usage_limit_seconds,
                 quality='exact-grid/coverage/numerical checks passed; scientific interpretation not validated')
    with locked(root): save_record(root/'acquisition.json',summary)
    print(group,'validated',record['cloud_status'].get('batch_eecu_usage_seconds'),'EECU-seconds',flush=True)
print('ALL GROUPS COMPLETE',flush=True)
