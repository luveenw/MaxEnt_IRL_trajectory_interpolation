"""Offline inventory verification of the three approved Spring land-cover caches."""
from pathlib import Path
import csv
import argparse
import hashlib
import numpy as np
import rasterio
from affine import Affine
from jaguar_irl.training.shared_storage import read,write
from jaguar_irl.training.terrain_roughness import verify_bundle
from jaguar_irl.data.pantanal_checkpoint import file_hash

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/pantanal_covariates'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--allow-incomplete',action='store_true')
args=parser.parse_args()
RUNS={'esa':('spring_esa_shrubland_v1',['shrubland_fraction']),
      'mapbiomas':('spring_mapbiomas_landcover_v1',['grassland_fraction','flooded_habitat_fraction'])}
plans={key:verify_bundle(ROOT/'gee'/folder/'jobs') for key,(folder,_) in RUNS.items()}
cp=Path(plans['esa']['checkpoint'])
with (cp/'collection_members.csv').open() as handle:
    expected={(r['group_id'],int(r['window_start'][:4])) for r in csv.DictReader(handle)
              if r['collection_id']=='SPR-C01' and r['selection_status']=='selected'}
assert len(expected)==24
report={'schema':'spring_landcover_inventory/1','group_years':{},'runs':{},
        'decisions_sha256':file_hash(DATA/'spring_landcover_decisions_20261103.json'),
        'representative_years':None,'epoch_role':'candidate-year cache; training-only selection after reviewed split',
        'scientific_validation':'not established by spatial/numerical/source checks'}
