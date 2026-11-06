"""Retrieve an official native-grid ESA CCI subset; no map-year allocation implied."""
import json, math, hashlib, os
from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import from_bounds,Window
from rasterio.shutil import copy as rio_copy
import ee
from google.cloud import storage
root=Path(__file__).resolve().parent
meta=json.loads((root/'source_inspection.json').read_text());url=meta['url']
a,b,c,d=meta['requested_bounds']; bounds=[a-.02,b-.02,c+.02,d+.02]
out=root/'esa_cci_v207_2005_spring_domain_access_pilot.tif'
if not out.exists():
 with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif',GDAL_HTTP_TIMEOUT='60'):
  with rasterio.open('/vsicurl/'+url) as ds:
   w=from_bounds(*bounds,ds.transform); c0=math.floor(w.col_off);r0=math.floor(w.row_off);c1=math.ceil(w.col_off+w.width);r1=math.ceil(w.row_off+w.height)
   w=Window(c0,r0,c1-c0,r1-r0);data=ds.read(1,window=w)
   profile=ds.profile.copy();profile.update(height=data.shape[0],width=data.shape[1],transform=ds.window_transform(w),compress='LZW',tiled=True,blockxsize=256,blockysize=256)
   pending=root/'.pending-pilot.tif'
   with rasterio.open(pending,'w',**profile) as dst:dst.write(data,1);dst.set_band_description(1,'lccs_class');dst.update_tags(**ds.tags())
  rio_copy(pending,out,driver='COG',compress='LZW',blocksize=256,overview_resampling='nearest');pending.unlink()
with rasterio.open(out) as ds:
 data=ds.read(1);values,counts=np.unique(data,return_counts=True)
 metadata=dict(source_url=url,source_version='2.0.7',year=2005,purpose='access pilot only; not a training map-year decision',sha256=hashlib.sha256(out.read_bytes()).hexdigest(),size_bytes=out.stat().st_size,shape=list(ds.shape),crs=str(ds.crs),transform=list(ds.transform),bounds=list(ds.bounds),nodata=ds.nodata,classes={str(int(v)):int(n) for v,n in zip(values,counts)})
(root/'pilot_metadata.json').write_text(json.dumps(metadata,indent=2));print('Pilot:',json.dumps(metadata),flush=True)
c=ee.data.get_persistent_credentials();client=storage.Client(project='perceptive-ivy-780',credentials=c)
for name in ('jour-22','vfaes'):
 b=client.get_bucket(name);print('Bucket:',name,'projectNumber',b._properties.get('projectNumber'),flush=True)
 if str(b._properties.get('projectNumber'))!='649987002740':continue
 key='columbia_ma_thesis/jaguar_irl/esa_cci_access_20261103/'+out.name
 blob=b.blob(key)
 if blob.exists():
  blob.reload()
  if blob.metadata and blob.metadata.get('sha256')!=metadata['sha256']:raise ValueError('Existing staging object differs')
 else:
  blob.metadata={'sha256':metadata['sha256'],'source_url':url,'source_version':'2.0.7','year':'2005'}
  blob.upload_from_filename(out,if_generation_match=0)
 blob.reload();stage=dict(bucket=name,project_number=b._properties.get('projectNumber'),object=key,uri=f'gs://{name}/{key}',generation=blob.generation,size=blob.size,md5_hash=blob.md5_hash,sha256=metadata['sha256'])
 (root/'staging.json').write_text(json.dumps(stage,indent=2));print('Staged:',json.dumps(stage),flush=True);break
else:raise RuntimeError('No verified same-project staging bucket')
