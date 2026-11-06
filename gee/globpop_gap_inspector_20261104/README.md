# GlobPOP missing-pixel inspector — JavaScript for GEE Code Editor

Open the published Code Editor script or paste `inspect_globpop_gaps.js` directly
into https://code.earthengine.google.com/ and click Run with project
`perceptive-ivy-780`. This JS script has no Python dependency and performs no
exports, imputation or uploads. Python files here are optional publication tools.

Use the left dropdown for G057/2013–2015, G286/2010 or G316/2011. Red polygons
identify exact native NaN pixel footprints from the finite-value audit, orange
shows affected 500 m cells, cyan the already padded model extent. Toggle layers
for annual GlobPOP density/counts and adjacent years, GPW density and land/water
area/mask, national-priority MapBiomas classes/source/open-water, and full500m grid.
The Console prints source collections, images and audited footprint properties.
Click any point for source/context values. Native NaNs may render as transparent
or behave differently from ordinary masks; red outlines are the audited truth.

GlobPOP units: people/km² for density versus people/native pixel for counts.
GPW density uses the nearest five-year epoch (earlier on a tie); it is diagnostic,
not a chosen fallback. GPW water mask:0total water/ice,1mixed water/land,2total land,3ocean. MapBiomas class labels
are in the panel; Chaco fallback26 is displayed as national water33 for this
inspection mosaic only. No production class/source/repair policy is modified.
Satellite basemap imagery is contextual and not year-matched.

The official source reference is https://zenodo.org/records/11179644 . Exact
footprints are embedded from
`data/pantanal_covariates/globpop_production_review_20261104/finite_gap_pixels.json`;
no telemetry observations or animal identifiers are uploaded. Saved grid bounds
are included. Native footprints outside the padded domain are shown in full so
you can see their context.

Validation: JavaScript syntax checked with `node --check`; layer asset access was
verified by the underlying Earth Engine probes. Remote script bytes are verified
by the publisher. Interactive UI rendering is not claimed tested unless separately
recorded. No automatic caching/filling is performed by running the viewer.

Component comparisons added2026-11-04: same-year LandScan ambient count and
area-derived density, legacy WorldPop residential area-derived density, and GHSL
P2023A nearest-epoch residential area-derived density. These are alternative
estimates, not applied fills or claims of identical original fusion inputs.
Area conversion divides native counts by native pixel area in km²; it is a
diagnostic surface, not final conservative500m integration.

Historical GHSLP2016 epoch2015 residential density is also available as an
optional layer on an explicitly labelled0–0.2people/km² visualization scale,
to inspect tiny fractional estimates. It is not annual or a replacement for
P2023A. Running the viewer still applies no fill.
