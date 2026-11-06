"""Read a small actual Spring window from official release using HTTP byte ranges."""
import json,os
from pathlib import Path
import rasterio,numpy as np
from rasterio.windows import from_bounds
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/pantanal_covariates/globpop_production_review_20261104'
meta=json.loads((OUT/'zenodo_latest.txt').read_text());f=next(x for x in meta['files']if 'Density_30arc_2011' in x['key']);url=f['links']['self']
p=json.loads((ROOT/'data/pantanal_covariates/globpop_access_20261104/pilots.json').read_text())['G316_2011'];bounds=Transformer.from_crs(p['grid']['crs'],4326,always_xy=True).transform_bounds(*p['grid']['bounds'],densify_pts=21)
with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',CPL_VSIL_CURL_ALLOWED_EXTENSIONS='content',GDAL_HTTP_TIMEOUT='45',GDAL_HTTP_MAX_RETRY='1'):
 with rasterio.open('/vsicurl/'+url) as ds:
  w=from_bounds(*bounds,transform=ds.transform);c0=int(np.floor(w.col_off));r0=int(np.floor(w.row_off));c1=int(np.ceil(w.col_off+w.width));r1=int(np.ceil(w.row_off+w.height));win=rasterio.windows.Window(c0,r0,c1-c0,r1-r0)
  a=ds.read(1,window=win);np.save(OUT/'official_G316_2011.npy',a)
  result={'url':url,'record_version':meta['metadata'].get('version'),'filename':f['key'],'archive_checksum':f['checksum'],'source_shape':ds.shape,'source_transform':list(ds.transform),'nodata':ds.nodata,'window':[c0,r0,c1-c0,r1-r0],'window_bounds':list(ds.window_bounds(win)),'window_shape':a.shape,'minimum':float(np.nanmin(a)),'maximum':float(np.nanmax(a))}
(OUT/'official_window_metadata.json').write_text(json.dumps(result,indent=2)+'\n');print(result,flush=True)
