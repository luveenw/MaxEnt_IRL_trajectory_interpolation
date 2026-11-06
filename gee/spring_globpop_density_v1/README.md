# Spring GlobPOP density with approved same-year LandScan fallback

Completed2026-11-04:24 candidate group/year pairs,13 saved padded500m grids,
24four-band GeoTIFFs and24 `human_population_density.npy` arrays. Products are
shared across train/test/folds. No animal allocation, selected representative
year, feature binding, ecological fit or evaluation was performed here.

## Source and scientific contract

- Published GlobPOP Float32 `b1`, people/km²,30arc-second native angular lattice:
  `projects/sat-io/open-datasets/GLOBPOP_DENSITY`, explicit calendar-year selection.
- Missing/masked/nonfinite source values are permitted only at the exact approved
  native coordinates copied into `jobs/approved_gap_footprints.json`. Actual
  same-year LandScan `b1` counts must be observed, finite and exactly0. Count0
  divided by full native WGS84 physical area is density0. Every finite observed
  nonnegative GlobPOP value is retained, including small positive values.
- Finite negative observations fail rather than becoming missing-value fills.
- LandScan annual grid origins differ; the actual annual projection is used.
  Native GEE extraction aligns LandScan by that projection before sampling.
- The412 approved native pixel-years span G057/2013–2015 (132 each),G286/2010(13),
  G316/2011(3). No generic `NoData ->0` rule is used. New/changed gaps fail.
- Modern GHSL corroborates these zero estimates. Source estimates do not prove
  human absence. LandScan is24h ambient population and has integer quantization.
  GlobPOP's land-only versus full-pixel density denominator was not reconstructed;
  this is a physical-area-weighted mean of the published density surface, not a
  claim of population conservation or a pure resident census at500m.
- Each annual surface applies throughout its Spring, Aug15–Nov14, as a constant
  annual approximation. No intra-season population observations are inferred.
- Immutable official reference: https://zenodo.org/records/11179644 . The pinned
  source snapshot records official filenames/checksums. Only a bounded440pixel
  G316/2011 window was previously shown exactly equivalent to the GEE mirror,
  not the entire global archive or all years. Release-label ambiguity is retained.

## Exact-grid spatial processing and output bands

The native source is coarser than500m. Therefore final raster generation does
**not** use center assignment, bilinear interpolation or `reduceResolution` to
upsample. `acquire.py` retrieves raw density/masks/native coordinates and actual
LandScan values from GEE, retains their NaNs, then performs local polygon-overlap
integration. Each native angular edge is densified into64segments before UTM
intersection. Intersection areas are measured on the WGS84 ellipsoid. The sum
is independently checked against physical target-cell areas (rtol2e-7,atol.02m²).
All observed plus fallback contributions form the denominator; missing areas
are never silently removed by conditional renormalization. No extra smoothing,
log transform or learned scaling is applied.

The TIFF bands are:

1. `human_population_density`: overlap-weighted density, people/km².
2. `globpop_observed_fraction`: fraction supported by original finite GlobPOP.
3. `landscan_fallback_fraction`: fraction supported by approved actual LandScan0.
4. `effective_valid_fraction`:1 throughout every output model cell.

A mixed target cell may retain positive density even if part of it receives
fallback0. The four bands use Float32, exactly the saved EPSG32721 bounds/affine;
all valid zeros remain valid data, with-9999 reserved as NoData. The NPY stores
band1 only. Existing grids already include the ecologically selected5km padding.

`jobs/plan.json` inherits some unused compatibility fields from the original
candidate-grid inventory, notably `source_band='classification_YYYY'`. This field
is NOT consumed by the population driver or JS. Both select actual population
band `b1` from `density_asset` and `landscan_asset`. `compatibility_metadata.json`
records this explicitly without modifying frozen plans or products.

## Reproduction and recovery

From the repository root, with `PYTHONPATH="$PWD"`:

```bash
/tmp/pantanal-gee-venv/bin/python gee/spring_globpop_density_v1/acquire.py --pilot-only
/tmp/pantanal-gee-venv/bin/python gee/spring_globpop_density_v1/acquire.py
/tmp/pantanal-gee-venv/bin/python gee/spring_globpop_density_v1/verify_outputs.py
/tmp/pantanal-gee-venv/bin/python -m pytest jaguar_irl/training/test_globpop_density.py -q
```

`setup_cloud.py` pins source metadata/approval and creates the Drive leaf; reruns
reject different frozen inputs. The pilot isG057/2013. Complete source metadata,
approval and software hashes are checked before acquisition. Cached native NPZs
and sparse overlap maps have checksums and lattice signatures; reuse does not
requery native values. Unexpected changes fail. Product directories are published
atomically and checksummed. Drive ledger reconciles exact filenames/content;
uncertain uploads must not be blindly retried. Missing metadata/cache sidecars
require investigation rather than silent recreation. Historical pre-pilot adapter
errors and the preserved initial plan are documented in `prepilot_recovery.json`.
The final numerical module/plan were frozen before the successful pilot/full run.

Data/provenance:
`data/pantanal_covariates/spring_globpop_density_v1/`.
`native/` retains original NaNs, `overlaps/` sparse geometric weights,
`products/GROUP/YEAR/` immutable final outputs, `tasks/` Drive ledgers,
`downloads/` unambiguous upload filenames. `verification.json` is the authoritative
complete product inventory. `source_snapshot` is embedded in `jobs/plan.json`.

Drive leaf: `pantanal_spring_globpop_density_v1`, ID
`1YvVeDG0UkbJe48a75wQ6SL49BOprNy47`, under
`columbia_ma_thesis/jaguar_irl/seasonal_covariates`.

## Published GEE JavaScript

`jobs/extract_population_density.js` is directly executable in GEE Code Editor:

https://code.earthengine.google.com/?scriptPath=users%2Fluveenw%2FColumbiaMAThesis%3Aseasonal_covariates%2Fpantanal_spring_globpop_density_v1%2Fextract_population_density

It exposes/exports native raw/guarded source bands, with a one-task default bound.
Final500m physical-overlap processing is explicitly local; the JS does not pretend
that a coarse-to-fine reducer reproduces it. Publishing is separate from manually
running native exports. Production used native GEE `sampleRectangle` requests,
then locally generated final TIFFs uploaded with checksum verification. There
were no batch export tasks, so interactive EECU remains unmeasured/null. JS syntax
and published bytes were checked; interactive Code Editor UI rendering was not
claimed tested. `publication.json` records verifiedcommit/path/hash.

## Verification

Five focused tests passed: sparse positive preservation, observed/fallback area
weighting, guarded source zero/mask requirements, bad unneeded bbox-corner
exclusion, finite negative rejection and curved native/metric partition coverage.
Full offline verification passed all24products/100402cells;412nativepixel-year
fallbacks affect1745target-cell-years. Independent limiting checks cover19306
whole-observed-native target cells and266 whole-fallback target cells;763 cells
have mixed observed/fallback areas. Whole fallback cells crossing several native
fallback pixels are also validated through reconstruction. Source, geometry,
plan/product and Drive-record hashes were checked, along with404 prior product
files unchanged. Ecological accuracy and interpolation performance were not
established by these software checks.
