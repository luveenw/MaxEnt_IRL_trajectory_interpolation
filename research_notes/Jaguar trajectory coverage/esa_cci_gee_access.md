# ESA CCI access in GEE — verified pilot

Checked 2026-11-03, America/New_York. The user selected ESA CCI for shrubland.
This access task establishes a usable, independently checked source route. It
does not select production representative years or publish a final 500 m feature.

## Result: direct GEE access works

A public ESA CCI mirror used by Conservation International's Trends.Earth is
readable through `perceptive-ivy-780`:

```javascript
var source = ee.Image(
  'users/geflanddegradation/toolbox_datasets/lcov_esacc_1992_2022'
);
var lc2005 = source.select('y2005'); // Access pilot only.
```

The mirror contains 31 annual bands, `y1992` through `y2022`. All ten required
Spring bands (2005, 2006 and 2008–2015), plus the wider movement-period 2016 band,
exist. It preserves original thematic codes rather than only seven SDG classes.
The live metadata gives EPSG:4326, 0.002777777777777778-degree native cells,
int16 values and **MODE** pyramiding. The geographic extent is 80°N to 80°S,
covering our entire Pantanal domain. An older 1992–2018 mirror has MEAN pyramids;
use the verified 2022 identifier, not that older asset interchangeably.

This is a third-party mirror documented by its maintainer, not an ESA-owned
standard Earth Engine catalog entry. The exact identifier is explicitly listed
under “Land cover / ESA CCI” in Conservation International's dataset config.
The config was pinned to commit `045d1dcb598fc7e094b079989d8ae9a877c9ac60` and its
bytes hashed. Some descriptive/source-citation fields in that config are stale
(the prose mentions 2018 and a surface-reflectance citation), so we did not rely
on those alone to establish fidelity.
[Maintainer's pinned configuration](https://github.com/ConservationInternational/trends.earth/blob/045d1dcb598fc7e094b079989d8ae9a877c9ac60/LDMP/data/gee_datasets.jsonc).

## Independent comparison against official ESA CCI

The official CEDA archive supplies ESA CCI annual land-cover v2.0.7 GeoTIFFs
without needing CDS credentials or submitting the UCL registration form.
The catalogue identifies these as public data supplied by the ESA CCI team.
[Official catalogue](https://catalogue.ceda.ac.uk/uuid/b382ebe6679d44b8b0e68ea4ef4b701c/),
[official directory](https://data.ceda.ac.uk/neodc/esacci/land_cover/data/land_cover_maps/v2.0.7/).

Using HTTP range reads, we retrieved only a native-grid regional subset from
`ESACCI-LC-L4-LCCS-Map-300m-P1Y-2005-v2.0.7.tif`, rather than downloading its
311,766,289-byte global file. The subset covers the bounding envelope of all
13 Spring grids with a small access margin. It is **1,402 rows × 869 columns**
(**1,218,338 pixels**), EPSG:4326, with no resampling or category changes. The
compressed local COG is 306,746 bytes, SHA256
`7fa5e6c84eaad01d58dce91dbef0f9fe06fa9dabd94b4bc32f0325ab36a55e1f`.
The original source tags report version 2.0.7 and ESA 2017/UCLouvain copyright.

The exact source-aligned window was then requested from the GEE mirror's
`y2005` band and compared locally against the official data:

- **0 class-value mismatches** across all 1,218,338 pixels.
- **0 valid-mask mismatches**; all pixels in this access envelope are valid.
- CRS, dimensions and affine transforms match.
- GeoTIFF NoData metadata differ (official 0, mirror download -32768), but no
  invalid pixels occur in this window. These sentinel conventions must remain
  explicit when generalizing the workflow.

This is a full regional pilot comparison, not proof that every global pixel or
every annual mirror band matches the official archive. Check the eventual
production years similarly before pinning their products. All current Spring
years fall in the historical ESA CCI portion through 2015; 2016 onward belongs
to the C3S continuation and should retain separate version provenance.
[ESA source/version description](https://climate.esa.int/en/projects/land-cover/data/).

## GEE coverage and shrubland presence

A read-only `y2005` probe on every exact checkpoint grid found coverage minimum,
mean and maximum **1.0 in all 13 Spring groups**, including cross-border G115
and G203. The candidate indicator `class in {120,121,122}` occurs in every group.
The G115 classified-shrub area fraction averaged approximately 0.04554; other
group means ranged approximately 0.01734–0.32585. These statistics confirm data
presence, not shrub ecological accuracy, canopy percentage or an adopted feature
recipe. Indicator formation preceded overlap-area aggregation; raw class codes
were never averaged.

No national mosaic is needed for this ESA shrubland source. Its common global
classification covers the relevant Brazil/Paraguay/Bolivia locations. Combining
it with MapBiomas grassland/wetland covariates can still create thematic overlap
because the legends differ; do not assume those predictors form one exclusive
partition.

## Import alternative and encountered staging limitation

The official native-grid subset is locally available for a future private EE
copy if wanted. We inspected the existing project asset quota (49 assets of
50,000; approximately 10.49 GB of 250 GB used). A server-side Storage API query
with explicit `project=perceptive-ivy-780` identifies the existing project buckets
as owned by project number **649987002740**. The number **517222506229** seen in
some API errors is the credential client's default API-consumer project, not
proof of ownership of `perceptive-ivy-780`.

Attempting to inspect the new intended staging object in the existing `jour-22`
bucket returned HTTP 403: “The billing account for the owning project is disabled
in state absent.” **No object was uploaded**, no bucket or EE image asset was
created, and no API, IAM or billing setting was changed. This does not block the
successful direct mirror route. The unused import route would need an available
staging destination or a separately authorized upload method, not automatic
billing changes. The user's script repository is not raster asset storage.

## Saved artifacts and reproduction

Everything is under `data/pantanal_covariates/esa_cci_access_20261103/`:

- `access_pilot.js`: runnable GEE Code Editor example; no task creation.
- `mirror_probe.json`: actual asset metadata including available bands/pyramids.
- `mirror_provenance.json` and pinned `trends_LDMP_data_gee_datasets.jsonc`:
  maintainer configuration identity and hash.
- `source_inspection.json`, `pilot_metadata.json`, official subset TIFF:
  official native source evidence and local checksum.
- `mirror_comparison.json`, mirror comparison TIFF: value/mask equality proof.
- `gee_coverage.json`: all 13 exact-grid coverage/presence results for the pilot.
- `inspect_source.py`, `prepare_pilot.py`, `verify_mirror.py`,
  `probe_gee_coverage.py`: runnable access/audit code. The prepare script's optional
  staging step is currently blocked; it preserves the already retrieved subset.
- `bucket_identity.json`, `project_identity.json`, `preflight.json`: resource and
  endpoint evidence. No credential values are stored.

Run from the repository root with `/tmp/pantanal-gee-venv/bin/python`; that
isolated environment has Earth Engine 1.7.51 and Rasterio 1.5.2. The probe script
reads the existing roughness grid plan only for geometry; it does not alter it.
JSON and Python syntax and JS syntax were checked. Actual remote reads,
full-region pixel equality and full-grid pilot coverage are reported separately
from ecological validation, which remains outstanding. No production shrubland
raster or trainer binding was generated.
