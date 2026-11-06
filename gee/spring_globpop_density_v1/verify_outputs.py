"""Offline full artifact/source/geometry/repair/Drive-record verification."""
from pathlib import Path
import hashlib,json
import numpy as np,rasterio
from affine import Affine
from jaguar_irl.data.pantanal_checkpoint import file_hash
from jaguar_irl.training.shared_storage import read,write
from jaguar_irl.training.globpop_density import aggregate,BANDS
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;BUNDLE=HERE/'jobs';DATA=ROOT/'data/pantanal_covariates/spring_globpop_density_v1'
plan=read(BUNDLE/'plan.json');prior=read(DATA/'prior_product_hashes.json');previous=read(ROOT/'data/pantanal_covariates/globpop_production_review_20261104/finite_coverage_summary.json')
for name,sha in prior.items():
 if file_hash(ROOT/name)!=sha:raise ValueError('Prior product archive changed: '+name)
if file_hash(ROOT/'jaguar_irl/training/globpop_density.py')!=plan['software_sha256']:raise ValueError('Numerical source changed')
if file_hash(BUNDLE/'approval.json')!=plan['approval_sha256']or file_hash(BUNDLE/'approved_gap_footprints.json')!=plan['gaps_sha256']:raise ValueError('Approval copy changed')
results={};total=0;native_fills=0;filled_cells=0;physical=0;projected=0;single_observed=0;single_fallback=0;mixed=0
for key,j in plan['groups'].items():
 g=j['grid'];p=DATA/'products'/j['group_id']/str(j['year']);v=read(p/'validation.json');checks=read(p/'checksums.json')
 if any(file_hash(p/name)!=sha for name,sha in checks.items()):raise ValueError('Product checksum mismatch')
 rawpath=DATA/'native'/(key+'.npz');rawmeta=read(rawpath.with_suffix('.json'));geom=DATA/'overlaps'/(j['grid_key']+'.npz');gm=read(geom.with_suffix('.json'))
 if file_hash(rawpath)!=rawmeta['sha256']or file_hash(geom)!=gm['sha256']:raise ValueError('Native or overlap cache changed')
 with np.load(rawpath)as z:raw={k:z[k]for k in z.files}
 with np.load(geom)as z:o={k:z[k]for k in z.files}
 expected,qa=aggregate(raw,o,j['approved_missing_pixels'])
 if v['statistics']!=qa or v['product_key']!=j['product_key']or v['plan_sha256']!=file_hash(BUNDLE/'plan.json'):raise ValueError('Product lineage mismatch')
 with rasterio.open(p/'source.tif')as ds:
  if ds.shape!=(g['rows'],g['cols'])or list(ds.bounds)!=g['bounds']or ds.crs.to_string()!=g['crs']or ds.count!=4:raise ValueError('Grid mismatch')
  if tuple(ds.descriptions)!=tuple(BANDS)or not np.allclose(tuple(ds.transform),tuple(Affine(*j['crs_transform']))):raise ValueError('Affine/band mismatch')
  data=ds.read()
  if not(ds.read_masks()>0).all()or not np.isfinite(data).all():raise ValueError('Incomplete final maps')
  if not np.array_equal(data,expected.astype(np.float32)):raise ValueError('Output differs from raw-source physical integration')
 a=np.load(p/'human_population_density.npy',allow_pickle=False)
 if not np.array_equal(a,data[0]):raise ValueError('NPY/TIFF differ')
 if not np.allclose(data[1]+data[2],1,atol=1e-6,rtol=0)or not(data[3]==1).all():raise ValueError('Observed/fallback coverage mismatch')
 if qa['native_fallback_pixels']!=previous[key]['bad_pixels_intersecting_domain']or qa['fallback_cells']!=previous[key]['affected_target_cells']:raise ValueError('Fallback scope differs from prior source audit')
 if abs(qa['fallback_projected_area_m2']-previous[key]['missing_projected_area_m2'])>.1:raise ValueError('Projected fallback area changed')
 # Cells wholly inside one native source pixel give an independent limiting case.
 counts=np.bincount(o['target'],minlength=a.size);sole=np.flatnonzero(counts==1)
 positions=np.full(a.size,-1,dtype=np.int64);positions[o['target']]=np.arange(len(o['target']))
 for target in sole:
  idx=positions[target];n=o['native'][idx];d=raw['density'].ravel()[n]
  if np.isfinite(d)and raw['density_mask'].ravel()[n]>0:
   if a.ravel()[target]!=np.float32(d):raise ValueError('Observed native value changed in a wholly covered target')
   single_observed+=1
  else:
   if a.ravel()[target]!=0 or data[2].ravel()[target]!=1:raise ValueError('Source-zero wholly covered target invalid')
   single_fallback+=1
 mixed+=int(np.count_nonzero((data[2]>1e-8)&(data[2]<1-1e-8)))
 ledger=read(DATA/'tasks'/(key+'.json'));tif=DATA/'downloads'/(j['export_prefix']+'.tif');remote=ledger['drive_file']
 if ledger['status']!='COMPLETED'or ledger['sha256']!=file_hash(tif)or remote['md5Checksum']!=hashlib.md5(tif.read_bytes()).hexdigest()or int(remote['size'])!=tif.stat().st_size:raise ValueError('Drive record mismatch')
 total+=a.size;native_fills+=qa['native_fallback_pixels'];filled_cells+=qa['fallback_cells'];physical+=qa['fallback_physical_area_m2'];projected+=qa['fallback_projected_area_m2']
 results[key]=dict(product_key=j['product_key'],array_path=str(p/'human_population_density.npy'),sha256=file_hash(p/'human_population_density.npy'),cells=a.size,minimum=float(a.min()),maximum=float(a.max()),mean=float(a.mean()),drive_file_id=remote['id'],**{k:qa[k]for k in ['native_fallback_pixels','fallback_cells','fallback_physical_area_m2','fallback_projected_area_m2']})
summary=dict(schema='spring_globpop_density_verification/1',status='COMPLETE',group_count=13,group_year_count=len(results),feature_array_count=len(results),total_cells=total,full_coverage=True,
 native_fallback_pixel_years=native_fills,fallback_target_cell_years=filled_cells,fallback_physical_area_m2=physical,fallback_projected_area_m2=projected,
 wholly_single_observed_native_target_checks=single_observed,wholly_fallback_target_checks=single_fallback,mixed_fallback_target_cells=mixed,
 prior_product_files_verified_unchanged=len(prior),original_archive_preserved=True,products=results,plan_sha256=file_hash(BUNDLE/'plan.json'),
 scientific_validation='not established; software numerical/coverage/lineage checks only',online_eecu_usage_measured=False,online_eecu_usage_seconds=None)
if len(results)!=24 or total!=100402 or native_fills!=412 or filled_cells!=1745:raise ValueError('Expected scope differs')
write(DATA/'verification.json',summary)
print(json.dumps({k:v for k,v in summary.items()if k!='products'},indent=2))
