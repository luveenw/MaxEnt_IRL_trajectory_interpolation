# GlobPOP: source assessment and actual Spring GEE access tests

2026-11-04. Research and bounded read-only access tests, not production extraction.
No source choice, split allocation, representative year, export task or Drive
product was finalized. Queries used the confirmed project `perceptive-ivy-780`.

**Correction from deeper native-pixel review:** mask-only pilot validity below
missed unmasked NaNs. G316/2011 has three such native pixels; count masks the
same pixels. Official Zenodo record11179644 matches the full440-pixel GEE window
exactly including NaNs. Finite-value coverage must be checked before production;
no repair or zero-fill is authorized by the prior successful access test.
The deeper review is in progress under `globpop_production_review_20261104`.

## Access, units and release identity

The [author dataset](https://zenodo.org/records/11179644) provides annual
1990–2022 GeoTIFFs, with density in people/km² (Float32), count in people per
native cell (Int32), and WGS84 30-arc-second cells. The 1990–2020 range in the
published article describes the original release; the archive subsequently added
2021–2022. The author repository currently calls the dataset 3.0, whereas the
linked Zenodo record renders Version 2.0. Do not infer a release identity merely
from the shared year range or names. [Author repository](https://github.com/lulingliu/GlobPOP).

The [community catalog](https://gee-community-catalog.org/projects/globpop/)
provides these usable assets:

- `projects/sat-io/open-datasets/GLOBPOP_DENSITY`
- `projects/sat-io/open-datasets/GLOBPOP_COUNT`

Our live inventory found **33 images in each, one per year 1990–2022**, including
all observed Spring candidate years. Density is one Float32 `b1` band; count is
one integer `b1` band. Actual affine is `[1/120,0,-180,0,-1/120,90]`, EPSG:4326;
nominal EE scale is approximately 927.66 m. The physical east–west dimension
varies with latitude. These are community-hosted mirrors, not provider-owned
EE assets. The catalog gives CC BY 4.0 and curator Samapriya Roy; its text still
says 1990–2020 and cites 2.0. **Exact byte/pixel equivalence to a named official
release has not been verified**, and retained metadata has no clear release tag.
Pin image IDs/metadata and resolve that identity before claiming a particular
archive version in production. The author code license is distinct from data licensing.

## Scientific suitability and limitations

The [primary paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10808219/)
fuses existing population products using clustering and statistical learning,
with interpolated/extrapolated inputs and national adjustments. For 2001–2020,
GPW is interpolated, while LandScan and WorldPop are annual inputs; this is not
five independent annually observed census surfaces. Inputs already share census
ancestry. WorldPop inherits ancillary land cover, elevation, lights, roads and
settlements, so fusion does not make population independent of landscape
covariates. The authors report weighting-related fine-scale discontinuities
from 2016 onward. Their subnational validation excludes Brazil, Paraguay and
Bolivia, and sparse-landscape pixel checks are visual rather than independent
census validation. The paper describes LandScan's ambient 24-hour meaning in
its methods; its later discussion calls it nighttime population inconsistently.
Treat this as a mixed-source modeled population surface, not a pure seasonal
resident census. Annual cadence is useful but does not establish local accuracy.

**Assessment:** GlobPOP is a credible candidate for annual population density,
with successful actual study-domain access. Its annual indexing avoids our having
to assign five-year GPW epochs. The reported 2016 change does not fall inside
Spring's observed 2005–2015 candidate years, but matters to later seasonal work
that includes 2016. Comparison around that boundary is needed before extending
this recipe to those records. This assessment does not establish superiority
over GPW in sparsely inhabited Pantanal cells.

## Actual queries, not catalog inference

Executable: `gee/globpop_access_20261104/probe.py`.
Evidence: `data/pantanal_covariates/globpop_access_20261104/` contains metadata,
three pilot results, exact source-grid identities, input hashes and the initial
query error. Pilot domains are the exact checkpoint rectangles, EPSG:32721,
500 m; dates are August 15–November 15 exclusive of each listed year.

| Spring domain/year | Native density range, people/km² | Valid density target centers |
|---|---:|---:|
| G115 / 2005 | 0.0369782–14.6875 | 2,478 / 2,478 |
| G316 / 2011 | 0.0000829021–20.1336 | 1,295 / 1,295 |
| G312 / 2015 | 0.0138093–1.51332 | 2,850 / 2,850 |

The center-mask check uses nearest assignment **only to diagnose source
availability**. It is not a production resampling method and does not prove
complete source overlap coverage within every target cell or every Spring group.
Count and density are not interchangeable: count has many zeros in these domains,
while density remains positive; count also has seven missing target centers in
G316/2011 under this diagnostic. The cause of that mask discrepancy is not yet
diagnosed. Preserve and investigate the respective masks rather than replacing
NoData with zero or converting rounded Int32 counts into density by default.

A direct `filterDate(Aug15,Nov15)` returned zero images and initially caused a
null-image error. EE filters `system:time_start`, which is January 1 here, rather
than overlap with an annual validity interval. The successful implementation
selects January 1–January 1 of the following calendar year, then explicitly
applies that annual estimate over Spring. All three pilots returned exactly one
annual image and zero images for the naive Spring date filter. Annual estimates
provide no within-Spring observations; a time mean of the assumed constant is
unchanged. Never average different candidate years as seasonal observations.

## Proposed production treatment, subject to source choice

Use density Float32 directly, with physical overlap-area weighting onto exact
500 m cells and no extra moving-window smoothing. Preserve valid zero values.
Native count allocation would instead require conservative distribution and
physical area division, with its rounding/masks explicitly addressed.

One denominator detail remains unresolved: the primary paper mentions a surface
area layer; the [author conversion script](https://github.com/lulingliu/GlobPOP/blob/main/Step1_preprocess/Pop_Density_Convert_To_Pop_Count.py)
labels its multiplier `landarea`, without identifying the layer or showing a
water-fraction rule. Therefore we have **not established whether reported density
uses total pixel area or land-only area**. Do not claim population conservation,
zero-fill water, or silently redefine density as full-cell people/km² until that
contract is resolved. A mean of the published density surface can be labeled as
such, but needs explicit valid-area coverage QA.

Current acquisition policy: pre-cache all applicable Spring group/year products
independently of the animal allocation, then select cached annual maps through
separate fitting/testing context plans. Apply each annual estimate throughout
the corresponding Spring; no within-season variation is observed. Remaining production checks: mirror release identity, denominator
and mask semantics, all selected domains/epochs, exact overlap integration and
coverage, and any later-year 2016 discontinuity. These are unresolved source QA,
not a claim that extraction has completed. Interactive EECU was not metered.
