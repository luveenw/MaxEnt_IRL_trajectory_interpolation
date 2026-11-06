# GHSL versus LandScan over the actual GlobPOP missing footprints

2026-11-04. Quantitative read-only diagnostic; no population fill or production
export was applied. The LandScan fallback remains unapproved. Code:
`gee/globpop_ghsl_comparison_20261104/`; evidence:
`data/pantanal_covariates/globpop_ghsl_comparison_20261104/`.

## Conclusion

**Modern GHS-POP P2023A corroborates LandScan's zero values over every audited
GlobPOP gap footprint at the tested epochs.** The four positive100mGHSL pixels
in the larger G057/G286 enclosing frames lie outside the missing footprints.
For G057, both2010and2015GHSL estimates give zero across the same132footprints,
so selecting the nearer2015epoch for2013/2014 does not drive the agreement.

Historical GHS-POP P2016/2015 gives small positive fractional population in a
subset/all footprints depending on domain. That is a real product disagreement,
not missing coverage. Its magnitudes are quantified below; do not interpret
fractional modeled people as directly observed individuals, round them away
before comparison, or call them numerical errors. Modern GHSL agreement
strengthens the source-based zero fallback rationale but does not prove absolute
absence of humans. These products share census ancestry and ancillary mapping
assumptions, so agreement is not independent ground-truth validation.

## Exact comparison target and method

We reused the native missing GlobPOP cell indices from the complete24pair finite
coverage audit. Counts were allocated from native GHSL100m(P2023A) or250m(P2016)
cells to each full30arcsecond missing GlobPOP footprint. No target-center shortcut
or comparison over the entire enclosing frame was substituted for the footprint.

For each GHSL native cell with population count C, its contribution is
C multiplied by the geodesic physical area intersecting the GlobPOP footprint,
divided by its full native cell's geodesic physical area. These contributions
are summed, then divided by the full geodesic footprint area to obtain
people/km². Zero-count cells contribute exactly zero. The local implementation
intersects polygons in the GHSL Mollweide plane; GlobPOP edges are densified
with32segments per edge, and inverse-projected clipped edges are densified to
at most25m before WGS84 ellipsoidal area calculations. This is a reproducible
high-resolution polygon approximation, not a claim of analytic spherical-edge
intersection. Areas and source counts are preserved in per-footprint evidence.

Native frame offsets were reconstructed from the saved source affine and
requested bounding rectangle, with inferred dimensions verified against every
saved array shape. As an independent alignment check, direct EE weighted sums
on each modern-source footprint returned zero for all132G057footprints in both
2010/2015 and for all13G286/2010 and3G316/2010 footprints. This corroborates the
local zero result; the diagnostic EE sum is not a general production count-
aggregation recipe for nonzero values.

The footprint is the full missing native cell, including any portion outside
its model rectangle. Consequently the areas here differ from the earlier
missing-area totals clipped to model domains. Do not add populations across
repeated G057years or overlapping G286/G316footprints as distinct people.

## Modern GHS-POP P2023A results

| Actual missing domain/year | GHSL epoch tested | Missing footprints | Footprints with positive allocated population | Total modeled people over footprints | Maximum density, people/km² |
|---|---|---:|---:|---:|---:|
| G057/2013 |2010and2015|132|0|0|0|
| G057/2014 |2010and2015 sensitivity on identical132footprints|132|0|0|0|
| G057/2015 |2015|132|0|0|0|
| G286/2010 |2010|13|0|0|0|
| G316/2011 |2010|3|0|0|0|

Minimum, maximum, mean and area-weighted density are all0 for these tests.
LandScan's same-year observed count is0 at all of these native gap locations,
so disagreement is0 in count/full-footprint density under this diagnostic.
G057uses108.093884km²of full native footprints, G28610.593447km² and
G3162.444670km². G0572013and2014 lack contemporaneous GHSL epochs;2010/2015
agreement is not evidence of annual/sub-season observation or absence throughout
those years. The G3162011check uses a one-year-earlier2010GHSL estimate.

## Historical GHS-POP P2016, epoch2015 sensitivity

This deprecated250mproduct is a separate historical alternative, not verified
equivalent to the paper's actual GPWv4.10-derived GHS input. Its2015epoch is not
contemporaneous with G2862010 or G3162011 and is used only as a product-sensitivity
comparison. All source frames are finite and mask-valid.

| Domain footprints | Positive / total footprints | Zero footprints | Total modeled people | Maximum people per native footprint | Density range, people/km² | Area-weighted density, people/km² |
|---|---:|---:|---:|---:|---:|---:|
| G057 |2/132|130|0.283407843|0.141703922|0–0.172975883|0.002621868|
| G286 |13/13|0|0.022732482|0.012772935|0.000620183–0.015672524|0.002145901|
| G316 |3/3|0|0.001516155|0.000505519|0.000620185–0.000620192|0.000620188|

For G057, the2positive footprints are shared across its2013/14/15missing masks;
this is the same2015source estimate, not three independent population counts.
All historical positive amounts are sub-person modeled allocations. The modern
product and LandScan zeros therefore disagree with small historical predicted
amounts, rather than with observations of whole residents. There is no accuracy
ranking established by this comparison.

## Source interpretation and recommendation

The [official P2023A catalog](https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2023A_GHS_POP)
describes residential population derived from GPWv4.11 and disaggregated using
GHSL built-up information, at100m with five-year modeled epochs. It does not
provide an annual census. The [historical P2016 catalog](https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2016_POP_GPW_GLOBE_V1)
describes the deprecated250mGPW-derived product. Neither should be called a
byte-identical test of the GlobPOP authors' original GHS working inputs.

[LandScan](https://pmc.ncbi.nlm.nih.gov/articles/PMC11933676/) estimates ambient
population and exports integer counts. Zero can reflect integer quantization;
GHSLFloat64zeros provide additional evidence beyond integer truncation but still
inherit modeled settlement/census assumptions. [GlobPOP](https://www.nature.com/articles/s41597-024-02913-0)
is itself a modeled fusion. Shared ancestry prevents treating these comparisons
as independent censuses.

The evidence now supports presenting a same-year LandScan gap-only fallback
as a reviewable choice: existing finite GlobPOP densities stay unchanged, only
audited gaps receive the documented component value, and fallback fractions,
source IDs and quantization/semantics are retained. Modern GHSL independently
within its product pipeline gives the same zero at tested epochs, while the
historical sensitivity difference should be disclosed. This remains a source-
based adaptation; it is not reconstruction of the unobserved GlobPOP estimate.
No fill was approved or applied by this comparison.

## Reproduction and artifacts

- `compare.py`: conservative allocation and per-footprint/summary outputs.
- `fetch_extra_epoch.py`: G057/2010 temporal-sensitivity native frame.
- `verify_zero_ee.py`: independent direct EE zero corroboration.
- `comparison_summary.json`, `per_gap_comparison.json`: counts, densities, areas,
  sources, epochs and source-array hashes.
- `ee_zero_corroboration.json`: complete per-footprint server responses.
- `manifest.json`: hashes of scripts, inputs and outputs for this diagnostic.

No scientific model was fitted, no interpolation performance was evaluated,
and no official census accuracy was established by these software checks.
