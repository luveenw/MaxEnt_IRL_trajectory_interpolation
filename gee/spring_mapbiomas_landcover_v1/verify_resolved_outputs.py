"""Offline verification of original products plus the explicit one-job repair overlay."""
from pathlib import Path
import json,hashlib
import numpy as np
import rasterio
from jaguar_irl.data.pantanal_checkpoint import file_hash
from jaguar_irl.training.shared_storage import read,write
from jaguar_irl.training.terrain_roughness import verify_bundle
from jaguar_irl.training.mapbiomas_landcover import check_pixels as check_original
from jaguar_irl.training.mapbiomas_temporal_repair import check_pixels as check_repair
ROOT=Path(__file__).resolve().parents[2];BUNDLE=Path(__file__).resolve().parent/'jobs'
DATA=ROOT/'data/pantanal_covariates/spring_mapbiomas_landcover_v1'
base=verify_bundle(BUNDLE);run=read(DATA/'acquisition.json');resolution=read(DATA/'repair_resolution.json');config=read(DATA/'cloud_setup.json')
assert resolution['status']=='COMPLETED' and set(resolution['resolutions'])=={'G316_2011'}
assert set(run['groups'])==set(base['groups']) and len(run['groups'])==24
assert file_hash(Path(base['checkpoint'])/'checkpoint.json')==base['checkpoint_sha256']
assert file_hash(Path(base['checkpoint'])/'grids.json')==base['grids_sha256']
products={};accepted_tiff_bytes=0
for key,original in base['groups'].items():
    repaired=key in resolution['resolutions']
    if repaired:
        ref=resolution['resolutions'][key];bundle=Path(ref['bundle']);plan=verify_bundle(bundle);j=plan['groups'][key]
        assert plan['original_product_key']==original['product_key']
        assert plan['original_plan_sha256']==file_hash(BUNDLE/'plan.json')
        assert plan['recipe']['features']==base['recipe']['features'] and j['grid']==original['grid'] and j['year']==original['year']
        assert plan['source_snapshot']==base['source_snapshot']
        out=Path(ref['product']);ledger_path=Path(ref['ledger']);downloads=Path(ref['downloads'])
        old_ledger=read(DATA/'tasks'/f'{key}.json');assert old_ledger['status']=='validation_failed'
        old_tif=DATA/'downloads'/(original['export_prefix']+'.tif')
        assert file_hash(old_tif)==plan['original_failed_tif_sha256']==old_ledger['download_sha256']
    else:
        bundle=BUNDLE;plan=base;j=original;out=DATA/'products'/j['group_id']/str(j['year']);ledger_path=DATA/'tasks'/f'{key}.json';downloads=DATA/'downloads'
    v=read(out/'validation.json')
    assert v['product_key']==j['product_key'] and v['plan_sha256']==file_hash(bundle/'plan.json')
    for name,checksum in read(out/'checksums.json').items():assert file_hash(out/name)==checksum
    with rasterio.open(out/'source.tif') as ds:
        data=ds.read();(check_repair if repaired else check_original)(data,ds.read_masks()>0)
    for i,n in enumerate(('grassland_fraction','flooded_habitat_fraction')):
        a=np.load(out/(n+'.npy'),allow_pickle=False)
        assert a.shape==(j['grid']['rows'],j['grid']['cols']) and a.dtype==np.float32
        assert np.array_equal(a,data[i])
    ledger=read(ledger_path);assert ledger['status']=='COMPLETED' and ledger['product_key']==j['product_key']
    direct=ledger.get('acquisition_kind')=='gee_direct_download'
    if direct:
        assert 'task_id' not in ledger and ledger['online_eecu_usage_measured'] is False
        assert ledger['source_identity']==plan['source_snapshot']['asset_fingerprint']
        assert ledger['download_sha256']==file_hash(out/'source.tif')
    tif=downloads/(j['export_prefix']+'.tif');remote=read(tif.with_name(tif.name+'.drive.json'))
    assert config['drive_leaf_id'] in remote['parents'] and hashlib.md5(tif.read_bytes()).hexdigest()==remote['md5Checksum']
    assert file_hash(tif)==v['source_tif_sha256'];accepted_tiff_bytes+=tif.stat().st_size
    products[key]=dict(acquisition_kind='gee_direct_download' if direct else 'gee_batch_export',drive_file_id=remote['id'],
        effective_bundle=str(bundle),plan_sha256=v['plan_sha256'],product_key=j['product_key'],
        npys={n:file_hash(out/(n+'.npy')) for n in ('grassland_fraction','flooded_habitat_fraction')},repaired=repaired)
    if not direct:products[key]['task_id']=ledger['task_id']
    if repaired:
        products[key].update(imputed_cells=v['imputed_cells'],imputed_projected_area_m2=v['imputed_projected_area_m2'],observed_coverage_min=v['observed_coverage_min'],effective_coverage_min=v['effective_coverage_min'])
    elif j['group_id']=='G115':assert v['fallback_cells']==7 and 80520<v['fallback_projected_area_m2']<80522
    else:assert v['fallback_fraction_max']==0
report=dict(schema='mapbiomas_landcover_resolved_inventory_verification/1',job_count=24,group_count=13,npy_count=48,
            output_cells=sum(j['output_cells'] for j in base['groups'].values()),reported_batch_eecu_usage_seconds=run['reported_batch_eecu_usage_seconds'],
            direct_job_count=run['direct_job_count'],failed_direct_job_count=1,online_eecu_usage_seconds=None,online_eecu_usage_measured=False,
            accepted_tiff_bytes=accepted_tiff_bytes,products=products,temporal_repair_jobs=['G316_2011'],
            quality='Exact-grid coverage and numerical checks passed; explicit user-approved one-pixel temporal imputation distinguished from observed support; ecological validation pending')
write(DATA/'verification.json',report)
print(json.dumps({k:v for k,v in report.items() if k!='products'},indent=2))
