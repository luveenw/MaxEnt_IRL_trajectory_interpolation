# Can a component source fill the actual GlobPOP gaps?

2026-11-04. Read-only source audit and explicitly unapplied candidate patches.
No production repair, export, upload or change to existing covariate products.
Code is under `gee/globpop_component_audit_20261104/`; retained native arrays,
metadata, author source code and candidate diagnostics are under
`data/pantanal_covariates/globpop_component_audit_20261104/`.

## The gaps are not present in every component

An important correction to the general five-source description: the
[GlobPOP paper](https://www.nature.com/articles/s41597-024-02913-0), its
[author input table](https://github.com/lulingliu/GlobPOP/blob/main/Tables/Input_pop_information.md)
and [fusion code](https://github.com/lulingliu/GlobPOP/blob/main/Step2_model_estimation/Composite_model_GlobPOP.py)
distinguish time periods. GHS-POP/GRUMP/GPW are used for1990–1999, all five products
for2000, and **LandScan/WorldPop/GPW for2001–2020**. GHS-POP inputs are listed for
1990/2000 and GRUMP for1990/1995/2000. They are not contemporaneous annual inputs
to our Spring2005–2015 maps. Thus five missing contemporaneous component rasters
is not the right hypothesis for this study period.

The author code constructs weighted arithmetic combinations of the three source
rasters, without a per-pixel missing-component replacement branch in the inspected
fusion expressions. [GRASS map algebra](https://grass.osgeo.org/grass-stable/manuals/r.mapcalc.html#null-support)
propagates NULL through ordinary arithmetic. This provides a plausible mechanism
for missing GlobPOP output despite finite values in another component. We have
not reconstructed the original authors' working rasters, masks and adjustment
pipeline, so this is an explanation consistent with the code and observations,
not proof of each gap's precise production history. Source coefficients may be
negative and are not generally simple convex averages; do not casually renormalize
remaining weights and claim to reproduce GlobPOP.

## Actual source access and footprint coverage

The tested frames enclose **all missing native footprints**, not just their
centers. Native values were downloaded and tested with `numpy.isfinite`, mask>0
and nonnegative count checks. Bounding frames also include intervening pixels;
complete validity of those frames establishes validity over the enclosed gap
footprints. This is coverage evidence, not local census-accuracy validation.

| Source tested | Temporal/data meaning | Result over actual missing footprints |
|---|---|---|
| GPWv4.11 density | Five-year epochs; nearest2015 forG057 | G057121/132nativecenters masked; insufficient. G316all3zero; G28611zero/2positive. Earlier probes were centers, not full-footprint integration. |
| LandScan Global | Same-year2010/11/13/14/15, integer ambient population counts,30arcsec | Every enclosing frame finite and mask-valid: G057805/805pixels in each year; G286192/192; G31672/72. All missing native cells have observed count0. |
| GHS-POP P2023A | Modern100m residential population counts; nearest2010/2015 | Complete finite coverage: G05769,353/69,353framepixels per candidate year; G28615,680/15,680; G3166,608/6,608. Modern alternative, not the actual historical source version. |
| GHS-POP P2016 | Deprecated250m product,2015epoch | Complete finite coverage: G05711,250/11,250; G2862,565/2,565; G3161,150/1,150. Not verified equivalent to the paper's GPWv4.10-derived input. |
| GRUMP | Original1990/95/2000 | No contemporaneous2005–2015raster exists in the paper's input series. No native pixel coverage query performed; do not infer coverage from other products. |
| WorldPop | Same-year legacy100m country mosaics | Root's [separate audit](worldpop_gap_coverage_20261104.md) found G05769complete/55partial/8zero-coverage footprints in each year, G2860complete/6partial/7zero, G316all3partial. It is not a blanket complete fallback. |

Live inventories confirm25LandScan annual images2000–2024,12GHS-P2023A epochs1975–2030
and4historicalP2016epochs1975/1990/2000/2015. The guessedP2019A GEEasset was not
found; this does not establish that historical2019 data is unavailable elsewhere.
GHS2023 uses updated GPWv4.11 and built-up information, whereas the paper's table
names GPWv4.10 ancestry for its historical GHS inputs. Modern-source tests cannot
be represented as byte-identical audits of the authors' actual input files.
Likewise the LandScan mirror is the same product/year family; exact file identity
to the authors' consumed copies is unverified.

Sources: [official GHS-P2023A catalog](https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2023A_GHS_POP),
[historical P2016 catalog](https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2016_POP_GPW_GLOBE_V1),
[LandScan provider paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC11933676/),
[LandScan GEE mirror/access](https://gee-community-catalog.org/projects/landscan/).
The LandScan provider describes ambient24hour population, distinct from strictly
residential/nighttime counts. Annual production/input changes can affect trends.

## Concrete LandScan candidate, not an approved repair

`landscan_candidates.py` creates five `*_candidate_patch_DO_NOT_USE.npz` files:
native-grid density is present **only at existing GlobPOP NaNs**, with an explicit
fallback flag; elsewhere the candidate patch is NaN. Nothing was applied to
GlobPOP or converted into a production500m raster. Conversion is native integer
count divided by full native WGS84 ellipsoidal cell area. It is not a claim about
GlobPOP's original land/total-area denominator. Every candidate gap value is0
because the actually observed LandScan count is0, not because of generic unmasking.

Annual LandScan grid origins differ:2010/2011start at84N, while2013–2015start at90N.
The diagnostic uses each image's affine and pixel coordinates. A collection-wide
fixed row offset would be wrong. Tiny affine numerical differences remain near
nominal30arcsec alignment; production must use the actual source geometry and
overlap integration rather than assuming array rows can simply be pasted.

On neighboring finite GlobPOP pixels within the same enclosing frames, candidate
LandScan count/area density differs from GlobPOP as follows (people/km²):

| Pair | Compared finite native pixels | MAE | RMSE | Median signed difference, LandScan minus GlobPOP |
|---|---:|---:|---:|---:|
| G057/2013 |673|0.091663|0.178057|-0.023553|
| G057/2014 |673|0.085332|0.163014|-0.024430|
| G057/2015 |673|0.047653|0.097311|-0.013799|
| G286/2010 |163|0.073568|0.179459|-0.000435|
| G316/2011 |57|0.000311|0.000332|-0.000326|

LandScan's median density in those sparse frames is0; GlobPOP preserves small
positive values. The comparison measures source disagreement, not predictive or
census error. Integer quantization is a material limitation; a zero source count
does not prove absolute human absence. Ambient population semantics and different
processing can also introduce seams. These differences must be disclosed even
when the numerical density values are small.

## Recommendation

Using a component to fill a missing ensemble pixel is **not inherently ill-advised**.
It is defensible as a versioned, explicitly labeled fallback when the component
is observed, valid, temporally appropriate and converted to compatible units.
For these gaps LandScan is a concrete complete annual candidate, already part of
the relevant GlobPOP fusion family. It is preferable to inventing spatial or
adjacent-year values at persistent gaps. It is nevertheless a methodological
adaptation, not reconstruction of the missing GlobPOP estimates.

If chosen, preserve finite GlobPOP values, fill only explicitly audited nonfinite
footprints using the declared same-year fallback, retain native/target fallback
fractions and source IDs, and perform exact-area integration before500m density
publication. Do not paste native counts into density, silently zero allNoData,
reuse nearest-center diagnostics as aggregation, or claim population-conserving
GlobPOP reconstruction. A single alternative source across all domains is a
separate defensible choice if semantic consistency outweighs retaining GlobPOP.
No fallback policy or production dataset has been finalized by this audit.
