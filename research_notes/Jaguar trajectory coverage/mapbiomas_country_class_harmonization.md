# MapBiomas country-class harmonization investigation

Checked 2026-11-03, America/New_York. This is a research proposal, not an approved
land-cover extraction recipe. The user selected **Brazil → Paraguay → Bolivia**
as the overlap priority. That is an operational preference; national project age
does not independently demonstrate local or class-specific accuracy.

## Findings that affect this project

Direct querying works, but equal numeric codes do not guarantee equivalent
categories. Current source IDs are pinned in the earlier
[access investigation](mapbiomas_access_and_coverage.md): Brazil Collection 11 v3,
Paraguay Collection 3 v1 and Bolivia Collection 4 v1. Official current legends
and live histograms were checked rather than reusing older MapBiomas code lists.

The principal result is that a broad common land-cover classification is
feasible, while a strict three-feature grassland/wetland/shrubland reconstruction
is not uniquely determined by these national products. Class 11 is the strongest
candidate correspondence. Class 12 supports a broader grass-dominated-open
vegetation concept. A separate shrubland indicator is not directly recoverable
consistently across these sources.

### Country definitions

Brazil Collection 11 distinguishes code 12 grassland, code 11 flooded grassland/
wetland, code 4 savanna, code 6 floodable forest and **code 7 flooded savanna
(beta)**. Code 50 is coastal herbaceous/shrub vegetation, not flooded savanna.
Code 77 is a herbaceous/shrub formation class; the current asset notes the
13→77 remapping. It is absent from all country-specific Brazil pixels in this
Spring audit. The official Pantanal descriptions allow scattered shrubs in
code 12; savanna code 4 has a woody/herbaceous structure, not a pure shrub layer.
[Brazil current product legend and biome descriptions](https://brasil.mapbiomas.org/iniciativas-e-produtos/cobertura-e-uso-da-terra/cobertura-30m/cobertura/).

Paraguay Collection 3 code 3 includes closed natural woody vegetation, without
separating trees and shrubs; code 4 is open woody vegetation. The descriptions
use over 65% woody canopy for code 3 and 15–65% for code 4. Code 6 includes
flooded woody vegetation, including palms; code 11 is flooded herbaceous
vegetation. Code 12 is grassland with permitted minor woody cover. Code 15 is
managed forage pasture. The legend has no separate shrubland class.
[Paraguay Collection 3 legend](https://paraguay.mapbiomas.org/wp-content/uploads/sites/11/2026/09/PY-LC-Col-3-Legend-code.pdf),
[Paraguay descriptive legend](https://paraguay.mapbiomas.org/wp-content/uploads/sites/11/2026/09/1.Descripc_Leyenda_ES-PRY.pdf_COLECCION_3.pdf).

Bolivia Collection 4 calls code 12 **grassland/shrubland**. Its Pantanal
description is herbaceous-dominated vegetation with isolated shrubs and stunted
woody plants, broadly compatible with the regional Brazil grassland concept,
but not evidence of a strict grass-only partition. Code 11 is flooded grassland/
shrubland; code 6 is flooded forest. Code 4 is open forest. Bolivia additionally
has code 66 scrubland and code 77 open shrubland (beta), but neither occurs in
our source-specific Spring grid audit. Such labels cannot be used to infer
absence of shrubs inside other categories.
[Bolivia current legend](https://bolivia.mapbiomas.org/wp-content/uploads/sites/5/2026/09/Leyenda_Code_Bolivia_Col4.pdf),
[Bolivia regional descriptions](https://bolivia.mapbiomas.org/wp-content/uploads/sites/5/2026/09/Leyenda_Descriptiva_MB-Bolivia-Col-4_Gral_ES.pdf).

### Actual codes present and surviving the priority

Read-only Earth Engine histograms covered the union of all 13 exact Spring
rectangles for 2005, 2006 and 2008–2015 on the source grid. No rasters were
exported. Unmasked codes other than 0/27 were considered observed.

- Brazil: 3, 4, 7, 11, 12, 15, 21, 25, 29, 33, 39, 41.
- Paraguay: 3, 6, 11, 15, 25, 33.
- Bolivia: 3, 11, 12, 33.

A separate audit masked Paraguay where Brazil was valid, and Bolivia where
Brazil or Paraguay was valid, for each year. **Every listed source-specific
code still occurs after priority selection.** Bolivia code 12 is selected in
every checked year, ranging from approximately 873 to 1,151 weighted native
pixel equivalents. Paraguay code 6 also survives every year, approximately
477,440–655,994 weighted native pixel equivalents. These frequency histogram
counts include fractional boundary weights; they are neither exact integer
pixel counts nor ground areas. Consequently, the definition mismatches are
relevant to the actual proposed mosaic rather than only hypothetical.

The inspected native grids share EPSG:4326 and pixel spacing. Their origins
are on the same lattice: relative to Brazil, Paraguay is offset by 40,797
columns/90,814 rows and Bolivia by 7,476 columns/52,276 rows (within floating-point
roundoff). This supports nearest-neighbor categorical alignment for these pinned
sources. A future product version still needs its grid checked independently.

The evidence is in
[raw/source histograms](../../data/pantanal_covariates/mapbiomas_class_audit_20261103/observed_classes.json)
and [priority-selected source histograms](../../data/pantanal_covariates/mapbiomas_class_audit_20261103/priority_selected_classes.json).
Both portable read-only query scripts are saved alongside the results. The
source country metadata alone is not a political border mask: the raster
footprints overlap, and source selection should remain traceable.

## Proposed common classes and feature decisions

[proposed_crosswalk.json](../../data/pantanal_covariates/mapbiomas_class_audit_20261103/proposed_crosswalk.json)
handles every code observed in this audit. It preserves distinctions rather
than claiming the national legends are identical. Unknown future codes stop
for review. Proposed broad coarsenings include natural closed woody vegetation,
natural open woody vegetation, flooded woody vegetation, flooded savanna,
wet natural herbaceous/shrub vegetation, grass-dominated natural open vegetation,
managed pasture, land-use mosaic, nonvegetated land, rocky outcrop, open water,
soybean and other temporary crops. Source country and original code must survive
as provenance because broad class agreement does not erase thematic differences.

For the three candidate predictors:

- **Grassland:** code 12 in all three countries is a reasonable candidate for
  a grass-dominated natural-open-vegetation fraction, with an explicit regional
  compatibility caveat. It is broader than pure grass cover and excludes
  code 15 managed pasture. It is a proposed ecological definition, not an exact
  ESA CCI class identity.
- **Flooded habitat:** code 11 across the countries is a defensible candidate
  for the narrow herbaceous/shrub wetland concept. Keep open water (33), flooded
  woody vegetation (6) and flooded savanna (Brazil 7) distinct. Including 6/7
  would broaden the predictor and should be an explicit scientific choice.
- **Shrubland:** no consistent standalone class exists for our actual selected
  national categories. Neither savanna code 4 nor every woody code 3/6 can be
  renamed shrubland. Do not produce an all-zero shrubland layer. Options are to
  defer this feature, redefine a common woody/open-vegetation predictor with
  review, or investigate a separate source that resolves shrubs consistently.

Tree canopy percentage remains a different measurement from a categorical
forest/woody area fraction; none of these crosswalks supplies continuous tree
canopy closure or tree-versus-shrub partitioning. Retain the separate tree-cover
source/epoch discussion.

## Correct implementation of the selected priority

Harmonize the source legend labels, but retain all supported valid source classes.
At each fine-resolution location/year choose Brazil when it has a valid class,
otherwise Paraguay, otherwise Bolivia. **Only then derive target indicators.**
A valid Brazil grassland pixel contributes wetland=0 and must not fall through
to a Paraguay wetland label. An unsupported or ecologically ambiguous Brazil
class must be surfaced for review, not treated as missing merely to obtain a
more convenient lower-priority answer.

Store source ID, original class, target mapping status, beta-class flag,
observed/imputed status and coverage independently. For a future 500 m feature,
aggregate class indicators by overlap area after harmonization and source
selection. Never average class IDs or bilinearly interpolate categories.
Source-to-target grid alignment and the exact choice of feature fractions still
need the production recipe review.

## Chaco fallback for genuine national gaps

The exact Chaco Collection 5 legend identifies code 26 as **water bodies**;
its detailed legend describes permanent surface water. It can map to the
common `open_water` class as a separate gap-only source, if that fallback is
adopted. This is verified directly from the Chaco legend, not inferred from
Paraguay's 26→33 asset remap. Open water is not code 11 flooded vegetation.
[Chaco Collection 5 code legend](https://chaco.mapbiomas.org/wp-content/uploads/sites/2/2024/12/MB-Chaco-Col-5-pdf-Legend-Code.pdf),
[Chaco Collection 5 descriptions](https://chaco.mapbiomas.org/wp-content/uploads/sites/2/2024/08/MB-Chaco-Col-5-pdf-Legend-Descript-ES.pdf).

See the separate G115 gap diagnosis for pixel-level spatial/year evidence and
recommendations; national priority must remain intact wherever any of the three
national sources is valid. A gap-only Chaco fallback does not justify replacing
the full national mosaic with Chaco's broader woody/herbaceous categories.

## Evidence and limits

Official current country legend PDFs, extracted text, originating page URLs,
observed histograms and proposed mappings are saved under
`data/pantanal_covariates/mapbiomas_class_audit_20261103/`. The web reader could
not open several current Paraguay PDFs; authenticated account access was not
required, and ordinary HTTP requests to their official public URLs succeeded.
Those exact PDFs were read locally and retained for audit.

The work establishes class semantics, observed categories and priority behavior.
It does not scientifically validate national classification accuracy, adopt
new feature definitions, select a map year, approve a gap-filling policy or
create production covariates. Brazil-first priority follows the user's chosen
preference, without claiming that it maximizes accuracy in every overlap.
