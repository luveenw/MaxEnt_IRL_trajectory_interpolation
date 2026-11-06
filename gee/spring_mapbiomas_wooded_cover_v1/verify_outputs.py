"""Offline complete inventory and independent cross-feature/provenance checks."""
from pathlib import Path
import hashlib,json
import numpy as np
import rasterio
from jaguar_irl.data.pantanal_checkpoint import file_hash
from jaguar_irl.training.shared_storage import read,write
from jaguar_irl.training.terrain_roughness import verify_bundle
from jaguar_irl.training.mapbiomas_wooded_cover import check_pixels
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
DATA=ROOT/'data/pantanal_covariates/spring_mapbiomas_wooded_cover_v1'
plan=verify_bundle(HERE/'jobs');results={};total=0
old=read(DATA/'prior_product_hashes.json')
for name,sha in old.items():
 if file_hash(ROOT/name)!=sha:raise ValueError('Prior product changed: '+name)
for key,j in plan['groups'].items():
 p=DATA/'products'/j['group_id']/str(j['year']);v=read(p/'validation.json');checks=read(p/'checksums.json')
 if any(file_hash(p/name)!=sha for name,sha in checks.items()):raise ValueError('Product checksum mismatch')
 with rasterio.open(p/'source.tif') as ds:
  if list(ds.bounds)!=j['grid']['bounds'] or ds.shape!=(j['grid']['rows'],j['grid']['cols']):raise ValueError('Grid changed')
  data=ds.read();check_pixels(data,ds.read_masks()>0,key)
 a=np.load(p/'forest_savanna_fraction.npy',allow_pickle=False)
 if not np.array_equal(a,data[0]):raise ValueError('NPY/TIFF mismatch')
 others=ROOT/'data/pantanal_covariates/spring_mapbiomas_landcover_v1/products'/j['group_id']/str(j['year'])
 grass=np.load(others/'grassland_fraction.npy',allow_pickle=False);wet=np.load(others/'flooded_habitat_fraction.npy',allow_pickle=False)
 if np.any(a+grass+wet>1+2e-6):raise ValueError('Exclusive classes3/4,12,11 exceed unity')
 ledger=read(DATA/'tasks'/f'{key}.json');tif=DATA/'downloads'/(j['export_prefix']+'.tif')
 if ledger['status']!='COMPLETED' or ledger['download_sha256']!=file_hash(tif):raise ValueError('Incomplete/mismatched ledger')
 remote=ledger['drive_file']
 if remote['md5Checksum']!=hashlib.md5(tif.read_bytes()).hexdigest() or int(remote['size'])!=tif.stat().st_size:raise ValueError('Recorded Drive checksum mismatch')
 total+=a.size
 results[key]=dict(product_key=j['product_key'],array_path=str(p/'forest_savanna_fraction.npy'),sha256=file_hash(p/'forest_savanna_fraction.npy'),
  cells=a.size,minimum=float(a.min()),maximum=float(a.max()),mean=float(a.mean()),imputed_cells=v['imputed_cells'],imputed_projected_area_m2=v['imputed_projected_area_m2'],
  drive_file_id=remote['id'],cross_feature_sum_max=float((a+grass+wet).max()))
summary=dict(schema='mapbiomas_wooded_cover_verification/1',status='COMPLETE',group_count=plan['group_count'],group_year_count=len(results),feature_array_count=len(results),
 total_cells=total,prior_product_files_verified_unchanged=len(old),full_coverage=True,original_archive_preserved=True,products=results,
 source_fingerprint=plan['source_snapshot']['asset_fingerprint'],plan_sha256=file_hash(HERE/'jobs/plan.json'),
 scientific_validation='not established; software checks only',online_eecu_usage_measured=False,online_eecu_usage_seconds=None)
write(DATA/'verification.json',summary)
print(json.dumps({k:v for k,v in summary.items() if k!='products'},indent=2))