for run,(folder,names) in RUNS.items():
    base=DATA/folder;plan=plans[run];jobs=plan['groups']
    assert {(j['group_id'],j['year']) for j in jobs.values()}==expected
    assert file_hash(cp/'checkpoint.json')==plan['checkpoint_sha256']
    assert file_hash(cp/'grids.json')==plan['grids_sha256']
    acquisition=read(base/'acquisition.json')
    ready=set(acquisition['groups'])
    assert acquisition['completed_jobs']==len(ready) and ready<=set(jobs)
    if not args.allow_incomplete: assert ready==set(jobs)
    setup=read(base/'cloud_setup.json');folder_id=setup.get('drive_leaf',{}).get('id') or setup['drive_leaf_id']
    resolution_index=read(base/'repair_resolution.json') if (base/'repair_resolution.json').exists() else {'resolutions':{}}
    fallback=[]; temporal_repairs=[]
    direct_completed=0; batch_completed=0; measured_batch=0.0
    for key,j in jobs.items():
        if key not in ready: continue
        base_job=j
        active_bundle=ROOT/'gee'/folder/'jobs'
        active_downloads=base/'downloads'
        ledger_path=base/'tasks'/f'{key}.json'
        repair=resolution_index.get('resolutions',{}).get(key)
        if repair:
            assert run=='mapbiomas' and key=='G316_2011'
            active_bundle=Path(repair['bundle'])
            if not active_bundle.is_absolute(): active_bundle=ROOT/active_bundle
            repair_plan=verify_bundle(active_bundle)
            assert repair_plan['original_plan_sha256']==file_hash(ROOT/'gee'/folder/'jobs/plan.json')
            assert repair_plan['original_product_key']==base_job['product_key']
            assert repair_plan['source_snapshot']==plan['source_snapshot']
            assert repair_plan['recipe']['features']==plan['recipe']['features']
            approval=base/'approved_G316_temporal_repair.json'
            assert read(approval)['status']=='accepted_by_user'
            assert file_hash(approval)==repair_plan['approval_sha256']==repair['approval_sha256']
            original_failure=read(base/'tasks'/f'{key}.json')
            assert original_failure['status']=='validation_failed'
            failed_tif=base/'downloads'/(base_job['export_prefix']+'.tif')
            assert file_hash(failed_tif)==repair_plan['original_failed_tif_sha256']==repair['original_failed_tif_sha256']
            j=repair_plan['groups'][key]
            assert j['grid']==base_job['grid'] and j['year']==base_job['year'] and j['group_id']==base_job['group_id']
            assert j['product_key']==repair['product_key'] and j['product_key']!=base_job['product_key']
            ledger_path=Path(repair['ledger'])
            active_downloads=Path(repair['downloads'])
            if not ledger_path.is_absolute(): ledger_path=ROOT/ledger_path
            if not active_downloads.is_absolute(): active_downloads=ROOT/active_downloads
            assert file_hash(active_bundle/'plan.json')==repair['plan_sha256']
        pair=f"{j['group_id']}_{j['year']}";dest=base/'products'/j['group_id']/str(j['year'])
        validation=read(dest/'validation.json')
        assert validation['product_key']==j['product_key']
        assert validation['plan_sha256']==file_hash(active_bundle/'plan.json')
        for filename,sha in read(dest/'checksums.json').items():
            assert Path(filename).name==filename and file_hash(dest/filename)==sha
        ledger=read(ledger_path)
        assert ledger['status']=='COMPLETED' and ledger['product_key']==j['product_key']
        if ledger.get('acquisition_kind')=='gee_direct_download':
            direct_completed+=1
            assert not ledger.get('task_id')
            assert ledger['online_eecu_usage_seconds'] is None and not ledger['online_eecu_usage_measured']
            assert len(ledger['request_graph_sha256'])==64
            assert ledger['request_parameters']['crs']==j['grid']['crs']
            assert ledger['request_parameters']['crs_transform']==j['crs_transform']
            assert ledger['request_parameters']['dimensions']==[j['grid']['cols'],j['grid']['rows']]
        else:
            batch_completed+=1
            assert ledger.get('task_id') and ledger['cloud_status']['state']=='COMPLETED'
            measured_batch+=ledger['cloud_status'].get('batch_eecu_usage_seconds',0)
        tif=active_downloads/(j['export_prefix']+'.tif');remote=read(tif.with_name(tif.name+'.drive.json'))
        assert folder_id in remote['parents']
        assert hashlib.md5(tif.read_bytes()).hexdigest()==remote['md5Checksum']
        assert file_hash(tif)==validation['source_tif_sha256']==file_hash(dest/'source.tif')
        if ledger.get('acquisition_kind')=='gee_direct_download':
            assert ledger['download_sha256']==file_hash(tif)
            assert ledger['drive_file']==remote
        with rasterio.open(dest/'source.tif') as ds:
            assert ds.crs==rasterio.crs.CRS.from_user_input(j['grid']['crs'])
            assert np.allclose(tuple(ds.transform),tuple(Affine(*j['crs_transform'])),rtol=0,atol=1e-7)
            assert ds.shape==(j['grid']['rows'],j['grid']['cols'])
            bands=ds.read();assert ds.read_masks().all() and np.isfinite(bands).all()
        arrays=[]
        for i,name in enumerate(names):
            p=dest/(name+'.npy');arr=np.load(p,allow_pickle=False)
            assert arr.dtype==np.float32 and np.array_equal(arr,bands[i])
            assert np.isfinite(arr).all() and ((arr>=0)&(arr<=1)).all()
            arrays.append(arr)
            entry=report['group_years'].setdefault(pair,{'group_id':j['group_id'],'year':j['year'],'grid_key':j['grid_key'],'features':{}})
            assert entry['grid_key']==j['grid_key']
            entry['features'][name]={'path':str(p.relative_to(ROOT)),'sha256':file_hash(p),'product_key':j['product_key']}
        coverage=bands[len(names)]
        assert (coverage>=1-1e-6).all() and (coverage<=1+1e-6).all()
        if run=='mapbiomas':
            if repair:
                assert bands.shape[0]==9
                observed,imputed=bands[7],bands[8]
                assert np.allclose(bands[3:7].sum(axis=0),observed,rtol=0,atol=1e-6)
                assert np.allclose(observed+imputed,coverage,rtol=0,atol=1e-6)
                assert np.argwhere(imputed>1e-6).tolist()==[[20,13]]
                assert 0.0034<float(imputed[20,13])<0.00342
                assert (arrays[0]+arrays[1]+bands[6]+imputed<=1+1e-6).all()
                temporal_repairs.append({'job_id':key,'plan':str(active_bundle/'plan.json'),
                    'plan_sha256':file_hash(active_bundle/'plan.json'),'original_product_key':base_job['product_key'],
                    'approval_sha256':repair_plan['approval_sha256'],'imputed_model_cells':1,
                    'imputed_projected_area_m2':float(imputed.astype(float).sum()*250000),
                    'observed_coverage_min':float(observed.min()),'effective_coverage_min':float(coverage.min())})
            else:
                assert np.allclose(bands[3:].sum(axis=0),coverage,rtol=0,atol=1e-6)
                assert (arrays[0]+arrays[1]+bands[6]<=1+1e-6).all()
            count=int(np.count_nonzero(bands[6]>1e-6))
            if count:
                assert j['group_id']=='G115'
                fallback.append({'group_id':j['group_id'],'year':j['year'],'cells':count,
                                 'projected_area_m2':float(bands[6].astype(float).sum()*250000)})
    assert np.isclose(measured_batch,acquisition.get('reported_batch_eecu_usage_seconds',acquisition.get('batch_eecu_usage_seconds')),rtol=0,atol=1e-8)
    report['runs'][run]={'plan_sha256':file_hash(ROOT/'gee'/folder/'jobs/plan.json'),
                         'completed_jobs':len(ready),'expected_jobs':24,'batch_eecu_usage_seconds':measured_batch,
                         'drive_folder_id':folder_id,'fallback':fallback,'temporal_repairs':temporal_repairs,
                         'batch_completed_jobs':batch_completed,'direct_completed_jobs':direct_completed,
                         'independently_summed_batch_eecu_usage_seconds':measured_batch,
                         'online_eecu_usage_seconds':None,'online_eecu_usage_measured':False}
