# GlobPOP production review: release verification, density semantics and actual gaps

2026-11-04. Read-only research and bounded native-pixel queries. No repair,
production raster, Drive upload or Earth Engine export was performed. Project:
`perceptive-ivy-780`. Code: `gee/globpop_production_review_20261104/`; evidence:
`data/pantanal_covariates/globpop_production_review_20261104/`. This review
corrects the earlier inference that density mask-validity demonstrated complete
finite-value coverage. The cache is split-independent; no animal/year freeze is
required to acquire candidate products.

## Main conclusions

GlobPOP is accessible, annual, and potentially suitable as a published modeled
density surface, but **five of the 24 actual Spring group/year combinations have
nonfinite native values**. In G057 these cover approximately 9.475% of the domain
and include mapped forest, so unrestricted zero fill or water-only explanations
are invalid. These actual gaps, rather than merely release-label uncertainty,
block complete production under the current requirement for finite covariates
at every model cell. Do not replace missing density with zero by default.

Use the Float32 density surface, not rounded Int32 counts. When complete and
properly masked, overlap-area-weighted mean of published density is a defensible
predictor definition without reconstructing counts or claiming population
conservation. Denominator details remain a source interpretation caveat. The
Spring candidate years end in 2015; the paper's reported 2016 fusion-weight
changes matter to later seasonal work, not this Spring cache.

## Release identity: a concrete official comparison

