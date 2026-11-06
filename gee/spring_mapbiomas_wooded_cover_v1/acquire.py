"""Sequential, resumable direct GEE extraction with validated Drive copies."""
import argparse,json
from pathlib import Path
import ee
from jaguar_irl.data.pantanal_checkpoint import digest,file_hash
from jaguar_irl.training.shared_storage import read,write
from jaguar_irl.training.terrain_roughness import verify_bundle
from jaguar_irl.training.gee_direct import acquire_direct
from jaguar_irl.training.mapbiomas_wooded_cover import SOURCES,build_ee_image,convert
from jaguar_irl.training.mapbiomas_temporal_repair import native_repair,APPROVAL
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;BUNDLE=HERE/'jobs'
DATA=ROOT/'data/pantanal_covariates/spring_mapbiomas_wooded_cover_v1'


def run(pilot_only=False):
    plan=verify_bundle(BUNDLE);config=read(DATA/'cloud_setup.json');ee.Initialize(project=config['project'])
    if file_hash(ROOT/'jaguar_irl/training/mapbiomas_wooded_cover.py')!=plan['software_sha256']:raise ValueError('Recipe code changed')
    for name,sha in plan['dependencies_sha256'].items():
        if file_hash(ROOT/'jaguar_irl/training'/name)!=sha:raise ValueError('Dependency changed')
    if file_hash(APPROVAL)!=plan['approval_sha256']:raise ValueError('Repair approval changed')
    if digest({c:ee.data.getAsset(a) for c,a in SOURCES.items()})!=plan['source_snapshot']['asset_fingerprint']:raise ValueError('Live source changed')
    ids=[plan['default_pilot_job']]+[k for k in plan['groups'] if k!=plan['default_pilot_job']]
    if pilot_only:ids=ids[:1]
    prior=read(DATA/'acquisition.json') if (DATA/'acquisition.json').exists() else None
    if prior and prior['plan_sha256']!=file_hash(BUNDLE/'plan.json'):
        raise ValueError('Existing acquisition belongs to another frozen plan')
    complete=dict(prior['groups']) if prior else {}
    for key in ids:
        j=plan['groups'][key]
        if key=='G316_2011':
            chosen,sid,observed,patch,previous,following,base=native_repair(ee)
            xy=ee.Image.pixelCoordinates(base)
            audit=(patch.selfMask().rename('patch').addBands(previous.rename('previous_class')).addBands(following.rename('following_class'))
              .addBands(observed.rename('observed_valid')).addBands(sid.rename('original_source_id')).addBands(xy.floor()))
            result=audit.sample(region=ee.Geometry.Rectangle(j['grid']['bounds'],j['grid']['crs'],False),projection=base,geometries=True).getInfo()
            if len(result['features'])!=1:raise ValueError('Repair scope is not exactly one native pixel')
            p=result['features'][0]['properties']
            if not(p['previous_class']==p['following_class']==4 and p['observed_valid']==p['original_source_id']==0 and p['x']==60974 and p['y']==86248):raise ValueError('Adjacent-year repair guard mismatch')
            write(DATA/'live_G316_consensus_check.json',result)
        product=DATA/'products'/j['group_id']/str(j['year'])
        rec=acquire_direct(ee,build_ee_image(ee,j),j,config['drive_leaf_id'],DATA/'downloads',DATA/'tasks'/f'{key}.json',
          source_identity=plan['source_snapshot']['asset_fingerprint'],validate=lambda tif:convert(BUNDLE,key,tif,product),project=config['project'])
        v=read(product/'validation.json')
        complete[key]=dict(group_id=j['group_id'],year=j['year'],product_key=j['product_key'],product=str(product),npy=str(product/'forest_savanna_fraction.npy'),
          drive_file_id=rec['drive_file']['id'],statistics=v['statistics'],effective_coverage_min=v['effective_coverage_min'],observed_coverage_min=v['observed_coverage_min'],
          imputed_cells=v['imputed_cells'],imputed_projected_area_m2=v['imputed_projected_area_m2'],fallback_cells=v['fallback_cells'])
        write(DATA/'acquisition.json',dict(schema='mapbiomas_wooded_cover_candidate_acquisition/1',status='COMPLETED' if len(complete)==plan['job_count'] else 'PARTIAL',
          completed_jobs=len(complete),expected_jobs=plan['job_count'],group_count=plan['group_count'],groups=complete,plan_sha256=file_hash(BUNDLE/'plan.json'),
          transport='sequential GEE direct downloads, validated before Drive upload',online_eecu_usage_seconds=None,online_eecu_usage_measured=False,
          epoch_role='shared split-independent candidate products',scientific_validation='not established'))
        print(key,'validated; Drive checksum verified',flush=True)
    print('Scope completed',len(complete),'of',plan['job_count'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pilot-only',action='store_true');run(**vars(p.parse_args()))