features={'grassland_fraction','flooded_habitat_fraction','shrubland_fraction'}
missing=[]
for group,year in sorted(expected):
    pair=f'{group}_{year}'
    present=set(report['group_years'].get(pair,{}).get('features',{}))
    if not args.allow_incomplete: assert present==features
    if features-present: missing.append({'group_id':group,'year':year,'features':sorted(features-present)})
report.update(group_count=len({g for g,y in expected}),group_year_count=len(expected),feature_array_count=sum(len(x['features']) for x in report['group_years'].values()),
              expected_feature_array_count=72,missing=missing,
              batch_eecu_usage_seconds=sum(v['batch_eecu_usage_seconds'] for v in report['runs'].values()),
              status='all groups/years/features, hashes, spatial grids, source provenance and completed acquisition identities verified',
              completed_direct_jobs=sum(v['direct_completed_jobs'] for v in report['runs'].values()),
              online_eecu_usage_seconds=None,online_eecu_usage_measured=False)
prior_path=DATA/'spring_landcover_inventory_partial_v1.json'
if not missing and prior_path.exists():
    prior=read(prior_path);unchanged=0
    for pair,item in prior['group_years'].items():
        for feature,identity in item['features'].items():
            assert report['group_years'][pair]['features'][feature]==identity
            unchanged+=1
    report['prior_ready_arrays_verified_unchanged']=unchanged
    report['prior_partial_inventory_sha256']=file_hash(prior_path)
if missing: report['status']='PARTIAL: verified ready products only; listed features remain incomplete and excluded'
output=DATA/('spring_landcover_inventory_partial_v1.json' if missing else 'spring_landcover_inventory_v1.json')
write(output,report)
print({k:v for k,v in report.items() if k not in ('group_years','runs')})