The [author README](https://github.com/lulingliu/GlobPOP/blob/main/README.md)
cites record11179644 as release3.0, while the [immutable Zenodo record/API](https://zenodo.org/records/11179644)
labels its version2.0. We retained the actual API response rather than resolving
this disagreement by guessing. Cite record/DOI and filename/checksum, and disclose
the label discrepancy. The GEE mirrors expose no clear source-release property.

We read only the official G316/2011 source window via HTTP byte ranges:22columns
by20rows from `GlobPOP_Density_30arc_2011_F32.tiff`. Its archived full-file checksum
is `md5:c67feaa1c77bd87dad388c610cf4cff3`; the full file was not downloaded.
Native affine and dimensions match the mirror. **All440 source pixels match GEE
exactly as Float32, including three NaNs; maximum finite absolute difference0.**
This validates that bounded source window, not global equivalence of every year.
Retained official header, metadata, subset and comparison allow reproduction.

## The mask issue and corrected all-Spring scope

The density mirror's mask is1 at native NaNs; the count mirror masks those same
locations. Consequently earlier nearest-center mask checks were insufficient.
G316's three native NaNs explain the count mirror's seven missing target centers.
Production must check finite numerical values as well as masks. Local downloaded
arrays use `numpy.isfinite`; an EE finite-value expression needs verification
rather than assuming `mask()` alone is enough.

We downloaded all24 actual native density rectangles, checked masks/finite values,
and intersected invalid source-cell footprints with target500m cells. Source
edges were densified with32segments per edge and transformed into EPSG32721.
Areas below are projected target-grid areas, not claims of exact ellipsoidal
physical area; tiny numerical fraction excesses above1 are rounding artifacts.
The production integration should retain its declared physical-area convention.

| Domain/year | Invalid native pixels intersecting domain | Affected500m cells | Missing area, km² | Domain missing fraction |
|---|---:|---:|---:|---:|
| G057/2013 |132|554|108.014733|9.47498%|
| G057/2014 |132|554|108.014733|9.47498%|
| G057/2015 |132|554|108.014733|9.47498%|
| G286/2010 |13|64|8.226835|2.52745%|
| G316/2011 |3|19|2.137853|0.66034%|

The other19 pairs are finite/mask-valid over their intersecting native cells.
Each affected domain includes wholly uncovered target cells; ignoring missing
fractions and renormalizing over observed portions cannot produce a complete
map. The132 G057 pixels are the same in all three tested candidate years.

G316 native indices are source column/row `(14698,12930)`, `(14702,12937)` and
`(14702,12940)`, with center lon/lat respectively
`(-57.5125,-17.7541666667)`, `(-57.4791666667,-17.8125)` and
`(-57.4791666667,-17.8375)`. All three are NaN in2009,2010,2011,2012 and2013.
Temporal interpolation from neighboring years cannot repair them. The initial
`sampleRegions` adjacent-year attempt returned empty features; native rectangles
were subsequently inspected to establish the actual NaNs, not inferred from
that empty response alone.

## Water context: mixed evidence, not one universal repair

We sampled official [GPW land area](https://developers.google.com/earth-engine/datasets/catalog/CIESIN_GPWv411_GPW_Land_Area),
[water area](https://developers.google.com/earth-engine/datasets/catalog/CIESIN_GPWv411_GPW_Water_Area)
and water-mask products at all146 unique native gap centers (G286/G316 share two).
Using the official legend (0=total water/ice,1=mixed,2=land,3=ocean), there
are20 total-water/ice centers,57 mixed and69 land centers.

We also calculated Brazil Collection11 class fractions over the actual native
gap footprints, using the corresponding year and native categorical grid:

- G316/2011: all three footprints100%MapBiomas33 water; GPW land_area0 and
  water_area approximately0.819km² each. A declared zero-human-density water
  convention is a plausible targeted treatment here, not a temporal repair.
- G286/2010:13footprints mean99.99195%water; the least-water footprint is99.8954%
  water, with the remainder class11. They are nearly, but not entirely, water.
- G057/2013:132footprints mean12.5962%water,5.4179%class11 wetland and36.4208%
  forest/savanna3+4. Some are100%forest/savanna. Missingness cannot be explained
  or repaired uniformly as open water. Classification fractions provide context,
  not direct observations of population. The zero-gap causal mechanism is not
  established by these correlations.

## Density denominator and integer counts

The [author conversion code](https://github.com/lulingliu/GlobPOP/blob/main/Step2_model_estimation/Convert%26export_GlobPOP_density.py)
divides modeled count by a layer matching `Area*`, then exports density Float32
and count Int32. The earlier preprocessing script calls that multiplier landarea
but does not identify the input raster. The paper describes a surface-area
layer and cites the GPW Land/Water Area product; this does not fully resolve
which layer/area convention was used.

Counts are compatible with rounding small fractional populations: in the three
pilot rectangles, density multiplied by full WGS84 pixel area and rounded agrees
with824/825,924/924 and437/437 valid integer count cells respectively. The one
mismatch is close to a half-person rounding boundary and could reflect area
convention differences. This is diagnostic evidence, not a proof of the global
denominator. It explains why many positive densities become zero integer counts.
Do not recover sparse-landscape density by dividing the rounded count asset.

## A tested fallback that is insufficient

Nearest-epoch GPW density was queried at the missing native centers:

- G316:2010GPW density is0 at all3centers.
- G286:2010GPW has11zeros and2positive densities, maximum0.00533363people/km².
- G057:2015GPW has121masked centers,8zeros and3positive densities, maximum
  0.176644people/km².

Therefore GPW does not fill the problematic G057 domain; do not promise that
fallback without more investigation. A targeted annual WorldPop or LandScan
coverage audit could provide a distinct source fallback, but requires explicit
units/area integration, version and predictor-definition review. Spatial
interpolation across108km² of G057 is not a small isolated-pixel repair and
should not be presented as harmless. Adjacent-year interpolation is unsupported
for persistent gaps. Using only observed area is also incomplete because some
cells have no observations.

## Recommended next decision

Proceed with MapBiomas production independently. For population, retain GlobPOP
as a candidate published-density surface and investigate a complete alternate
source for the five affected pairs or the missing footprints, rather than
silently imputing values. A declared water-zero convention can address confirmed
water footprints but does not resolve G057. Whether to use a versioned fallback
mosaic or a single complete alternative remains a scientific source choice.
No population production should claim complete coverage until that decision and
all-cell finite coverage QA pass.

## Reproduction

`probe_semantics.py`: native density/count/mask arrays; corrected unsigned-mask
sentinel cast. `official_window.py`: bounded official source subset using range
reads. `compare_official.py`: exact Float32 comparison. `finite_coverage.py`:
24native windows and target intersections; `gap_context.py`: GPW context and
persistent G316 NaNs; `mapbiomas_gap_context.py`: actual footprint class fractions;
`gpw_fallback_probe.py`: nearest-epoch GPW feasibility. Raw responses, arrays and
metadata are retained with checksum manifest. Interactive EECU was not measured.
