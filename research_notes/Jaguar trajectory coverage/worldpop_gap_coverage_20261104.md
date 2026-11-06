# Annual WorldPop coverage over GlobPOP missing footprints

2026-11-04. Read-only Earth Engine tests, no imputation or production exports.
Source: `WorldPop/GP/100m/pop`, country/year images for BRA, BOL and PRY,
queried for2010,2011,2013,2014,2015. Each country/year had one image.
[Official catalog](https://developers.google.com/earth-engine/datasets/catalog/WorldPop_GP_100m_pop).
This legacy collection is deprecated but currently accessible; the R2025A
successor starts2015 and cannot alone cover our full period. Do not switch
releases silently. Identity relative to GlobPOP's exact historic input files
has not been established; these are available same-family candidate fallbacks.

The band contains **people per native approximately100m pixel**, not density.
A finite nonnegative predicate with a very high upper bound excludes NaN/Inf
and negative values; only this QA predicate is unmasked to0 to quantify missing
coverage. Actual population values are not zero-filled. Earth Engine
native-resolution overlap-weighted reducer means over each exact audited
30arc-second footprint provide coverage diagnostics, not final exact500m area
integration. Native image masks are preserved.

| GlobPOP missing footprint set | Native footprints | Full WorldPop finite coverage | Partial | No finite coverage |
|---|---:|---:|---:|---:|
| G057/2013 |132|69|55|8|
| G057/2014 |132|69|55|8|
| G057/2015 |132|69|55|8|
| G286/2010 |13|0|6|7|
| G316/2011 |3|0|3|0|

Therefore it is false that all GlobPOP missing pixels are absent from WorldPop,
but equally false that a direct WorldPop substitution would provide complete
coverage. Remaining masked parts require a separately justified water/missingness
policy or another complete source. Finite counts in these footprints are very
small (overall maxima below0.00045people/nativepixel) and include valid zeros;
masked areas must not be interpreted as zero from these values alone.

For a reviewed fallback, allocate source counts by physical overlap fraction,
sum population contributions, then divide by target physical area in km².
Do not paste raw counts into a density band. Published GlobPOP density denominator
semantics and water treatment remain distinct contracts to disclose. Source
blending needs fallback-area fractions/provenance and consistency checks against
nearby valid GlobPOP values; those comparisons do not establish independent
accuracy because these modeled products share input ancestry.

Executable: `gee/globpop_component_audit_20261104/worldpop_coverage.py`.
Evidence: `data/pantanal_covariates/globpop_component_audit_20261104/worldpop_gap_coverage.json`
and `worldpop_provenance.json`, including source image IDs and projection.
