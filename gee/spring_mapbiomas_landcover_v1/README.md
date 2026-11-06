# Spring MapBiomas land-cover candidate cache

This workflow caches 24 observed Spring group/year combinations on the 13 saved
EPSG:32721 500 m grids. It does not select final representative years or filter
trajectories. Final training-only map-year selection follows the future animal
split.

The approved features are natural grass-dominated vegetation (source code 12,
including the Bolivia grassland/shrubland label, excluding managed pasture) and
narrow flooded herbaceous/shrubby vegetation (code 11, excluding flooded forest,
flooded savanna and open water). Each output is overlap-area-weighted classified
area fraction, 0–1, without extra neighborhood smoothing.

The original highest-priority available classification is selected before
feature indicators: Brazil, Paraguay, Bolivia. An unknown code in the selected
source invalidates coverage rather than falling through to another country.
Only where all national sources are missing does Chaco code 26 Water bodies
supply valid non-target cover. Other Chaco classes are not silently accepted.
The seven exported bands are the two feature fractions, complete valid coverage,
and selected-source area fractions for Brazil, Paraguay, Bolivia and Chaco.
The latter sum to coverage. This retains the actual fallback footprint.

All source asset metadata and native projections are pinned under
`data/pantanal_covariates/spring_mapbiomas_landcover_v1/source_snapshot.json`.
Metadata fingerprints are checked before submission and on resume. The native
country grids use a shared angular pixel lattice and categorical nearest
alignment; integer class IDs are never bilinearly interpolated or averaged.

Executable code and immutable jobs are here under `gee/`; data/metadata are under
`data/pantanal_covariates/spring_mapbiomas_landcover_v1/`. Drive destination:
`columbia_ma_thesis/jaguar_irl/seasonal_covariates/pantanal_spring_mapbiomas_landcover_v1`.
The project is `perceptive-ivy-780`. No billing or API changes are made.

From the repository root, using the existing isolated EE/Rasterio environment:

```bash
PYTHONPATH="$PWD" /tmp/pantanal-gee-venv/bin/python gee/spring_mapbiomas_landcover_v1/acquire.py --pilot-only
PYTHONPATH="$PWD" /tmp/pantanal-gee-venv/bin/python gee/spring_mapbiomas_landcover_v1/acquire.py --direct
PYTHONPATH="$PWD" /tmp/pantanal-gee-venv/bin/python gee/spring_mapbiomas_landcover_v1/verify_resolved_outputs.py
```

The G115_2005 pilot exercises the cross-border mosaic and the real Chaco fallback.
Each driver submits one owned task at a time, and refuses submission when two
visible project batch tasks are already active. A 1,000 reported completed-task
EECU-second guard stops further submissions; it does not bound a running task
or total project usage. A 20-minute wait timeout preserves the existing ledger.
Uncertain responses are reconciled by task identity, never blindly retried.

Original downloaded GeoTIFFs and Drive identity/checksums are retained. Conversion
rejects shifted grids, missing/nonfinite values, incomplete coverage, out-of-range
fractions and inconsistent source-area sums. Atomic product directories contain
both NPY features, the original TIFF and provenance/checksums. These are software
checks, not validation of ecological class accuracy or a trained model.

Nine local tests cover priority/non-target/unknown-code semantics, Chaco water,
complete coverage, fractional ranges and source sums, exact candidate years,
source-version identity, half-cell shifts, missing values and bundle integrity.
The read-only native graph probe independently compares actual selected source
and class against raw source pixels in G115, including the fallback.

## Acquisition transport

The first three jobs were genuine batch exports with durable task IDs and
reported batch EECU-seconds. Subsequent small outputs use `--direct`: normal GEE
`getDownloadURL` retrieval with the same frozen image graph, explicit dimensions,
CRS and affine. The helper validates the local TIFF before uploading it to the
pinned Drive folder and verifying the remote size/MD5 and parent ID. Direct
ledgers store request graph/parameter/source hashes and Drive identity; they do
not invent batch task IDs or report zero compute usage. Interactive EECU usage
is unmeasured and remains null, separately from the known batch total.

Existing batch ledgers always finish through the batch status/download branch.
Existing direct ledgers reuse their checked TIFF and reconcile any uncertain
Drive upload instead of blindly creating duplicates. One direct job per driver
runs at a time. The batch 1,000-second submission guard cannot constrain direct
interactive compute; small output limits and bounded sequential requests apply.
The source fingerprints and image recipe are identical across transports.

A direct pilot also exercised recovery from an Earth Engine client mutation of
its input parameter dictionary; the shared helper now isolates those parameters.
The existing TIFF was reused, not recomputed. The exact original helper source
for that historical record is preserved under `gee/_historical/20261103/`.

## Approved G316 2011 repair and completed inventory

The original strict extraction accepted 23 jobs and rejected `G316_2011` for a
single masked native pixel. The user then approved exact-pixel temporal consensus:
retrieve Brazil 2010 and 2012 in GEE, require both observed classes to agree at
class 4 Savanna formation, and repair only native column 60974 / row 86248 in
2011 where all national sources are unavailable. This is not a general
interpolation policy. The actual retrieved 2010 value is used after the guards.

Executable repair code is under
`repairs/G316_2011_temporal_consensus_v1/`, including a commented JavaScript
version published as a distinct `extract_landcover_temporal_repair` script in
the existing Earth Engine repository. The original extraction script is preserved.
The frozen repair plan pins its approval record, original failed plan/product
and source fingerprint. The original rejected TIFF and ledger are retained.

`data/pantanal_covariates/spring_mapbiomas_landcover_v1/repair_resolution.json`
maps only that job to its new repair plan, product key and ledger. Its canonical
NPYs now occupy `products/G316/2011/`. The complete current `acquisition.json`
indexes all 24 jobs and identifies the repair explicitly. Its original 23-job
record is retained at `provenance/acquisition_before_G316_repair.json`; the old
partial verification remains unchanged.

The repaired TIFF preserves the original first seven band positions. Band 2
`valid_fraction` now denotes effective supported coverage; the four country/source
fractions remain observed current-year support only. Band 7 is
`observed_valid_fraction`, and band 8 is `temporal_imputed_fraction`. The four
source fractions sum to observed coverage; observed plus imputed coverage sums
to effective coverage. Only model cell row 20 / column 13 has nonzero temporal
support, approximately 851.47 projected square metres. Observed coverage there
remains 0.99659413 while effective coverage is 1. No observation is relabeled as
observed solely because it was temporally imputed.

For a guarded repair resume, use:

```bash
PYTHONPATH="$PWD" /tmp/pantanal-gee-venv/bin/python \
  gee/spring_mapbiomas_landcover_v1/repairs/G316_2011_temporal_consensus_v1/acquire.py
```

The original acquisition coordinator deliberately stops with this command and
resolved-verifier instructions when a repair is registered. It cannot blindly
retry the historical failed job. `verify_resolved_outputs.py` verifies all 24
jobs / 48 NPY arrays against each job's effective plan. Scientific ecological
accuracy remains unvalidated; cached candidate years are not final map years.
