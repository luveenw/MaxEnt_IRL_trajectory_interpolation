"""Compare the documented Trends.Earth mirror to an official native ESA pilot."""
from pathlib import Path
REPO = next(p for p in Path(__file__).resolve().parents if (p/'jaguar_irl').is_dir() and (p/'data').is_dir())
DATA_ROOT = REPO/'data/pantanal_covariates/esa_cci_access_20261103'
SCRIPT_ROOT = REPO/'gee/esa_cci_access_20261103'
import json,requests,hashlib
from pathlib import Path
import numpy as np
import rasterio
import ee
root=DATA_ROOT
meta=json.loads((root/'pilot_metadata.json').read_text())
ee.Initialize(project='perceptive-ivy-780')
asset='users/geflanddegradation/toolbox_datasets/lcov_esacc_1992_2022'
img=ee.Image(asset).select('y2005').rename('lccs_class')
url=img.getDownloadURL({'crs':meta['crs'],'crs_transform':meta['transform'][:6],'dimensions':[meta['shape'][1],meta['shape'][0]],'format':'GEO_TIFF'})
p=root/'trends_earth_esa_cci_y2005_native_comparison.tif'
r=requests.get(url,timeout=120);r.raise_for_status();p.write_bytes(r.content)
with rasterio.open(root/'esa_cci_v207_2005_spring_domain_access_pilot.tif') as a,rasterio.open(p) as b:
 va=a.read(1);vb=b.read(1)
 result=dict(asset=asset,band='y2005',official_source=meta['source_url'],official_subset_sha256=meta['sha256'],mirror_download_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),official_shape=list(a.shape),mirror_shape=list(b.shape),official_transform=list(a.transform),mirror_transform=list(b.transform),crs_match=a.crs==b.crs,transforms_match=np.allclose(tuple(a.transform),tuple(b.transform),atol=1e-10,rtol=0),nodata_official=a.nodata,nodata_mirror=b.nodata)
 if va.shape==vb.shape:
  result.update(mask_mismatched_pixels=int(np.count_nonzero((a.read_masks(1)>0)!=(b.read_masks(1)>0))),official_valid_pixels=int((a.read_masks(1)>0).sum()),mirror_valid_pixels=int((b.read_masks(1)>0).sum()),total_pixels=va.size,mismatched_pixels=int(np.count_nonzero(va!=vb)),mirror_classes={str(int(v)):int(n) for v,n in zip(*np.unique(vb,return_counts=True))},all_values_identical=bool(np.array_equal(va,vb)))
(root/'mirror_comparison.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
