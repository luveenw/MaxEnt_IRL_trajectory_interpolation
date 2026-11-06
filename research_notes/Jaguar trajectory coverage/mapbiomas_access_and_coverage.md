# MapBiomas access and Pantanal coverage investigation

Checked 2026-11-03 (America/New_York). This is the user's separately authorized
access/coverage sidequest. The earlier draft about Alvarenga and MapBiomas (2021)
was withdrawn and supplies no accepted source, class mapping, or map-year choice.
No land-cover raster export, asset import, or new covariate recipe was performed.

**Later production correction (2026-11-03):** the initial all-year coverage
probe below missed a transient single-pixel G316/2011 mask gap because across-band
minimum skips masked values. Each annual validity image must be unmasked to zero
before the across-year reduction. Production per-year QA caught the issue and
rejected the incomplete TIFF; 23 paired products remain valid. The original
reported probe results are retained, but its 12-of-13 completeness observation
is not a guarantee for all individual years. See
[the discrepancy evidence](../../data/pantanal_covariates/spring_mapbiomas_landcover_v1/earlier_audit_discrepancy.json)
and current manual/handoff for the pending repair decision.

## Findings

**MapBiomas can be queried directly in Google Earth Engine.** Public national
land-cover assets exist for Brazil, Bolivia and Paraguay. They do not need to be
downloaded and re-uploaded to the user's project. Their official access pages
provide asset identifiers; live authenticated `ee.data.getAsset()` calls using
`perceptive-ivy-780` succeeded for all three current identifiers below.
[MapBiomas Brazil assets](https://brasil.mapbiomas.org/downloads/assets-no-google-earth-engine/),
[MapBiomas Bolivia assets](https://bolivia.mapbiomas.org/downloads/assets-en-google-earth-engine/),
[MapBiomas Paraguay maps](https://paraguay.mapbiomas.org/descargas/mapas-de-las-colecciones/),
[Paraguay access FAQ](https://paraguay.mapbiomas.org/faq/?tema=datos).

The national products verified in the live API are:

- **Brazil, Collection 11, version 3:**
  `projects/mapbiomas-public/assets/brazil/lulc/collection11/mapbiomas_brazil_collection11_coverage_v3`
- **Bolivia, Collection 4, version 1:**
  `projects/mapbiomas-public/assets/bolivia/lulc/collection4/mapbiomas_bolivia_collection4_coverage_v1`
- **Paraguay, Collection 3, version 1:**
  `projects/mapbiomas-public/assets/paraguay/lulc/collection3/mapbiomas_paraguay_collection3_coverage_v1`

All three are **`IMAGE` assets with 41 annual bands, `classification_1985`
through `classification_2025` inclusive**. These are live API observations, not
assumptions inferred from publication year. The inspected grids are geographic
EPSG:4326 with approximately 0.000269494585-degree pixels (nominal 30 m), integer
class values and `MODE` pyramiding. Native angular cells are not 30 × 30 m UTM
cells. Exact API metadata and a reproducible metadata query script are retained
under [the access audit](../../data/pantanal_covariates/mapbiomas_access_audit_20261103/asset_metadata.json).

The official pages describe national coverage; Paraguay explicitly describes
its Collection 3 as national annual maps for 1985–2025. National coverage is the
appropriate starting point for the user's cross-border question, rather than
assuming a regional initiative covers all of a country.
[Paraguay Collection 3 description](https://paraguay.mapbiomas.org/descargas/destacados/).
Actual masks at trajectories and full padded map extents must be checked
separately from those advertised geographic scopes.

## Querying the annual classifications

A minimal GEE Code Editor example using a verified asset is:

```javascript
var year = 2009; // Example only; not an adopted representative year.
var id = 'projects/mapbiomas-public/assets/paraguay/lulc/collection3/' +
         'mapbiomas_paraguay_collection3_coverage_v1';
var landCover = ee.Image(id).select('classification_' + year);
print('Selected annual band', landCover.bandNames());
print('Native grid', landCover.projection());
```

Use `.select('classification_' + year)` on these multiband images. Do not use
`filterDate()` to select years inside a single image. Bolivia and Paraguay assets
carry a `year: 2000` metadata field despite containing all 41 annual bands;
interpreting that property as the dataset's only epoch would be incorrect.
These observations are preserved in the API snapshot above.

A separate public convenience catalog,
`projects/mapbiomas-public/assets/brazil/lulc/v1`, is an **`IMAGE_COLLECTION`**
(live API verified). Its images have a `classification` band and represent
particular years/versions/collection IDs. Do not interchange that collection API
with the multiband-image API. For reproducible research, the exact verified
collection/version asset plus explicit year band avoids accidentally mixing
versions or selecting an arbitrary collection image.
[MapBiomas publisher catalog](https://developers.google.com/earth-engine/datasets/catalog/projects_mapbiomas-public_assets_brazil_lulc_v1).

## Temporal fit to this project

The root agent's checkpoint inspection found preserved source observations from
**2005-08-09 through 2016-05-23**; selected Spring window years are
**2005, 2006, and 2008–2015**. Each current national asset contains every needed
annual band. Publication/collection versions are separate from map years:
a 2026 release can include a revised 2009 classification.

Annual coverage does **not** establish Spring-specific vegetation or inundation.
An annual band has no August 15–November 14 observations to isolate with a date
filter. The model may use an annual representation as a declared approximation,
but that choice and wetland semantics remain to be reviewed. The existing
training-only representative-year choice still depends on the pending animal
allocation; this investigation does not select years or alter retained routes.

The access finding concerns the historical Landsat-based nominal-30 m land-cover
series. Do not substitute newer higher-resolution products without separately
checking that their shorter temporal record covers these movements.

## Bolivia, Paraguay and regional alternatives

Individuals **74 and 75** occur in Spring group **G115**, according to the root
agent's checkpoint audit. Their reported study country is Paraguay; their combined
retained-point bounding box is approximately
`[-58.2441, -20.079479, -58.13943, -19.910097]` in longitude/latitude. Country labels
in telemetry metadata are not a point-by-point border determination. Full padded
grid coverage and actual positions need the live masks, not just a study label.

MapBiomas also has regional initiatives, including Chaco and Amazonia. The
[official Chaco tools page](https://chaco.mapbiomas.org/en/tools/) supplies
`projects/mapbiomas-public/assets/chaco/lulc/collection5/mapbiomas_chaco_collection5_integration_v2`.
The root agent also live-probed this alternative: it covers about 57.06% of G115
in the all-year mask check and leaves some grid cells entirely uncovered. It
cannot serve as the sole G115 source; no source has been selected here. An
Amazonia product covering parts of Bolivia does not establish coverage of the
Bolivian Pantanal; likewise Chaco and Atlantic Forest products have regional
boundaries, not guaranteed full-country scope. Prefer the verified national
products for the first coverage assessment, then consider regional alternatives
only where their coverage or class definitions provide a justified benefit.

Before producing combined covariates, a national-source mosaic needs an explicit
country/overlap priority, a cross-country class mapping, and gap handling.
Successful pixel coverage does not prove compatible ecological class semantics.
The live metadata itself demonstrates version differences: Brazil Collection 11
v3 records `class_remap: 13->77`; Paraguay Collection 3 v1 records
`class_remap: 22->25, 26->33`. Do not silently reuse older legends or infer that
equal class numbers always mean the same ecological category. Missing cells must
not become habitat absence by replacing them with zero.

## Live Spring coverage probes

The root agent evaluated the ten Spring years listed above, requiring unmasked
classification values other than 0 and 27, and aggregated coverage onto the
existing exact 500 m grids. It combined the national products as a coverage union
only; it did not create a combined land-cover classification. The first probe
took the minimum across years within each country before the country union.
That conservative check gave full coverage in **12 of 13 Spring extents**.
G115 had a small remaining gap, with mean coverage 0.9998700229557798 and minimum
cell coverage 0.8693661093711853.

A follow-up combined the three countries separately in each year and then checked
the exact grid. **The G115 gap persists in every tested year**, so it is not an
artifact of the conservative order of those operations. Seven of G115's 2,478
cells are partially covered. Each year's mean is 0.9998700229570656 (about
99.987% coverage), and its worst cell is 0.8693660988897567 (about 86.94%). These
are coverage fractions, not classification probabilities or ecological confidence.

A local projected-cell lookup found **zero of 1,177 retained fixes for ID 74 and
zero of 1,563 retained fixes for ID 75 in those seven incomplete cells**. This
does not assign political-country identity to individual fixes. It also does
not resolve the model-domain requirement: full finite feature coverage is still
needed beyond observed fixes. Do not silently fill missing areas as habitat
absence or claim complete coverage for all seasons.

G115 received contributions from Brazil, Bolivia and Paraguay. G203 required
Brazil/Paraguay contributions; the other eleven Spring grids were fully covered
by the Brazil candidate alone in this probe. National raster footprints overlap:
country-product coverage fractions are non-additive and are not political-country
area fractions. A boundary or priority rule remains necessary when combining
actual classes. The Chaco Collection 5 candidate alone had mean G115 coverage
0.5705512276658189 and minimum cell coverage 0; it is not a complete alternative.

The evidence is retained in
[the full extent probe](../../data/pantanal_covariates/mapbiomas_access_audit_20261103/mapbiomas_coverage_probe.json),
[the per-year G115 follow-up and retained-fix counts](../../data/pantanal_covariates/mapbiomas_access_audit_20261103/mapbiomas_gap_probe.json),
and [the input summary](../../data/pantanal_covariates/mapbiomas_access_audit_20261103/mapbiomas_coverage_inputs.json).
The corresponding scripts are
[mapbiomas_probe.py](../../gee/mapbiomas_access_audit_20261103/mapbiomas_probe.py)
and [mapbiomas_gap_probe.py](../../gee/mapbiomas_access_audit_20261103/mapbiomas_gap_probe.py).
These are archived audit scripts, not production extraction code: their exact historical versions used `/tmp`; active scripts were subsequently
relocated under `gee/` and now resolve their corresponding saved data fixtures.
See `data/pantanal_covariates/script_migration.json` for original/current hashes. The root agent appended the local retained-fix lookup counts to the gap
JSON after the Earth Engine script completed; that local lookup is not included
in the archived Earth Engine script.

## If a private EE copy or upload is eventually needed

Direct public-asset use is sufficient for analysis and derived exports. Reading
a public asset through `perceptive-ivy-780` does not copy it into that project's
asset storage. A future reproducibility snapshot could be exported to an EE
image asset under `projects/perceptive-ivy-780/assets/...`; that would consume
storage and needs its own provenance and bounded extent. No such copy is needed
or created by this sidequest.

For an otherwise unavailable external GeoTIFF, EE supports uploading with the
Code Editor Asset Manager or uploading staged Cloud Storage files using the CLI.
For land-cover classes use a categorical pyramiding policy (`MODE`, or a justified
`SAMPLE` policy), retain the original NoData mask, band names and native grid, and
record source version/year. Do not use the default mean pyramid for class codes.
The existing `users/luveenw/ColumbiaMAThesis` location is a **script repository**;
it is not the destination for raster image assets.
[EE raster upload guide](https://developers.google.com/earth-engine/guides/image_upload),
[EE command-line upload guide](https://developers.google.com/earth-engine/guides/command_line).

The official country pages identify MapBiomas data as public/open with attribution
(CC BY 4.0 on the current dedicated pages). Preserve the correct country's
collection/version citation, access date, asset ID and any derivative processing
when publishing derived inputs. No third-party contact or new cloud storage
resource is required for direct querying.

## Verification limits and source discrepancies

The exact current asset IDs were extracted from live official-page HTML and
verified with the EE API. Search snippets and some generic pages were stale or
internally inconsistent. In particular, Bolivia's generic FAQ displayed the
Brazil collection history, while its dedicated assets page and live Bolivia
Collection 4 asset agree on 1985–2025. Paraguay's collection page retains an older
Collection 2 identifier alongside Collection 3; the older asset was also checked
and contains 1985–2023, but is not the current candidate above. Prefer pinned API
metadata and country-specific product documentation over those generic snippets.

This establishes data access and annual-band availability. The parent agent's
separate spatial mask audit supplies the actual Spring/individual coverage result.
Neither exercise establishes classification accuracy, seasonal fidelity,
cross-border ecological comparability, or suitability of a particular class
mapping for movement inference. Those remain recipe decisions.
