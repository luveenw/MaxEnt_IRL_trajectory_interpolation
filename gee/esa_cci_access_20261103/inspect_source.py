from pathlib import Path
REPO = next(p for p in Path(__file__).resolve().parents if (p/'jaguar_irl').is_dir() and (p/'data').is_dir())
DATA_ROOT = REPO/'data/pantanal_covariates/esa_cci_access_20261103'
SCRIPT_ROOT = REPO/'gee/esa_cci_access_20261103'
import json
from pathlib import Path
import rasterio
from rasterio.windows import from_bounds
from pyproj import Transformer
root=DATA_ROOT
repo=REPO
plan=json.loads((repo/'gee/spring_srtm_roughness_v1/jobs/plan.json').read_text())
t=Transformer.from_crs(32721,4326,always_xy=True)
points=[]
for job in plan['groups'].values():
 a,b,c,d=job['grid']['bounds']; points.extend(t.transform(x,y) for x,y in ((a,b),(a,d),(c,b),(c,d)))
bounds=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
url='https://dap.ceda.ac.uk/neodc/esacci/land_cover/data/land_cover_maps/v2.0.7/ESACCI-LC-L4-LCCS-Map-300m-P1Y-2005-v2.0.7.tif'
with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif',GDAL_HTTP_TIMEOUT='60'):
 with rasterio.open('/vsicurl/'+url) as ds:
  window=from_bounds(*bounds,ds.transform).round_offsets().round_lengths()
  report=dict(url=url,source=dict(shape=ds.shape,crs=str(ds.crs),transform=list(ds.transform),dtype=ds.dtypes,nodata=ds.nodata,block_shapes=ds.block_shapes,tags=ds.tags()),requested_bounds=bounds,window=dict(col_off=window.col_off,row_off=window.row_off,width=window.width,height=window.height))
  (root/'source_inspection.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2),flush=True)
