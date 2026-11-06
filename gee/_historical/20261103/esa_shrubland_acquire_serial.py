"""Resume candidate-year ESA shrubland acquisition, with one active project task."""
import argparse
from pathlib import Path
import time
import ee
from jaguar_irl.data.pantanal_checkpoint import digest,file_hash
from jaguar_irl.training.shared_storage import read,write,locked
from jaguar_irl.training.terrain_roughness import verify_bundle
from jaguar_irl.training.run_terrain_gee import save_record,status
from jaguar_irl.training.terrain_drive import download
from jaguar_irl.training.shrubland import build_ee_image,convert,SOURCE
ROOT=Path(__file__).resolve().parents[2]
BUNDLE=Path(__file__).resolve().parent/'jobs'
DATA=ROOT/'data/pantanal_covariates/spring_esa_shrubland_v1'

def submit(plan,key,ledger,config):
    j=plan['groups'][key]
    if plan['software_sha256']!=file_hash(ROOT/'jaguar_irl/training/shrubland.py'):raise ValueError('Installed software differs from plan')
    if digest(ee.data.getAsset(SOURCE))!=plan['source_snapshot']['asset_fingerprint']:raise ValueError('Live source changed from pinned metadata')
    tasks=ee.batch.Task.list()
    if any(t.config and t.config.get('description')==j['export_prefix'] for t in tasks):raise ValueError('Matching cloud task exists; reconcile ledger')
    if any(t.state in ('READY','RUNNING','CANCEL_REQUESTED') for t in tasks):raise ValueError('Another project task is active; resume later')
    region=ee.Geometry.Rectangle(j['grid']['bounds'],j['grid']['crs'],False)
    task=ee.batch.Export.image.toDrive(image=build_ee_image(ee,j),description=j['export_prefix'],
        folder=config['drive_leaf']['name'],fileNamePrefix=j['export_prefix'],region=region,
        crs=j['grid']['crs'],crsTransform=j['crs_transform'],maxPixels=j['output_cells']*2,
        fileFormat='GeoTIFF',formatOptions={'cloudOptimized':True,'noData':-9999})
    record=dict(schema='shrubland_cache_task/1',project=config['project'],job_id=key,
                product_key=j['product_key'],plan_sha256=file_hash(BUNDLE/'plan.json'),description=j['export_prefix'],
                source_fingerprint=plan['source_snapshot']['asset_fingerprint'],task_id=None,status='submission_intent')
    with locked(ledger.parent):
        if ledger.exists():raise ValueError('Existing ledger; inspect status')
        save_record(ledger,record)
        try:task.start()
        except Exception:
            record['status']='submission_uncertain; reconcile, never blindly retry';save_record(ledger,record);raise
        record.update(task_id=task.id,status='submitted',operation=task.operation_name);save_record(ledger,record)
    return record


def run(pilot_only=False):
    plan=verify_bundle(BUNDLE);config=read(DATA/'cloud_setup.json');ee.Initialize(project=config['project'])
    snapshot=ee.data.getAsset(SOURCE)
    if digest(snapshot)!=plan['source_snapshot']['asset_fingerprint']:raise ValueError('Live source changed')
    ids=[plan['default_pilot_job']]+[k for k in plan['groups'] if k!=plan['default_pilot_job']]
    if pilot_only:ids=ids[:1]
    complete={}
    for key in ids:
        j=plan['groups'][key];ledger=DATA/'tasks'/f'{key}.json'
        if not ledger.exists():
            usage=sum(read(p).get('cloud_status',{}).get('batch_eecu_usage_seconds',0) for p in (DATA/'tasks').glob('*.json'))
            if usage>=1000:raise ValueError('Completed-task compute guard reached; no further submissions')
            rec=submit(plan,key,ledger,config);print(key,'submitted',rec['task_id'],flush=True)
        started=time.monotonic()
        while True:
            rec=status(ee,ledger)
            if rec['status']=='COMPLETED':break
            if rec['status'] in ('FAILED','CANCELLED'):raise RuntimeError(str(rec['cloud_status']))
            if time.monotonic()-started>1200:raise RuntimeError('Task still active after20min; inspect/resume existing ledger')
            time.sleep(10)
        tif=download(BUNDLE,key,config['drive_leaf']['id'],DATA/'downloads')
        product=convert(BUNDLE,key,tif,DATA/'products'/j['group_id']/str(j['year']))
        v=read(product/'validation.json')
        complete[key]=dict(group_id=j['group_id'],year=j['year'],product_key=j['product_key'],
                           tif=str(tif),npy=str(product/'shrubland_fraction.npy'),task_id=rec['task_id'],
                           minimum=v['minimum'],maximum=v['maximum'],mean=v['mean'],
                           eecu_seconds=rec['cloud_status'].get('batch_eecu_usage_seconds',0))
        summary=dict(schema='shrubland_candidate_year_acquisition/1',groups=complete,completed_jobs=len(complete),
                     expected_jobs=plan['job_count'],group_count=plan['group_count'],plan_sha256=file_hash(BUNDLE/'plan.json'),
                     batch_eecu_usage_seconds=sum(x['eecu_seconds'] for x in complete.values()),
                     epoch_role='candidate caches; representative year not selected',scientific_validation='not established')
        with locked(DATA):save_record(DATA/'acquisition.json',summary)
        print(key,'validated',complete[key]['eecu_seconds'],'EECU-seconds',flush=True)
    print('Acquisition scope complete',len(complete),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pilot-only',action='store_true');run(**vars(p.parse_args()))
