"""Submit one pinned terrain export or inspect its durable task record.

Earth Engine authentication must already exist. No credential values are logged.
"""
import argparse
import json
import os
from pathlib import Path

from jaguar_irl.data.pantanal_checkpoint import file_hash
from .shared_storage import locked, read, write, sync_dir
from .terrain_roughness import RECIPE, build_ee_image, verify_bundle


def load_bundle(bundle):
    bundle = Path(bundle).resolve()
    plan = verify_bundle(bundle)
    if plan['recipe'] != RECIPE:
        raise ValueError('Installed terrain graph differs from saved recipe')
    if plan['software_sha256'] != file_hash(Path(__file__).with_name('terrain_roughness.py')):
        raise ValueError('Installed terrain software differs from saved plan')
    return bundle, plan


def save_record(path, state):
    pending = path.with_name('.'+path.name+'.pending')
    write(pending, state)
    os.replace(pending, path)
    sync_dir(path.parent)


def submit(ee, bundle, project, folder, ledger, group=None, validated_pilot=None):
    bundle, plan = load_bundle(bundle)
    group = group or plan['default_pilot_group']
    job = plan['groups'][group]
    if group != plan['default_pilot_group']:
        if not validated_pilot:
            raise ValueError('Validate the pilot TIFF before submitting other groups')
        pilot = read(Path(validated_pilot)/'validation.json')
        if (pilot['product_key'] != plan['groups'][plan['default_pilot_group']]['product_key']
                or pilot['plan_sha256'] != file_hash(bundle/'plan.json')):
            raise ValueError('Pilot validation does not belong to this plan')
    ledger = Path(ledger).resolve()
    with locked(ledger.parent):
        if ledger.exists():
            raise ValueError('Task record already exists; inspect status instead of resubmitting')
        ee.Initialize(project=project)
        tasks = ee.batch.Task.list()
        if any(t.config and t.config.get('description') == job['export_prefix'] for t in tasks):
            raise ValueError('A matching cloud task already exists; reconcile instead of duplicating')
        if any(t.state in ('READY','RUNNING','CANCEL_REQUESTED') for t in tasks):
            raise ValueError('An existing project task is active; wait before submitting another')
        region = ee.Geometry.Rectangle(job['grid']['bounds'], job['grid']['crs'], False)
        task = ee.batch.Export.image.toDrive(
            image=build_ee_image(ee, job), description=job['export_prefix'],
            folder=folder, fileNamePrefix=job['export_prefix'], region=region,
            crs=job['grid']['crs'], crsTransform=job['crs_transform'],
            maxPixels=job['output_cells']*2, fileFormat='GeoTIFF',
            formatOptions={'cloudOptimized':True,'noData':RECIPE['nodata']})
        state = dict(schema='terrain_cloud_task/1', group_id=group,
                     plan_sha256=file_hash(bundle/'plan.json'), product_key=job['product_key'],
                     project=project, drive_folder=folder, description=job['export_prefix'],
                     task_id=None, status='submission_intent',
                     runner_sha256=file_hash(__file__))
        save_record(ledger,state)
        try:
            task.start()
        except Exception:
            # A failed response can follow a successful server submission. Never auto-retry.
            state['status']='submission_uncertain; inspect cloud tasks before retrying'
            save_record(ledger,state)
            raise
        state.update(task_id=task.id,status='submitted',operation=task.operation_name)
        save_record(ledger,state)
    return state


def status(ee, ledger):
    ledger=Path(ledger).resolve()
    with locked(ledger.parent):
        state=read(ledger)
        ee.Initialize(project=state['project'])
        if state.get('task_id'):
            result=ee.data.getTaskStatus(state['task_id'])[0]
        else:
            matches=[t for t in ee.batch.Task.list()
                     if t.config and t.config.get('description')==state['description']]
            if len(matches)!=1:
                raise ValueError('Uncertain submission: reconcile cloud task list manually')
            result=matches[0].status()
            state['task_id']=matches[0].id
        # Retain status, usage and error metadata. Credentials never enter this record.
        state['cloud_status']=result
        state['status']=result.get('state','UNKNOWN')
        save_record(ledger,state)
    return state


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('submit')
    p.add_argument('--bundle',required=True); p.add_argument('--project',required=True)
    p.add_argument('--folder',required=True); p.add_argument('--ledger',required=True)
    p.add_argument('--group'); p.add_argument('--validated-pilot')
    p=sub.add_parser('status'); p.add_argument('--ledger',required=True)
    args=vars(parser.parse_args()); command=args.pop('command')
    try:
        import ee
    except ImportError as exc:
        raise RuntimeError('Install earthengine-api in your extraction environment') from exc
    result=submit(ee,**args) if command=='submit' else status(ee,**args)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
