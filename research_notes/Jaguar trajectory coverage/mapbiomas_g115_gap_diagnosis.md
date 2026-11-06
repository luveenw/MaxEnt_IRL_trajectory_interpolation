# G115 MapBiomas gap diagnosis and fill options

Investigated 2026-11-03, America/New_York, at the user's request. Read-only
Earth Engine computations used project `perceptive-ivy-780`. No production
classification was changed, exported, imported or imputed.

## Finding and recommendation

The seven partially covered 500 m cells arise from **holes in the data masks of
all three national products**. The regional MapBiomas Chaco Collection 5 product
has observations in those holes and classifies them as **water bodies**.
Consequently, the preferred candidate is an observed-source fallback, using
Brazil → Paraguay → Bolivia first, then Chaco **only where all three national
sources are unavailable**. This recommendation is not an adopted production
recipe. A harmonized open-water category, a pinned source version/year and
per-pixel fallback provenance remain necessary before implementation.

## Demonstrated cause versus upstream explanation

The original coverage audit excluded masked pixels and classes 0 and 27. This
investigation repeated it with three successive criteria: raw national mask
alone, mask plus nonzero class, and mask plus exclusion of 0/27. All produced the
same G115 coverage: mean 0.9998700229570656 and minimum 0.8693660988897567.
Therefore the missing coverage is **not created by excluding codes 0/27**.
Direct inspection on the Brazil product's native grid found 96 missing pixel
centers; every national product was masked at them. This establishes a
source-mask problem rather than merely a 500 m aggregation/rounding issue.
See [native diagnosis](../../data/pantanal_covariates/mapbiomas_gap_diagnosis_20261103/diagnosis.json)
and its [portable script](../../gee/mapbiomas_gap_diagnosis_20261103/diagnose.py).

The remaining producer-side reason for these omissions is **not established**.
A national clipping/cartographic boundary seam around a water feature is
plausible, but these API checks do not prove the country clipping algorithm,
intentional water masking, the feature's river name, or a satellite acquisition
failure. Do not elevate that inference into a confirmed cause.

The seven cells are affected in every checked Spring year (2005, 2006,
2008–2015). Their missing projected area totals **80,520.7781 m², about 8.0521 ha**,
0.0130% of G115. The worst affected cell lacks about **13.0634%** of its area.
The earlier local lookup found no retained fixes from individuals 74 or 75 in
these seven cells; all model-domain cells still need valid covariate values.
[Original per-year gap audit](../../data/pantanal_covariates/mapbiomas_access_audit_20261103/mapbiomas_gap_probe.json).

## Observed regional fallback and temporal checks

The exact fallback examined is:

`projects/mapbiomas-public/assets/chaco/lulc/collection5/mapbiomas_chaco_collection5_integration_v2`

It supplies code **26 at all 96 diagnosed missing native-grid centers** in 2005.
The official Collection 5 legend identifies code 26 as **Cuerpo de agua / Water
bodies**. Its descriptive legend describes permanent surface water. This is an
open-water class, not proof of flood-influenced herbaceous/shrub vegetation.
[Official Chaco tools](https://chaco.mapbiomas.org/en/tools/),
[Collection 5 code legend](https://chaco.mapbiomas.org/wp-content/uploads/sites/2/2024/12/MB-Chaco-Col-5-pdf-Legend-Code.pdf),
[Collection 5 descriptive legend](https://chaco.mapbiomas.org/wp-content/uploads/sites/2/2024/08/MB-Chaco-Col-5-pdf-Legend-Descript-ES.pdf).

The Chaco asset has 39 annual bands, 1985–2023. The gap-only histograms contain
only class 26 in every one of those bands, including every required Spring year.
Conversely, the maximum national mask validity across **all 41 bands
1985–2025** is zero at these gap locations for every national source. Borrowing
another national map year therefore does not repair these holes.
[Temporal/source fallback evidence](../../data/pantanal_covariates/mapbiomas_gap_diagnosis_20261103/fill_checks.json),
[reproducer](../../gee/mapbiomas_gap_diagnosis_20261103/fill_checks.py).

Adding Chaco's common valid mask across all its annual bands to the national
2005 coverage gives full G115 coverage: exact-grid minimum and mean both **1**.
Together with the earlier identical national coverage in every required Spring
year, this verifies that the candidate source fallback can close the observed
holes for all required years. It does not establish ecological classification
accuracy. The Chaco product alone still covers only part of G115 and is not a
replacement for the country mosaic. It also supplies no 2024/2025 band; a future
extension beyond 2023 needs a separately verified fallback.

## Comparison with the user's proposed fill approaches

- **Fill missing fine pixels from a classified alternative source:** preferred
  here because an existing, versioned source supplies a coherent open-water
  classification at precisely the missing locations. Remap Chaco 26 to the
  common open-water category before mosaicking. Retain a source/fallback flag
  and aggregate the completed categorical indicators to the 500 m grid.
- **Copy the dominant neighboring class:** possible as an explicit imputation
  fallback if no suitable source exists, but it assumes continuity across the
  gap and can erase narrow water features. A categorical nearest-neighbor or
  mode operation must be bounded in physical distance and limited to missing
  fine pixels; never interpolate numerical class IDs or replace an entire
  partially observed 500 m cell. No neighboring-class imputation was run here.
- **Use the observed composition of the same partially covered cell:** if the
  output is a habitat fraction, this means dividing by observed area, rather
  than total cell area. It assumes the missing portion has the same class
  mixture. That assumption is unsupported here because the alternative source
  explicitly identifies the missing patch as water. At the worst cell, any
  binary class fraction can change by as much as 13.0634 percentage points
  depending on the unknown patch. This is not a negligible error merely because
  the total affected study area is small.
- **Use another year:** national masks remain empty throughout 1985–2025;
  temporal filling from those sources cannot solve this case. Chaco already
  provides the corresponding historical years, avoiding a year substitution.

For example, if 60% of a cell's observed area were grassland and only 86.9366%
of the cell were observed, assuming the missing patch is also 60% grassland
would yield a whole-cell fraction of 60%. If that patch is open water, the
whole-cell grassland fraction would instead be about 52.16%. This is an
illustration, not a measured G115 grassland fraction.

If the agreed covariates retain their existing meanings, valid open-water pixels
would contribute zero to grassland, shrubland and flooded **vegetation**
indicators, while remaining valid observed habitat. That is a semantic crosswalk
decision, distinct from replacing NoData with zero. An expanded definition of
flooded habitat including open water would be a separate scientific choice.

## What remains before production

Agree the fallback and common open-water meaning; harmonize the country
legends; preserve the user's national priority; pin year/version; validate full
coverage and keep per-cell/source provenance. A production implementation must
also pin the categorical working grid and nearest-neighbor/mode behavior, retain
class masks, and avoid using map display/pyramid settings as a scientific
resampling policy. The present investigation provides evidence and a recommended
candidate, not a scientific validation or permission to invent filled classes.
