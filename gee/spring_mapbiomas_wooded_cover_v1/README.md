# Spring forest/savanna classified-area cache

This versioned recipe extracts MapBiomas classes3+4 only, excluding6/7, for all24
observed Spring group/year combinations on13 exact saved padded500m EPSG32721
grids. The output `forest_savanna_fraction.npy` is classified-area fraction0–1,
not continuous canopy closure or tree-height-filtered canopy. Multiply by100
only when reporting percent area. National descriptions include tree/shrub mixtures.

Source priority and native categorical alignment match the existing grassland/
narrow-flooded workflow: BrazilC11v3, ParaguayC3v1, BoliviaC4v1. ChacoC5integrationv2
class26 supplies non-target water only where national data are unavailable. A
selected unknown class fails coverage QA rather than falling through. Binary
membership is overlap-area-averaged to500m, without added smoothing. Full5km
padding is already part of checkpoint grids. Annual maps apply throughout
Aug15–Nov14, without claiming sub-season observations. All years remain shared
cache products, independent of train/test allocations.

G316/2011 reuses the approved exact-native-pixel repair: retrieve real Brazil2010
and2012 classifications; require both observed and equal4 at col60974,row86248,
with no current source. The retrieved class4 contributes ONE to this feature.
The generated JavaScript includes this actual retrieval and explanatory comment.
The acquisition runtime also checks the live one-pixel consensus separately.
No other temporal interpolation is allowed.

Eight TIFF bands: forest/savanna fraction, effective-valid fraction, observed
Brazil/Paraguay/Bolivia/Chaco source fractions, observed-valid fraction, temporal-
imputed fraction. Country fractions sum to observed coverage; observed plus
imputed equals effective coverage. The sole imputed500m cell is G316 row20,col13.

Code lives here and in `jaguar_irl/training/mapbiomas_wooded_cover.py`; all data,
identity snapshots, TIFFs, NPYs and durable ledgers live under
`data/pantanal_covariates/spring_mapbiomas_wooded_cover_v1`.
Drive destination:
`columbia_ma_thesis/jaguar_irl/seasonal_covariates/pantanal_spring_mapbiomas_wooded_cover_v1`.
Project:`perceptive-ivy-780`; script repo:`users/luveenw/ColumbiaMAThesis`.

From repo root with the isolated EE environment:

```bash
PYTHONPATH="$PWD" /tmp/pantanal-gee-venv/bin/python gee/spring_mapbiomas_wooded_cover_v1/setup_cloud.py
PYTHONPATH="$PWD" /tmp/pantanal-gee-venv/bin/python gee/spring_mapbiomas_wooded_cover_v1/acquire.py --pilot-only
PYTHONPATH="$PWD" /tmp/pantanal-gee-venv/bin/python gee/spring_mapbiomas_wooded_cover_v1/acquire.py
PYTHONPATH="$PWD" /tmp/pantanal-gee-venv/bin/python gee/spring_mapbiomas_wooded_cover_v1/verify_outputs.py
```

The frozen jobs bundle was prepared using `mapbiomas_wooded_cover.prepare` with
the saved checkpoint and source snapshot. Do not regenerate it in place after
changing code/source identity; create a new version. The sequential direct
transport uses the existing verified GEE helper, hashes exact request graphs,
validates TIFFs before uploading, and verifies Drive size/MD5/parent. It does not
invent batch task IDs. Interactive EECU use is unmeasured. Resume the same command
with existing ledgers; do not delete ledgers or blindly retry uncertain uploads.
A failed QA leaves evidence intact and stops acquisition. Source fingerprints,
recipe/dependency hashes and approval identity are checked before running.

Four local tests check provenance sums, missing coverage, exact repair scope and
its feature contribution, and unchanged24 candidate grids/years. The independent
output verifier checks every array/TIFF/grid, source/imputation coverage, Drive
recorded checksums, prior product hashes, and forest+grass+flooded<=1 per cell.
All are software checks; ecological classification accuracy remains unvalidated.

## Completed production run

2026-11-04: all24 jobs completed, producing24 NPY features and24 eight-band
TIFFs across13 grids /100,402 cells. `verification.json` passed complete effective
coverage, geometry, ranges, observed/source/imputed identities and cross-feature
exclusivity. All295 previously pinned roughness/grassland/wetland/shrubland product
files remain byte-for-byte unchanged. G316's approved repair affects exactly one
model cell (approximately851.47m²); its retrieved class4 is included in wooded area.

All24 TIFFs were uploaded with size/MD5/parent verification to Drive leaf
`1uDHZKP_OT8a-M71oSMs-RXVsvhwToGjo`. The JavaScript is published and remote-hash
verified at `seasonal_covariates/pantanal_spring_mapbiomas_wooded_cover_v1/extract_wooded_cover`
in the requested EE repository, commit`e7f8f842054c5f0eafb986f5edc19c13851d9420`.
The data archive's `manifest.json` records checksums, code identity and publication.
Four targeted tests passed; no ecological accuracy validation or fitted model is
claimed. Interactive EECU remains unmeasured, not zero.

The output feature key is `forest_savanna_fraction`; mapping it to the legacy
training template key `tree_cover` must retain this categorical-proxy definition.
No split allocation, representative-year choice, feature binding or training was
performed. The inherited frozen plan's advisory `year_policy` text comes from
the earlier candidate-year helper; current train/test-context selection rules
are in the maintained manual. That text does not confer split ownership on data.
