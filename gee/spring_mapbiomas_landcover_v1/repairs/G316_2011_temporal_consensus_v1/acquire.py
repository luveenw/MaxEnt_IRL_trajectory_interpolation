"""Run only the user-approved exact G316_2011 temporal consensus repair."""
from pathlib import Path
import argparse,copy,json,hashlib
import ee
from jaguar_irl.data.pantanal_checkpoint import digest,file_hash
from jaguar_irl.training.shared_storage import read,write,locked
from jaguar_irl.training.terrain_roughness import verify_bundle
from jaguar_irl.training.run_terrain_gee import save_record
from jaguar_irl.training.gee_direct import acquire_direct
from jaguar_irl.training.mapbiomas_landcover import SOURCES
from jaguar_irl.training.mapbiomas_temporal_repair import native_repair,build_ee_image,convert,HERE,DATA,REPAIR_DATA,APPROVAL
BUNDLE=HERE/'jobs';KEY='G316_2011';PRODUCT=DATA/'products/G316/2011'


def run(check_only=False):
    plan=verify_bundle(BUNDLE);j=plan['groups'][KEY];config=read(DATA/'cloud_setup.json')
    if file_hash(APPROVAL)!=plan['approval_sha256']:raise ValueError('Pinned approval record changed')
    if file_hash(Path(__file__).resolve().parents[4]/'jaguar_irl/training/mapbiomas_temporal_repair.py')!=plan['software_sha256']:raise ValueError('Repair software changed')
    ee.Initialize(project=config['project'])
    if digest({c:ee.data.getAsset(a) for c,a in SOURCES.items()})!=plan['source_snapshot']['asset_fingerprint']:raise ValueError('Source identity changed')
    chosen,sid,observed,patch,previous,following,base=native_repair(ee)
    xy=ee.Image.pixelCoordinates(base)
    raw=ee.Image(SOURCES['brazil']).select('classification_2011')
    points=(patch.selfMask().rename('patch').addBands(previous.rename('previous_class')).addBands(following.rename('following_class'))
            .addBands(observed.rename('observed_valid')).addBands(sid.rename('original_source_id'))
            .addBands(raw.unmask(-9999,False).rename('original_2011_class')).addBands(xy.floor()))
    region=ee.Geometry.Rectangle(j['grid']['bounds'],j['grid']['crs'],False)
    audit=points.sample(region=region,projection=base,geometries=True).getInfo()
    if len(audit['features'])!=1:raise ValueError('Runtime guard did not identify exactly one approved source pixel')
    p=audit['features'][0]['properties']
    if not (p['previous_class']==p['following_class']==4 and p['observed_valid']==0 and p['original_source_id']==0 and p['x']==60974 and p['y']==86248):raise ValueError('Live adjacent-year consensus/scope mismatch')
    REPAIR_DATA.mkdir(parents=True,exist_ok=True)
    write(REPAIR_DATA/'live_consensus_check.json',dict(status='Live GEE guard passed: exactly one approved missing native pixel, adjacent years retrieved and both class4',source_fingerprint=plan['source_snapshot']['asset_fingerprint'],features=audit['features']))
    index=dict(schema='mapbiomas_repair_resolution/1',status='approved_and_runtime_checked' if check_only else 'running',resolutions={KEY:dict(
        bundle=str(BUNDLE),plan=str(BUNDLE/'plan.json'),plan_sha256=file_hash(BUNDLE/'plan.json'),ledger=str(REPAIR_DATA/'tasks'/f'{KEY}.json'),
        downloads=str(REPAIR_DATA/'downloads'),product=str(PRODUCT),product_key=j['product_key'],
        original_bundle=plan['original_bundle'],original_plan_sha256=plan['original_plan_sha256'],original_product_key=plan['original_product_key'],
        original_failed_ledger=plan['original_failed_ledger'],original_failed_tif_sha256=plan['original_failed_tif_sha256'],approval_sha256=plan['approval_sha256'])})
    prior_resolution=read(DATA/'repair_resolution.json') if (DATA/'repair_resolution.json').exists() else None
    if prior_resolution and prior_resolution.get('status')=='COMPLETED':
        old_ref=prior_resolution['resolutions'][KEY]
        if any(old_ref.get(k)!=v for k,v in index['resolutions'][KEY].items()):raise ValueError('Completed repair identity differs')
        index=prior_resolution # A read-only guard check must not downgrade a completed resolution.
    else:
        save_record(DATA/'repair_resolution.json',index)
    if check_only:
        print('Runtime consensus confirmed; no raster export/download/upload performed');return
    record=acquire_direct(ee,build_ee_image(ee,j),j,config['drive_leaf_id'],REPAIR_DATA/'downloads',REPAIR_DATA/'tasks'/f'{KEY}.json',
                          source_identity=plan['source_snapshot']['asset_fingerprint'],validate=lambda tif:convert(BUNDLE,tif,PRODUCT),project=config['project'])
    v=read(PRODUCT/'validation.json');index['status']='COMPLETED';index['resolutions'][KEY].update(drive_file_id=record['drive_file']['id'],source_tif_sha256=v['source_tif_sha256'])
    save_record(DATA/'repair_resolution.json',index)
    with locked(DATA):
        current=read(DATA/'acquisition.json');prior=DATA/'provenance/acquisition_before_G316_repair.json';prior.parent.mkdir(exist_ok=True)
        if not prior.exists():prior.write_bytes((DATA/'acquisition.json').read_bytes())
        if KEY not in current['groups']:
            current=copy.deepcopy(current)
            current['groups'][KEY]=dict(group_id='G316',year=2011,product_key=j['product_key'],acquisition_kind='gee_direct_download',
                tif=str(REPAIR_DATA/'downloads'/(j['export_prefix']+'.tif')),npy={n:str(PRODUCT/(n+'.npy')) for n in ('grassland_fraction','flooded_habitat_fraction')},
                statistics=v['statistics'],repair_bundle=str(BUNDLE),repair_plan_sha256=file_hash(BUNDLE/'plan.json'),repair_ledger=str(REPAIR_DATA/'tasks'/f'{KEY}.json'),
                original_product_key=plan['original_product_key'],original_plan_sha256=plan['original_plan_sha256'],drive_file_id=record['drive_file']['id'],
                observed_coverage_min=v['observed_coverage_min'],effective_coverage_min=v['effective_coverage_min'],imputed_cells=1,imputed_projected_area_m2=v['imputed_projected_area_m2'],
                online_eecu_usage_seconds=None,online_eecu_usage_measured=False)
            current.update(schema='mapbiomas_landcover_candidate_year_acquisition/3',completed_jobs=len(current['groups']),direct_job_count=current['direct_job_count']+1,
                           repair_resolution=str(DATA/'repair_resolution.json'),effective_plan_policy='Original per-job plan except versioned user-approved G316_2011 repair; each repaired entry pins its own plan',repaired_jobs=[KEY])
            save_record(DATA/'acquisition.json',current)
    print(json.dumps(dict(status='COMPLETED',job_id=KEY,product=str(PRODUCT),observed_coverage_min=v['observed_coverage_min'],effective_coverage_min=v['effective_coverage_min'],imputed_cells=1,imputed_projected_area_m2=v['imputed_projected_area_m2']),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');run(**vars(p.parse_args()))
