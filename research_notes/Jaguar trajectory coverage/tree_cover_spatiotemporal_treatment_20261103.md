# Hansen tree cover: spatial and temporal treatment

Recorded 2026-11-03. Source metadata pinned; no raster graph, pilot, export or
download has been submitted. Production is held while the temporal estimand is
reviewed. Code scaffolding exists and five local numerical/coverage QA tests
pass; this does not validate cloud execution or ecological accuracy.

## Spatial treatment

Use the continuous `treecover2000` canopy-closure percentage directly. Native
pixels are approximately 30 m, representing vegetation taller than 5 m in 2000.
Compute the **overlap-area-weighted mean of native percentages in each exact
500 × 500 m model cell**, on saved EPSG:32721 transforms. For percentages c_i and
intersection areas a_i, the cell value is sum(a_i c_i)/sum(a_i), retaining percent
units (0–100). This estimates canopy-covered area relative to total cell area;
it is neither the percentage of pixels above a canopy threshold nor the mean
only among treed pixels. Source: [official Hansen band definitions](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2025_v1_13).

Earth Engine's [resampling guide](https://developers.google.com/earth-engine/guides/resample)
explicitly demonstrates Hansen `treecover2000` aggregated with
`reduceResolution(ee.Reducer.mean(), maxPixels=1024)` and reprojection to a coarse
500 m grid. We use that same pattern with checkpoint transforms and
`bestEffort=False`, preserving native inputs rather than silently choosing a
coarser pyramid. [The API reference](https://developers.google.com/earth-engine/apidocs/ee-image-reduceresolution)
specifies weights as input mask × fraction of output pixel covered. A separate
unmasked validity band must therefore establish full-cell source coverage,
preventing true NoData from silently disappearing from the denominator.

Bilinear interpolation estimates a value from neighboring sample locations;
coarse-cell area means answer the actual cell-average canopy question. Thresholds
would change the predictor to a forest-class area fraction and discard canopy
gradients. No extra 90 m, 3 × 3 or 17 × 17 moving window is indicated. Keep valid
zero-canopy pixels. Permanent water (`datamask=2`) belongs in the full-cell area
with zero tree canopy; report water fraction, flag any nonzero source canopy on
water, and reject actual NoData (`datamask=0`) or incomplete coverage. Those last
rules are project QA policies based on the documented mask semantics, not an
additional biological forest definition.

## Temporal treatment and unresolved estimand

The [Hansen v1.13 producer download page](https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/download.html)
and official catalog distinguish fixed `treecover2000`, dated stand-replacement
`lossyear`, nonannual `gain` (2000–2012), and spectral reference imagery. A recent
release date does not update the canopy-percentage observation epoch. Annual
loss does not supply annual canopy percentages or seasonal regrowth/leaf-state
observations. It cannot justify a Spring mean-canopy reconstruction.

**If the intended predictor is a structural year-2000 baseline:** carry the same
cell value throughout Spring (15 August–14 November). Its time-weighted seasonal
average is mathematically identical to that constant value, but this represents
an assumption of constant baseline applicability, **not observational coverage
of that Spring or the representative telemetry year**. No monthly replication,
season date filter, seasonal compositing, or trajectory-year filter is meaningful
for this band. Label source epoch 2000 explicitly in artifacts and reporting.

**If the intended predictor is canopy cover observed over the chosen Spring:**
Hansen `treecover2000` cannot meet that requirement. The source and temporal
recipe must be revisited; an annual alternative also requires reviewing its
actual observation/compositing window before calling it seasonal. The production
gate is deciding between these scientific estimands; no temporal inference is
silently adopted here.
