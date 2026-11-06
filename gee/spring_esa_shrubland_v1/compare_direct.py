"""Compare normal direct small-raster output with the already validated batch pilot."""
from pathlib import Path
import hashlib,json
import ee,numpy as np,rasterio,requests
from jaguar_irl.training.shared_storage import read,write
from jaguar_irl.training.shrubland import build_ee_image
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent;DATA=ROOT/'data/pantanal_covariates/spring_esa_shrubland_v1'
plan=read(HERE/'jobs/plan.json');key=plan['default_pilot_job'];j=plan['groups'][key]
ee.Initialize(project='perceptive-ivy-780');im=build_ee_image(ee,j)
params={'crs':j['grid']['crs'],'crs_transform':j['crs_transform'],'dimensions':[j['grid']['cols'],j['grid']['rows']],'format':'GEO_TIFF','name':'direct_batch_comparison'}
f=DATA/'direct_batch_comparison.tif'
if not f.exists():
    u=im.getDownloadURL(dict(params))
    try:r=requests.get(u,timeout=300)
    except Exception:raise RuntimeError('Direct comparison request failed; signed URL suppressed') from None
    if r.status_code!=200:raise RuntimeError('Non-success direct comparison response; URL suppressed')
    f.write_bytes(r.content)
batch=DATA/'products'/j['group_id']/str(j['year'])/'source.tif'
with rasterio.open(f) as a,rasterio.open(batch) as b:
    av,bv=a.read(),b.read();report=dict(job_id=key,direct_shape=list(av.shape),batch_shape=list(bv.shape),
        crs_match=a.crs==b.crs,transform_match=a.transform==b.transform,masks_match=bool(np.array_equal(a.read_masks(),b.read_masks())),
        mismatched_values=int(np.count_nonzero(av!=bv)),maximum_absolute_difference=float(np.max(np.abs(av-bv))),
        direct_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),batch_sha256=hashlib.sha256(batch.read_bytes()).hexdigest(),
        request_parameters=params,online_eecu_usage_seconds=None)
    assert report['crs_match'] and report['transform_match'] and report['masks_match'] and report['maximum_absolute_difference']<=1e-7
write(DATA/'direct_batch_comparison.json',report);print(json.dumps(report,indent=2))
