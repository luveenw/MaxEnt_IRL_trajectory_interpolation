"""Resume candidate-year MapBiomas acquisition without duplicating prior work."""
import argparse
from pathlib import Path
import time
import ee
from jaguar_irl.data.pantanal_checkpoint import digest,file_hash
from jaguar_irl.training.shared_storage import read,locked
from jaguar_irl.training.terrain_roughness import verify_bundle
from jaguar_irl.training.run_terrain_gee import save_record,status
from jaguar_irl.training.terrain_drive import download
from jaguar_irl.training.mapbiomas_landcover import build_ee_image,convert,SOURCES
from jaguar_irl.training.gee_direct import acquire_direct
ROOT=Path(__file__).resolve().parents[2]
BUNDLE=Path(__file__).resolve().parent/'jobs'
DATA=ROOT/'data/pantanal_covariates/spring_mapbiomas_landcover_v1'


def check_source(plan):
    if plan['software_sha256']!=file_hash(ROOT/'jaguar_irl/training/mapbiomas_landcover.py'):raise ValueError('Installed software differs from plan')
    if digest({c:ee.data.getAsset(a) for c,a in SOURCES.items()})!=plan['source_snapshot']['asset_fingerprint']:
        raise ValueError('Live source changed from pinned metadata')


def submit(plan,key,ledger,config):
    j=plan['groups'][key];check_source(plan)
    tasks=ee.batch.Task.list()
    if any(t.config and t.config.get('description')==j['export_prefix'] for t in tasks):raise ValueError('Matching cloud task exists; reconcile ledger')
    if sum(t.state in ('READY','RUNNING','CANCEL_REQUESTED') for t in tasks)>=2:raise ValueError('Two project tasks are active; resume later')
    task=ee.batch.Export.image.toDrive(image=build_ee_image(ee,j),description=j['export_prefix'],
        folder=config['drive_leaf_name'],fileNamePrefix=j['export_prefix'],region=ee.Geometry.Rectangle(j['grid']['bounds'],j['grid']['crs'],False),
        crs=j['grid']['crs'],crsTransform=j['crs_transform'],maxPixels=j['output_cells']*7,
        fileFormat='GeoTIFF',formatOptions={'cloudOptimized':True,'noData':-9999})
    record=dict(schema='mapbiomas_landcover_cache_task/1',project=config['project'],job_id=key,
                product_key=j['product_key'],plan_sha256=file_hash(BUNDLE/'plan.json'),description=j['export_prefix'],
                source_fingerprint=plan['source_snapshot']['asset_fingerprint'],task_id=None,status='submission_intent',
                acquisition_kind='gee_batch_export')
    with locked(ledger.parent):
        if ledger.exists():raise ValueError('Existing ledger; inspect status')
        save_record(ledger,record)
        try:task.start()
        except Exception:
            record['status']='submission_uncertain; reconcile, never blindly retry';save_record(ledger,record);raise
        record.update(task_id=task.id,status='submitted',operation=task.operation_name);save_record(ledger,record)
    return record


def run(pilot_only=False,direct=False,one_pending=False):
    if (DATA/'repair_resolution.json').exists():
        raise ValueError('A versioned G316_2011 repair is registered. Do not retry the historical failed job. Resume gee/spring_mapbiomas_landcover_v1/repairs/G316_2011_temporal_consensus_v1/acquire.py or verify with gee/spring_mapbiomas_landcover_v1/verify_resolved_outputs.py.')
    plan=verify_bundle(BUNDLE);config=read(DATA/'cloud_setup.json');ee.Initialize(project=config['project']);check_source(plan)
    ids=[plan['default_pilot_job']]+[k for k in plan['groups'] if k!=plan['default_pilot_job']]
    if pilot_only:ids=ids[:1]
    complete={}
    for key in ids:
        j=plan['groups'][key];ledger=DATA/'tasks'/f'{key}.json';was_new=not ledger.exists()
        existing=read(ledger) if ledger.exists() else None
        direct_job=(existing and existing.get('acquisition_kind')=='gee_direct_download') or (was_new and direct)
        if direct_job:
            check_source(plan)
            # A completed direct job has no batch task ID and must never enter status().
            rec=acquire_direct(ee,build_ee_image(ee,j),j,config['drive_leaf_id'],DATA/'downloads',ledger,
                               source_identity=plan['source_snapshot']['asset_fingerprint'],
                               validate=lambda tif:convert(BUNDLE,key,tif,DATA/'products'/j['group_id']/str(j['year'])),project=config['project'])
            tif=DATA/'downloads'/(j['export_prefix']+'.tif')
        else:
            if was_new:
                usage=sum(read(p).get('cloud_status',{}).get('batch_eecu_usage_seconds',0) for p in (DATA/'tasks').glob('*.json'))
                if usage>=1000:raise ValueError('Completed batch compute guard reached; no further batch submissions')
                rec=submit(plan,key,ledger,config);print(key,'submitted',rec['task_id'],flush=True)
            started=time.monotonic()
            while True:
                rec=status(ee,ledger)
                if rec['status']=='COMPLETED':break
                if rec['status'] in ('FAILED','CANCELLED'):raise RuntimeError(str(rec['cloud_status']))
                if time.monotonic()-started>1200:raise RuntimeError('Task still active after20min; inspect/resume existing ledger')
                time.sleep(10)
            tif=download(BUNDLE,key,config['drive_leaf_id'],DATA/'downloads')
        product=convert(BUNDLE,key,tif,DATA/'products'/j['group_id']/str(j['year']));v=read(product/'validation.json')
        kind='gee_direct_download' if direct_job else 'gee_batch_export'
        complete[key]=dict(group_id=j['group_id'],year=j['year'],product_key=j['product_key'],acquisition_kind=kind,
                           tif=str(tif),npy={n:str(product/(n+'.npy')) for n in ('grassland_fraction','flooded_habitat_fraction')},
                           statistics=v['statistics'],fallback_fraction_max=v['fallback_fraction_max'],fallback_fraction_mean=v['fallback_fraction_mean'],
                           fallback_cells=v['fallback_cells'],fallback_projected_area_m2=v['fallback_projected_area_m2'])
        if direct_job:complete[key].update(drive_file_id=rec['drive_file']['id'],online_eecu_usage_seconds=None,online_eecu_usage_measured=False)
        else:complete[key].update(task_id=rec['task_id'],reported_batch_eecu_seconds=rec['cloud_status'].get('batch_eecu_usage_seconds',0))
        summary=dict(schema='mapbiomas_landcover_candidate_year_acquisition/2',groups=complete,completed_jobs=len(complete),expected_jobs=plan['job_count'],group_count=plan['group_count'],
                     plan_sha256=file_hash(BUNDLE/'plan.json'),reported_batch_eecu_usage_seconds=sum(x.get('reported_batch_eecu_seconds',0) for x in complete.values()),
                     direct_job_count=sum(x['acquisition_kind']=='gee_direct_download' for x in complete.values()),online_eecu_usage_seconds=None,online_eecu_usage_measured=False,
                     epoch_role='candidate caches; representative year not selected',scientific_validation='not established')
        with locked(DATA):save_record(DATA/'acquisition.json',summary)
        print(key,'validated',kind,flush=True)
        if one_pending and was_new:break
    print('Acquisition scope complete',len(complete),'of',len(plan['groups']),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pilot-only',action='store_true');p.add_argument('--direct',action='store_true');p.add_argument('--one-pending',action='store_true');run(**vars(p.parse_args()))
