"""Offline verification of the accepted partial MapBiomas cache; never accepts failed products."""
from pathlib import Path
import json
import hashlib
import numpy as np
import rasterio
from jaguar_irl.data.pantanal_checkpoint import file_hash
from jaguar_irl.training.shared_storage import read,write
from jaguar_irl.training.terrain_roughness import verify_bundle
from jaguar_irl.training.mapbiomas_landcover import check_pixels
ROOT=Path(__file__).resolve().parents[2];BUNDLE=Path(__file__).resolve().parent/'jobs'
DATA=ROOT/'data/pantanal_covariates/spring_mapbiomas_landcover_v1'
plan=verify_bundle(BUNDLE);run=read(DATA/'acquisition.json');config=read(DATA/'cloud_setup.json')
assert set(run['groups']) < set(plan['groups'])
assert len(plan['groups'])==24 and plan['group_count']==13
assert file_hash(Path(plan['checkpoint'])/'checkpoint.json')==plan['checkpoint_sha256']
assert file_hash(Path(plan['checkpoint'])/'grids.json')==plan['grids_sha256']
products={}
for key in run['groups']:
    j=plan['groups'][key]
    out=DATA/'products'/j['group_id']/str(j['year']);v=read(out/'validation.json')
    assert v['product_key']==j['product_key'] and v['plan_sha256']==file_hash(BUNDLE/'plan.json')
    for name,checksum in read(out/'checksums.json').items():assert file_hash(out/name)==checksum
    with rasterio.open(out/'source.tif') as ds:
        data=ds.read();check_pixels(data,ds.read_masks()>0)
    for i,n in enumerate(('grassland_fraction','flooded_habitat_fraction')):
        a=np.load(out/(n+'.npy'),allow_pickle=False)
        assert a.shape==(j['grid']['rows'],j['grid']['cols']) and a.dtype==np.float32
        assert np.array_equal(a,data[i])
    ledger=read(DATA/'tasks'/f'{key}.json');assert ledger['status']=='COMPLETED' and ledger['product_key']==j['product_key']
    direct=ledger.get('acquisition_kind')=='gee_direct_download'
    if direct:
        assert 'task_id' not in ledger and ledger['online_eecu_usage_measured'] is False
        assert ledger['source_identity']==plan['source_snapshot']['asset_fingerprint']
        assert ledger['download_sha256']==file_hash(out/'source.tif')
    tif=DATA/'downloads'/(j['export_prefix']+'.tif');remote=read(tif.with_name(tif.name+'.drive.json'))
    assert config['drive_leaf_id'] in remote['parents'] and hashlib.md5(tif.read_bytes()).hexdigest()==remote['md5Checksum']
    assert file_hash(tif)==v['source_tif_sha256']
    products[key]=dict(acquisition_kind='gee_direct_download' if direct else 'gee_batch_export',drive_file_id=remote['id'],npys={n:file_hash(out/(n+'.npy')) for n in ('grassland_fraction','flooded_habitat_fraction')},fallback_fraction_max=v['fallback_fraction_max'],fallback_cells=v['fallback_cells'],fallback_projected_area_m2=v['fallback_projected_area_m2'])
    if not direct:products[key]['task_id']=ledger['task_id']
    if j['group_id']!='G115':assert v['fallback_fraction_max']==0
    else:assert v['fallback_fraction_max']>0
report=dict(schema='mapbiomas_landcover_inventory_verification/1',job_count=len(products),group_count=len({plan['groups'][k]['group_id'] for k in products}),missing_jobs=sorted(set(plan['groups'])-set(products)),npy_count=len(products)*2,
            output_cells=sum(plan['groups'][k]['output_cells'] for k in products),reported_batch_eecu_usage_seconds=run['reported_batch_eecu_usage_seconds'],direct_job_count=run['direct_job_count'],online_eecu_usage_seconds=None,online_eecu_usage_measured=False,
            downloaded_tiff_bytes=sum(p.stat().st_size for p in (DATA/'downloads').glob('*.tif')),
            products=products,quality='exact-grid, complete coverage, source provenance sum and numerical integrity checks passed; ecological validation pending')
write(DATA/'partial_verification.json',report)
print(json.dumps({k:v for k,v in report.items() if k!='products'},indent=2))
