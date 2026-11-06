"""Resume ESA caches: ledgered batch jobs finish; new jobs use bounded direct retrieval."""
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
from jaguar_irl.training.gee_direct import acquire_direct
ROOT=Path(__file__).resolve().parents[2]
BUNDLE=Path(__file__).resolve().parent/'jobs'
DATA=ROOT/'data/pantanal_covariates/spring_esa_shrubland_v1'

def submit(plan,key,ledger,config):
    j=plan['groups'][key]
    if plan['software_sha256']!=file_hash(ROOT/'jaguar_irl/training/shrubland.py'):raise ValueError('Installed software differs from plan')
    if digest(ee.data.getAsset(SOURCE))!=plan['source_snapshot']['asset_fingerprint']:raise ValueError('Live source changed from pinned metadata')
    tasks=ee.batch.Task.list()
    if any(t.config and t.config.get('description')==j['export_prefix'] for t in tasks):raise ValueError('Matching cloud task exists; reconcile ledger')
    if sum(t.state in ('READY','RUNNING','CANCEL_REQUESTED') for t in tasks)>=2:raise ValueError('Two project tasks are active; resume later')
    region=ee.Geometry.Rectangle(j['grid']['bounds'],j['grid']['crs'],False)
    task=ee.batch.Export.image.toDrive(image=build_ee_image(ee,j),description=j['export_prefix'],
        folder=config['drive_leaf']['name'],fileNamePrefix=j['export_prefix'],region=region,
        crs=j['grid']['crs'],crsTransform=j['crs_transform'],maxPixels=j['output_cells']*2,
        fileFormat='GeoTIFF',formatOptions={'cloudOptimized':True,'noData':-9999})
    record=dict(schema='shrubland_cache_task/1',project=config['project'],job_id=key,
                product_key=j['product_key'],plan_sha256=file_hash(BUNDLE/'plan.json'),description=j['export_prefix'],
                source_fingerprint=plan['source_snapshot']['asset_fingerprint'],driver_sha256=file_hash(__file__),task_id=None,status='submission_intent')
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
        existing=read(ledger) if ledger.exists() else None
        is_direct=existing is None or existing.get('acquisition_kind')=='gee_direct_download'
        destination=DATA/'products'/j['group_id']/str(j['year'])
        if is_direct:
            if digest(ee.data.getAsset(SOURCE))!=plan['source_snapshot']['asset_fingerprint']:
                raise ValueError('Live source changed')
            rec=acquire_direct(ee,build_ee_image(ee,j),j,config['drive_leaf']['id'],DATA/'downloads',ledger,
                {'asset':SOURCE,'band':j['source_band'],'asset_fingerprint':plan['source_snapshot']['asset_fingerprint']},
                lambda path:convert(BUNDLE,key,path,destination),project=config['project'])
            rec.update(job_id=key,group_id=j['group_id'],year=j['year'],plan_sha256=file_hash(BUNDLE/'plan.json'),driver_sha256=file_hash(__file__))
            save_record(ledger,rec)
            tif=DATA/'downloads'/(j['export_prefix']+'.tif')
        else:
            rec=existing
            started=time.monotonic()
            while rec['status']!='COMPLETED':
                rec=status(ee,ledger)
                if rec['status'] in ('FAILED','CANCELLED'):raise RuntimeError(str(rec['cloud_status']))
                if rec['status']=='COMPLETED':break
                if time.monotonic()-started>1200:raise RuntimeError('Batch task remains active; inspect/resume its ledger')
                time.sleep(10)
            tif=DATA/'downloads'/(j['export_prefix']+'.tif')
            if not tif.exists():tif=download(BUNDLE,key,config['drive_leaf']['id'],DATA/'downloads')
            convert(BUNDLE,key,tif,destination)
        v=read(destination/'validation.json')
        item=dict(group_id=j['group_id'],year=j['year'],product_key=j['product_key'],
                  tif=str(tif),npy=str(destination/'shrubland_fraction.npy'),
                  minimum=v['minimum'],maximum=v['maximum'],mean=v['mean'],
                  acquisition_kind='gee_direct_download' if is_direct else 'gee_batch_export')
        if is_direct:
            item.update(online_eecu_usage_seconds=None,drive_file_id=rec['drive_file']['id'],request_graph_sha256=rec['request_graph_sha256'])
        else:item.update(task_id=rec['task_id'],batch_eecu_seconds=rec['cloud_status'].get('batch_eecu_usage_seconds'))
        complete[key]=item
        summary=dict(schema='shrubland_candidate_year_acquisition/2',groups=complete,completed_jobs=len(complete),
                     expected_jobs=plan['job_count'],group_count=plan['group_count'],plan_sha256=file_hash(BUNDLE/'plan.json'),
                     batch_eecu_usage_seconds=sum(x.get('batch_eecu_seconds') or 0 for x in complete.values()),
                     direct_job_count=sum(x['acquisition_kind']=='gee_direct_download' for x in complete.values()),
                     online_eecu_usage_measured=False,
                     epoch_role='candidate caches; representative year not selected',scientific_validation='not established',
                     driver_sha256=file_hash(__file__),max_total_reviewed_workflows=2,max_active_requests_per_driver=1)
        with locked(DATA):save_record(DATA/'acquisition.json',summary)
        print(key,'validated',item['acquisition_kind'],flush=True)
    print('Acquisition scope complete',len(complete),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pilot-only',action='store_true');run(**vars(p.parse_args()))
