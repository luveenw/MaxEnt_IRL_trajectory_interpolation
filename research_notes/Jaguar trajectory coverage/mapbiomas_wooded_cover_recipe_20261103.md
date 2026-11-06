# MapBiomas annual wooded-class proxy: decision-ready recipe

2026-11-03. Planning only. The user selected MapBiomas instead of Hansen;
requested classes 3 + 4 are the starting definition, not permission to add other
classes. No new raster graph, export or extraction was submitted for this review.
The Hansen draft is superseded and its setup/publication entry points disabled.

**Final user decision (2026-11-03): keep only classes 3 and 4.** This resolves
the choice discussed below; the broader-class recommendation is retained as
research rationale, not the selected recipe. Exclude 6/7; retain the documented
500 m area-fraction and annual seasonal treatments. Allocation/year selection
remains pending; no wooded production extraction has run.

## Meaning and crosswalk

This predictor is **the fraction of a 500 m cell assigned to selected natural
wooded-vegetation classes**, not measured tree-canopy percentage. Trees, shrubs,
herbaceous spaces and bare interstices within a selected 30 m class pixel all
contribute to its full classified area. Thus this is an explicit adaptation of
Alvarenga's canopy predictor and must retain that definition in any `tree_cover`
legacy feature-key mapping.

- **Brazil Collection 11 v3:** 3 = Forest Formation; 4 = Savanna Formation.
  Pantanal class 3 contains tall trees with lower shrubs; class 4 includes small,
  scattered trees in shrub/herbaceous vegetation. Separate 6 = Floodable Forest
  and 7 = Flooded Savanna (beta) are excluded by a strict 3 + 4 rule.
  [Official current product/legend, including Pantanal method](https://brasil.mapbiomas.org/iniciativas-e-produtos/cobertura-e-uso-da-terra/cobertura-30m/cobertura/).
- **Paraguay Collection 3 v1:** 3 = Closed Natural Woodlands; 4 = Open Natural
  Woodlands. These include trees **and shrubs without distinction**; the
  descriptive legend uses respectively >65% and 15–65% woody-canopy coverage.
  Code 6 separately represents flooded woody vegetation including palms.
  [Code legend](https://paraguay.mapbiomas.org/wp-content/uploads/sites/11/2026/09/PY-LC-Col-3-Legend-code.pdf),
  [descriptions](https://paraguay.mapbiomas.org/wp-content/uploads/sites/11/2026/09/1.Descripc_Leyenda_ES-PRY.pdf_COLECCION_3.pdf).
- **Bolivia Collection 4 v1:** 3 = Forest; 4 = Open Forest. The latter can include
  trees, shrubs or mixtures with 20–65% cover. Code 6 = Flooded Forest.
  [Current codes](https://bolivia.mapbiomas.org/wp-content/uploads/sites/5/2026/09/Leyenda_Code_Bolivia_Col4.pdf),
  [retained official descriptions](https://bolivia.mapbiomas.org/wp-content/uploads/sites/5/2026/09/Leyenda_Descriptiva_MB-Bolivia-Col-4_Gral_ES.pdf).
- **Chaco Collection 5 integration v2:** 3 = Closed Woodland; 4 = Open Woodland;
  6 = Flooded Woodland; 45 = Sparse Woodland. **3 and 4 do match these broad
  woody categories**; do not assume all Chaco numeric codes differ. Water is
  26 (national products use 33), and grassland has additional child classes.
  [Exact Collection 5 code legend](https://chaco.mapbiomas.org/wp-content/uploads/sites/2/2024/12/MB-Chaco-Col-5-pdf-Legend-Code.pdf).
  A separate agent is checking coverage and latest collection availability.

These class semantics were already independently established in the retained
[official-legend fixtures](../../data/pantanal_covariates/mapbiomas_class_audit_20261103/legend_download_sources.json)
and [country harmonization note](mapbiomas_country_class_harmonization.md);
existing observed histograms need not be rerun just to confirm class presence.

## Flooded woody vegetation is a material decision

Existing [priority-selected Spring-domain histograms](../../data/pantanal_covariates/mapbiomas_class_audit_20261103/priority_selected_classes.json)
cover 2005, 2006 and 2008–2015. Brazil 3, 4 and **7** occur in all ten checked
years; Brazil 6 does not. Paraguay 3 and **6** occur in every year, while Paraguay
4 does not. Bolivia contributes 3 in all years but no 4/6. Paraguay 6 ranges
477,440–655,994 weighted native-pixel equivalents; Brazil 7 ranges
71,006–483,751. These are boundary-weighted histogram frequencies over the
union of all Spring rectangles, not ground areas or results for each final
representative group/year.

**Recommendation:** for a broadly natural-wooded habitat proxy, include flooded
woody classes (national 6; Brazil 7) as well as 3/4, because inundation does not
remove woody structure. **The user must choose this broadening**; strict 3 + 4
is also implementable but must be described as excluding separately mapped
flooded woody/savanna vegetation. Neither option becomes actual canopy percent.
Plantations (9) remain outside the requested natural-wooded concept. Chaco 45
requires its own sparse-woodland decision if a broader Chaco fallback is adopted;
do not silently map it into a 3 + 4 target.

## Spatial and temporal recipe

Choose the highest-priority valid source class first (Brazil → Paraguay →
Bolivia, plus the reviewed Chaco gap policy), then derive a native binary
membership indicator and overlap-area-weighted mean into exact saved 500 m UTM
cells. Units: fraction 0–1 (multiply by 100 only for display). No bilinear class
interpolation, dominant-class replacement or extra neighborhood smoothing.
[Earth Engine overlap-weight semantics](https://developers.google.com/earth-engine/apidocs/ee-image-reduceresolution).

Freeze the animal allocation and training-only representative year per group
before the subsequent production epoch plan. Apply that year's annual map as a
static predictor throughout Spring, 15 August–14 November, pooling admitted
trajectory years as already agreed. This is an annual structural proxy assigned
to the season, not a measured Spring average or seasonal inundation time series.

The official [MapBiomas methodology](https://brasil.mapbiomas.org/iniciativas-e-produtos/metodologia-mapbiomas/visao-geral/)
uses cloud-screened observations, annual spectral mosaics, classification and
spatial/temporal postfilters. The current Pantanal description additionally says
its classifier receives within-year medians, standard deviations, quartiles and
ranges from Landsat mosaics (product link above). Those within-year inputs yield
one annual class; they do not make the delivered annual band a Spring-only
composite. Filtering that band by season dates cannot recover seasonal classes.

## Repair reuse and remaining choices

The approved G316/2011 one-pixel adjacent-year consensus retrieves valid class
4 in both 2010 and 2012. For a 3 + 4 wooded target it contributes **1**, unlike
the zero contributions to grassland and narrow flooded habitat. Its effect is
851.4703 m² / 250,000 m² = 0.00340587 cell fraction (**0.340587 percentage
points**) in one cell. Reuse the same explicit class repair and retain the
separate observed/imputed coverage QA; do not hard-code the old target zeros.
See [approved repair record](../../data/pantanal_covariates/spring_mapbiomas_landcover_v1/approved_G316_temporal_repair.json).

Before extraction: resolve strict 3/4 versus inclusion of 6/7; finish Chaco
collection/footprint and gap policy; freeze allocation/year plan; record the
feature-key/units adaptation. Source versions and masks must be pinned; retain
existing historical products unchanged. Outside MapBiomas coverage, revisit the
source and semantic compatibility rather than silently treating missing pixels
as zero wooded cover.
