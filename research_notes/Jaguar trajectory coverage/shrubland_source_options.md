# Consistent shrubland source options for the Pantanal

Investigated 2026-11-03 (America/New_York), as an explicitly requested subagent
sidequest. This records source research and read-only API probes, not an adopted
shrubland recipe or production export. The user separately accepted the Chaco
fallback for the already diagnosed MapBiomas holes; that decision does not
select a shrubland source.

**Subsequent access result:** the user selected ESA CCI. The documented
Trends.Earth GEE mirror was then found and its 2005 regional subset matched the
official CEDA v2.0.7 raster pixel-for-pixel. See
[the completed access report](esa_cci_gee_access.md); the initial access uncertainty
below is retained as investigation history, not the current access status.

## Recommendation

**Investigate ESA CCI first for fidelity to Alvarenga; retain GLC_FCS30D as a
promising finer-resolution alternative for an explicit adaptation.** Both use
global classifications, avoiding a different shrubland definition at each
national boundary. MODIS is technically straightforward but almost never labels
our Spring domains shrubland under its IGBP legend. WorldCover is temporally
inappropriate for these historical tracks.

A common legend supplies definitional consistency, not proof of local accuracy
or equal errors among countries. Before choosing the source, inspect actual ESA
class presence and compare representative patches against independent imagery
or suitable reference data. A preference for more mapped shrubs is not an
accuracy criterion. The large MODIS/GLC disagreement below makes this review
important.

## What Alvarenga (2021) actually did

Section 2.3 and Table 1 identify ESA Climate Change Initiative Land Cover
(ESA, 2017), at **300 m**, as the source for grassland, shrubland and flooded
habitats. They converted these categories into separate binary layers, then
resampled all raster layers to 500 m and reprojected to Plate Carrée. This is
use of an existing classified land-cover product, rather than a separately
reported shrub-detection algorithm fitted to their jaguar data.

