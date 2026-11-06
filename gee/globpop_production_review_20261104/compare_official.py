"""Compare bounded official window and mirror Float32 density values."""
import json,numpy as np
from pathlib import Path
OUT=Path(__file__).resolve().parents[2]/'data/pantanal_covariates/globpop_production_review_20261104'
a=np.load(OUT/'G316_2011_native.npz');d=a['density'].astype('float32');official=np.load(OUT/'official_G316_2011.npy')
r={'window':'G316_2011','shape':list(d.shape),'pixel_count':d.size,'finite_pixels':int(np.isfinite(d).sum()),'nonfinite_pixels':int((~np.isfinite(d)).sum()),'exact_float32_equal_including_nan':bool(np.array_equal(d,official,equal_nan=True)),'maximum_finite_absolute_difference':float(np.nanmax(np.abs(d-official))),'nan_positions_local':np.argwhere(~np.isfinite(d)).tolist(),'count_mask_missing_positions_local':np.argwhere(a['count_mask']<=0).tolist(),'density_mask_claims_valid_at_nan':bool(np.all(a['density_mask'][~np.isfinite(d)]>0)),'scope':'Bounded window equivalence, not global release identity proof.'}
(OUT/'official_mirror_comparison.json').write_text(json.dumps(r,indent=2)+'\n');print(r)
