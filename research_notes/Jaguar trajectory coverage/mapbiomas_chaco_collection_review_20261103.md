# MapBiomas Chaco collection reassessment for Pantanal covariates

Checked 2026-11-03. **Recommendation: retain the national-source mosaic and the
existing gap-only Chaco fallback. Do not regenerate the completed Spring
land-cover covariates using Chaco alone or Brazil + Chaco.** Both alternatives
lose substantial coverage, and neither repairs G316/2011. This conclusion is
based on actual Earth Engine queries over all 13 Spring grids / 24 required
candidate group/year pairs, not on the names of the initiatives.

## Current product and geographic scope

The official [Chaco product page](https://chaco.mapbiomas.org/en/products/)
lists Collection 5 (released September 2024, 1985–2023, 18 classes). The
[official GEE tools page](https://chaco.mapbiomas.org/en/tools/) still identifies
`projects/mapbiomas-public/assets/chaco/lulc/collection5/mapbiomas_chaco_collection5_integration_v2`.
This is exactly the regional product already used to fill G115's national-source
gaps. No newer Chaco collection was identified in these current primary sources.
Live asset metadata confirms 39 annual bands, `classification_1985` through
`classification_2023`, and an update timestamp of 2025-12-12T22:03:01.674351Z.
The `years` property says 1985–2022 but the actual band list and `yearEnd=2023`
confirm the usable final year; the audit uses band identities.

MapBiomas Chaco maps the **Gran Chaco**. Participation by institutions in several
countries does not mean the raster covers all territory or all Pantanal in those
countries. The [producer's project description](https://chaco.mapbiomas.org/conoce-mapbiomas/)
identifies this geographic target. The empirical test below directly refutes
complete coverage of our Pantanal model extents by Chaco plus Brazil.

## Actual full-cell coverage

All percentages below are within individual exact 500 m model rectangles. They
are not a unique-biome area estimate; rectangles overlap and candidate years
repeat the same geography.

| Spring model domain | Chaco alone | Brazil + Chaco | Existing national mosaic + approved repairs |
| --- | ---: | ---: | ---: |
| G115, 2005 and 2006 | 57.0551228% | 57.0551228% | 100% effective coverage |
| G203, 2010 | 100% | 100% | 100% effective coverage |
| G316, 2011 | 0% | 99.9997370% | 100% effective coverage |
| Other ten groups, all their required years | 0% | 100% | 100% effective coverage |

For G115, replacing the national mosaic with Brazil + Chaco leaves **1,117 of
2,478 model cells partially or wholly uncovered**, including **1,008 wholly
uncovered cells**. Missing area is **266.043514 km² of 619.5 km²**, per year.
The previous national-source omissions total only approximately 0.080521 km²,
which the already selected Chaco water fallback supplies. Thus the proposed
replacement would greatly enlarge missingness.

Chaco is absent from **11 of the 13 groups**, wholly covers G203 and partly
covers G115. It cannot act as the sole uniform source for this Spring domain.
Brazil + Chaco leaves two kinds of gaps: the large geographic omission in G115
and the same isolated 2011 source hole in G316. Adding Paraguay/Bolivia again
would return to a multi-source mosaic rather than eliminate it.

Coverage here is intentionally optimistic: any observed class other than 0/27
counts before applying a feature crosswalk. Even that upper bound fails. Class
harmonization cannot fill geographical NoData.

## Exact problem-pixel rechecks

The audit re-queried **97 native Brazil-grid centers**: the 96 original G115
holes and G316's one problematic pixel.

- **G115:** all 96 centers are valid Chaco **26, Water bodies**, in 2005, 2006,
  2010, 2011 and 2012. The two production years are therefore directly confirmed.
  The prior all-band audit additionally established code 26 throughout Chaco's
  1985–2023 sequence. This is already the source used for those gaps.
- **G316/2011:** at longitude −57.58843266634279, latitude −17.83771184946872,
  Chaco, Paraguay and Bolivia are masked in every checked year (2005, 2006,
  2010, 2011, 2012). Brazil is valid class **4** in 2010 and 2012 and masked in
  2011. This reproduces the adjacent-year consensus supporting the approved
  repair. Switching to Chaco cannot remove that imputation.
- The G316 gap affects one 500 m cell: observed coverage is 0.9965941186, about
  **851.47 m²** missing. The existing repair supplies effective coverage of one
  while retaining separate observed/imputed fractions.

A separate local read of all 24 current canonical MapBiomas TIFFs confirmed
full effective-coverage band values after the established repairs. No old
product, repair, manifest or raster value was changed by this investigation.

## Thematic compatibility also matters

The official [Collection 5 code legend](https://chaco.mapbiomas.org/wp-content/uploads/sites/2/2024/12/MB-Chaco-Col-5-pdf-Legend-Code.pdf)
identifies 3 as closed woodland, 4 as open woodland, 45 as sparse woodland, 6 as
flooded woodland, 11 as flooded grassland, 26 as water, and 27 as unobserved.
Grassland's hierarchy includes 12 and the more detailed 42/43/44 subclasses.
A country-code-12-only extractor is therefore not a general Chaco grassland
crosswalk. The [descriptive legend](https://chaco.mapbiomas.org/wp-content/uploads/sites/2/2024/08/MB-Chaco-Col-5-pdf-Legend-Descript-EN.pdf)
allows trees, shrubs or mixtures in its woodland classes; closed woodland has
at least 65% woody cover and open woodland 20–65%. These are categorical woody
formations, not continuous tree-canopy measurements.

Actual Chaco histograms in the only overlapping Spring grid/year pairs
(G115/2005, G115/2006, G203/2010) contain **3, 6, 11, 15 and 26**. They contain
no 4, 12 or 42/43/44 in these particular queried regions/years. Flooded woodland
6 is common, not a hypothetical category. These histograms are weighted native
pixel equivalents, not ground-area estimates. The separate wooded-cover class
review addresses whether the new predictor should include flooded woody types.

For a final wooded mask containing class 4, the existing G316 temporal repair
would contribute wooded=1 at that pixel, unlike its grassland=0 and wetland=0
contributions. Reuse would require preserving its temporal-imputation provenance
and documenting that different feature contribution; it does not become a
current-year observation.

## Reproducibility, cost and scope

- [Coverage script](../../gee/mapbiomas_chaco_review_20261103/review_coverage.py):
  read-only source metadata, 24 per-year grid queries and one 97-center sample.
  Missing annual values are explicitly zeroed **before** reduction, avoiding
  the earlier across-year masked-value bug. Native categorical masks align by
  nearest sampling to Brazil's compatible lattice; coverage aggregates by
  overlap weights to each saved UTM affine grid.
- [Histogram script](../../gee/mapbiomas_chaco_review_20261103/probe_chaco_classes.py):
  one bounded request containing the three overlapping grid/year histograms.
- [Audit data directory](../../data/pantanal_covariates/mapbiomas_chaco_review_20261103/):
  exact source metadata, input/script hashes, per-group JSON summaries and NPZ
  coverage arrays, combined summary, native-center samples, class histograms,
  local existing-product coverage check, and checksums.
- All **100,402 cached model cells** were checked for finite [0,1] coverage,
  dimensions and unique full-grid row/column membership. No new source imagery,
  export task, Drive object or replacement covariate was created.
- One initial request failed because the `toList(6)` pixel limit counted six
  bands; it was corrected to the known grid-cell count times six without
  changing scale or using `bestEffort`. The failed attempt is recorded.
  Interactive EECU use is **unmeasured**; elapsed request times are not compute
  charges. Successful coverage queries took roughly 1–3 seconds each in this
  run, but this is not a promise for future runs.
- Scope is the current 13-group Spring collection. No claim is made about full
  biome coverage or all alternative/future seasonal extents. Those require
  their own source-coverage audit before acquisition.

The available evidence supports the current collection choice for coverage.
It does not prove the national classifications are ecologically more accurate
than Chaco where both are available. A source replacement would require a
classification-accuracy or feature-definition reason, not a coverage benefit
shown here. No replacement run is justified by this reassessment.