The paper does **not** supply the exact annual map band, shrubland numeric-code
crosswalk, or categorical resampling algorithm. Its ESA reference points to the
project website. Our existing R helper's codes **120, 121, 122** are a plausible
legend-based reconstruction, not an author-published code table or confirmed
reproduction. [Alvarenga paper, §2.3 and Table 1](https://www.fs.usda.gov/rm/pubs_journals/2021/rmrs_2021_alvarenga_g001.pdf).

## ESA CCI / Copernicus C3S: closest source family

The global annual land-cover series has a nominal **300 m** grid and covers all
three countries and all our 2005–2016 movements. ESA's data page describes
1992–2020; the current Copernicus record describes 1992 to present. The historical
CCI maps through 2015 use v2.0.7, with operational C3S continuation from 2016.
Pin the exact release and annual file rather than inferring map year from the
2017 citation. All required current Spring years (2005, 2006, 2008–2015) fall
within the historical CCI portion.
[ESA product description](https://climate.esa.int/en/projects/land-cover/data/),
[Copernicus dataset and versions](https://cds.climate.copernicus.eu/datasets/satellite-land-cover?tab=overview).

The official legend explicitly separates:

- 120: shrubland; 121: evergreen shrubland; 122: deciduous shrubland.
- 152: sparse shrub cover below 15%, within the sparse-vegetation branch.
- 100/110: tree/shrub/herbaceous mosaics, not pure shrubland labels.
- 180: flooded shrub/herbaceous vegetation, distinct from dry shrubland.

A candidate strict shrubland indicator is `class in {120,121,122}`. Including
152 or mosaic categories would broaden the feature and needs justification.
The PUG describes the shrub classes using natural/semi-natural terrestrial
shrub/thicket LCCS categories. Do not import MODIS's 1–2 m or 10–60% thresholds
into ESA classes. [Official CCI legend](https://maps.elie.ucl.ac.be/CCI/viewer/download/CCI-LC_Maps_Legend.pdf),
[2017 product user guide](https://climate.esa.int/media/documents/CCI_Land_Cover_PUG_v2.0.pdf).

These annual maps derive from a 2003–2012 baseline updated backward/forward with
change detection; an annual label is not an independent Spring observation.
At this scale, small shrub patches can be missed or incorporated into mosaics.
[ESA production description](https://climate.esa.int/en/projects/land-cover/data/).

**Access:** official downloads are available through the ESA/UCL portal and
Copernicus Climate Data Store as NetCDF. We did not identify a documented
standard GEE catalog asset for this series. The guessed `ESA/CCI/LC` ID returned
not found in the live API; that does not establish that no mirror exists.
A July 2026 ECMWF staff response says GEE catalog integration was being asked
about internally, rather than documenting an available asset. Therefore use a
verified mirror only after checking provenance, or download the necessary
annual spatial subsets and import categorical GeoTIFFs to GEE assets. Preserve
class values/NoData and use categorical pyramiding; never bilinearly interpolate
class numbers. No such import was performed here.
[Official download portal](https://maps.elie.ucl.ac.be/CCI/viewer/download.php),
[ECMWF staff response](https://forum.ecmwf.int/t/esa-cci-lc-landcover-23-24-25-updates/15175/2),
[GEE import guide](https://developers.google.com/earth-engine/guides/image_upload).

## GLC_FCS30D: a plausible 30 m alternative

The authors' global product supplies consistent fine land-cover categories
across national boundaries. It is annual during **2000–2022** and five-yearly
before 2000, covering our entire movement period. Its legend includes shrubland
120, evergreen shrubland 121, deciduous shrubland 122 and a separate sparse-shrub
class 152 (`fc < 0.15`). Its classes and mapping method should not be described
as an exact reproduction of ESA CCI or Alvarenga.
[Primary methods paper](https://essd.copernicus.org/articles/16/1353/2024/),
[Authors' versioned data and user guide](https://zenodo.org/records/15063683).

The public community mirror is live-readable in GEE:

```javascript
var tiles = ee.ImageCollection(
  'projects/sat-io/open-datasets/GLC-FCS30D/annual'
);
// Its 23 bands b1...b23 correspond to years 2000...2022.
var map2005 = tiles.filterBounds(region).mosaic().select('b6');
var shrub2005 = map2005.eq(120).or(map2005.eq(121)).or(map2005.eq(122));
```

This is a **community-hosted mirror**, not a Google-managed or author-owned
catalog entry. Its provenance page was used only for mirror access instructions;
the class definitions/methods above were checked against author sources. The
mirror was last documented as uploaded in 2024, whereas the authors' Zenodo
record has a 2025 v2. Matching the mirror's bytes to that newer version has not
been established. A production choice requires pinning the mirror/version or
importing the desired author release. [Mirror access documentation](https://gee-community-catalog.org/projects/glc_fcs/).

## MODIS MCD12Q1: direct historical access, different shrub definition

`MODIS/061/MCD12Q1` is a global annual nominal-500 m GEE ImageCollection. Its
`LC_Type1` IGBP classes 6/7 are closed/open shrublands: woody perennials
approximately 1–2 m tall, with respectively over 60% or 10–60% cover. These
thresholds differ from simply reusing an ESA class name. Native MODIS uses a
sinusoidal grid; nominal 500 m pixels do not align with our exact 500 m UTM grid.
The live collection contains annual images from 2001–2025, despite the catalog
summary stopping at 2024. Pin an exact image/year in any future recipe.
[NASA/USGS GEE catalog and class descriptions](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MCD12Q1),
[MODIS user guide](https://modis.ornl.gov/documentation/guides/MCD12_User_Guide_V6.pdf).

The direct-access convenience is not enough to recommend it as primary here:
our spatial probe found no classes 6/7 in nine of ten Spring years, and only
about 0.553 weighted pixel-equivalents of class 6 in 2006. This is source-label
scarcity, not proof that shrubs were absent on the ground. MODIS could serve
as a comparison product, with the scheme and QA layers stated explicitly.

## WorldCover: consistent globally, wrong observation years

`ESA/WorldCover/v100` supplies 2020 and `ESA/WorldCover/v200` supplies 2021 at
10 m, with a shrubland category. Both were directly accessible in the live API.
Those dates follow our 2005–2016 movements; using them would require an explicitly
accepted temporal mismatch, not representative-year extraction for these tracks.
[2020 catalog](https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v100),
[2021 catalog](https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200).

## Live probe evidence and limits

[probe.py](../../gee/shrubland_source_audit_20261103/probe.py)
and [probe.json](../../data/pantanal_covariates/shrubland_source_audit_20261103/probe.json)
retain availability, image metadata and class histograms over the union of the
13 Spring rectangles for all ten required years. The probe queried MODIS at
500 m and the GLC mirror at 30 m. These are screening histograms, not exact
UTM-grid class fractions, cell-by-cell full-coverage certificates or validation
of classification accuracy. Histogram counts have boundary weights and must
not be interpreted as exact ground areas.

The GLC mirror returns two intersecting tiles and all 23 expected annual bands.
Classes 120/121 are present in every required year, while 122/152 were absent
from this screening query. The combined 120/121 counts range from about 1.14
million to 1.49 million weighted pixel-equivalents. That considerable difference
from MODIS warrants inspecting mapped patches and class definitions. We did not
read ESA classification pixels in this investigation, so ESA's shrub abundance
and detailed masks in these domains remain unverified.

The downloaded official CCI PUG and GLC author guide, and extracted text, are
retained with the audit. No cloud export, private asset copy, learned scaling,
animal split, new shrubland feature or production raster was created.

## Proposed next scientific/implementation decision

If preserving the paper's predictor meaning is the priority, obtain a verified
ESA CCI annual subset and inspect whether `{120,121,122}` gives a meaningful
shrubland signal in these domains. If a finer-resolution adaptation is desired,
review GLC_FCS30D patches against the ESA baseline/reference imagery and establish
the mirror's version before adoption. A future 500 m fraction would represent
**the area classified as shrubland**, not measured shrub canopy percentage.

Using ESA/GLC shrubland alongside MapBiomas grassland/wetland is technically
possible, but independent products may overlap or disagree within the same
location. Those predictors would not constitute an exclusive partition of one
land-cover map, and their fractions need not sum to one. Preserve that meaning,
check redundancy/contradictions, and do not force renormalization across sources.
