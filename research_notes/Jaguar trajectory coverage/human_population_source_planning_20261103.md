# Human population covariate: source and recipe preflight

Recorded 2026-11-03. Research/planning only: no GEE collection was queried, no
raster was downloaded or uploaded, no animal allocation or epoch was selected,
and no production extraction was run. Catalog coverage below is documented,
not an empirical verification of all Brazil/Paraguay/Bolivia group/year pixels.

## What Alvarenga actually specifies

Alvarenga (2021), §2.3, printed pp. 3–4 and Table 1, identifies human population
density from Venter's Global Human Footprint data at 1,000 m, then resamples
predictors to 500 m. The paper does not identify the population raster filename,
chosen epoch, physical units, transformation, or resampling algorithm. Therefore
neither raw people/km² nor the processed population-pressure score can be claimed
as an exact reconstruction without additional author/code evidence. Its citation
is the Scientific Data descriptor, not merely a reference to the composite map.
[Author-hosted paper](https://www.fs.usda.gov/rm/pubs_journals/2021/rmrs_2021_alvarenga_g001.pdf).

## Paper-associated component

Venter's descriptor, population methods and Tables 2–3, establishes that the
released individual population layers are processed pressure scores: density is
logarithmically transformed below 1,000 people/km² and capped at 10 above that
threshold. Input GPW census summaries are approximately 4 km and were bilinearly
sampled onto the 1 km² grid. Table 3 names `Popdensity1990.tif` and
`Popdensity2010.tif`; the underlying population epoch for the newer footprint
is therefore 2010, despite the composite's 2009 label. These components differ
from the cumulative `HFP2009.tif`. The archive includes separate pressure files
and is cited at [Dryad DOI](https://doi.org/10.5061/dryad.052q5).
[Venter methods and data records](https://pmc.ncbi.nlm.nih.gov/articles/PMC5127486/).

The formula is 3.333 × log(density + 1), with saturation at 10. Base 10 is
consistent with the specified threshold; confirm the actual raster scale and
NoData metadata rather than reconstructing scores from assumptions. Direct
archive access timed out during this preflight. Individual raster readability,
value scaling, masks and any GEE mirror remain unverified. Global coverage is
published for non-Antarctic terrestrial areas, including the three countries;
water/domain coverage requires a pixel-level test.

## Alternatives with explicit population-density meaning

**GPWv4.11 density**: direct GEE asset
`CIESIN/GPWv411/GPW_Population_Density`, global census-based people/km² at
30 arc-seconds (nominal 927.67 m), epochs 2000/2005/2010/2015/2020. Population is
proportionally allocated from administrative units and extrapolated between
census/reference years. It spans the study period but not as annual observed
maps. It is an updated source/feature adaptation relative to Venter's processed
component. Mapping to 500 m cannot create finer population information.
[Official catalog](https://developers.google.com/earth-engine/datasets/catalog/CIESIN_GPWv411_GPW_Population_Density).

**Legacy WorldPop**: `WorldPop/GP/100m/pop` is now deprecated. The catalog lists
2000 through 2020 annual epochs, approximately 100 m, country/year images and
population **counts per native pixel**. Spatial detail is model-derived through
Random Forest redistribution using geospatial predictors; it should not be
interpreted as a census at each 100 m location. Coverage of BRA/PRY/BOL for every
required epoch needs actual collection metadata queries. Deprecation alone does
not prove the asset unreadable, but warrants pinning availability and provenance.
[Legacy catalog](https://developers.google.com/earth-engine/datasets/catalog/WorldPop_GP_100m_pop).

**Successor WorldPop R2025A**:
`WorldPop/GP/100m/R2025A/v1/pop` supplies annual 2015–2030 population counts,
constrained to settlement areas and nationally adjusted. It cannot alone cover
our 2005–2016 records. Mixing releases across 2015 would require an explicitly
reviewed discontinuity policy; it is not a routine replacement of the legacy
asset for this study.
[Successor catalog](https://developers.google.com/earth-engine/datasets/catalog/WorldPop_GP_100m_R2025A_v1_pop).

## Spatial and temporal recipe to settle

For a density source, integrate density over source/target intersection areas
and divide by the declared target area. For native pixel counts, allocate each
count by its intersected fraction of native physical area, sum contributions,
then divide by target physical area in km². A simple mean of counts is not
population density, and summing density values is not population conservation.
Use consistent geodesic/equal-area physical areas or document the projected-area
approximation. For GPW inspect whether density denominators use land area; do not
silently convert land-only density to full-cell density by zero-filling water.

For a pretransformed pressure source, overlap-area-weighted averaging gives
mean pressure, a different feature from pressure computed after averaging density.
Keep that order explicit. Proposed default is no extra moving-window smoothing.
Any learned normalization belongs to training-only preprocessing.

All sources need full model-domain mask audits: true zero is valid; water and
NoData are not automatically interchangeable. For country mosaics select one
valid source per location before integration, avoiding duplicate counts in
border overlaps; inspect seams/holes. Do not infer country from animal metadata.

Freeze the animal allocation and training-derived representative-year plan
before dated production. A five-year source additionally needs a deterministic
mapping from representative year to source epoch (nearest epoch with a declared
tie rule is a proposal). Do not interpolate or average epochs without approval.
A selected fixed-2010 pressure baseline would instead be static and independent
of animal allocation, as with Hansen 2000, but that scientific choice remains open.

## Recommendation and smallest decision needed

First ask whether the intended predictor is **Venter's population-pressure
component** or **raw population density**. For continuity with the named source
in Alvarenga, investigate the actual `Popdensity2010.tif` component first; label
it pressure, and disclose the unresolved exact Alvarenga implementation. For
physical interpretability and dated population inputs, GPWv4.11 is a transparent
starting alternative, with explicitly limited spatial/temporal resolution.
WorldPop should be a deliberate modeled-downscaling alternative after availability
and covariate-dependence review, not a default upgrade based on pixel size.

Once that choice is made, a separate extraction subagent can verify source
readability, units/scale and masks over one pilot extent, document the epoch
rule and pixel QA, then generate the frozen Spring plan. Scripts belong under
`gee/`; rasters/arrays and provenance under `data/pantanal_covariates/`; the
established GEE project and seasonal Drive parent remain applicable. No component
or epoch policy is approved by this note.
