# Spring ESA CCI shrubland candidate-year cache

This workflow retrieves classified-area fractions for the 24 observed canonical
Spring group/year combinations on all 13 saved 500 m EPSG:32721 grids. It does
not choose a representative year, assign train/test animals, remove trajectories,
or bind a model. The selected classes are Shrubland (120), Evergreen shrubland
(121), and Deciduous shrubland (122). Fractions describe the area assigned those
labels, not measured shrub canopy percentage. They can overlap conceptual
predictors from independent MapBiomas classifications.

Executable scripts and the immutable jobs bundle live here. Raster downloads,
NPY arrays, task records and source metadata live under
`data/pantanal_covariates/spring_esa_shrubland_v1/`.

The verified Trends.Earth mirror is
`users/geflanddegradation/toolbox_datasets/lcov_esacc_1992_2022`, bands `yYYYY`.
The source snapshot pins full asset metadata/fingerprint, projection, available
bands and maintainer-config provenance before generation. The driver rejects a
changed live source. Regional pixel equality with official ESA v2.0.7 was proved
for the earlier 2005 access pilot; equality for every annual/global pixel has
not been established.

From the repository root, with the isolated extraction environment:

```bash
PYTHONPATH="$PWD" /tmp/pantanal-gee-venv/bin/python \
  gee/spring_esa_shrubland_v1/setup_cloud.py
python3 -m jaguar_irl.training.shrubland prepare \
  --checkpoint analysis/pantanal_seasonal_selection/checkpoints/selection_5bf188474d229bb43e3efde0 \
  --source-snapshot data/pantanal_covariates/spring_esa_shrubland_v1/source_snapshot.json \
  --output gee/spring_esa_shrubland_v1/jobs
PYTHONPATH="$PWD" /tmp/pantanal-gee-venv/bin/python \
  gee/spring_esa_shrubland_v1/acquire.py
PYTHONPATH="$PWD" /tmp/pantanal-gee-venv/bin/python \
  gee/spring_esa_shrubland_v1/verify_outputs.py
```

Use the isolated Python for preparation too if the default environment lacks
its dependencies. `acquire.py --pilot-only` limits execution to G316/2011, the
smallest grid. That pilot was initially exported with the batch API. The generated Code Editor JavaScript defaults to that one task;
creating a task does not launch it. Inspect existing ledgers before any manual
submission. The driver reuses existing batch task ledgers and immutable products. After
comparison showed zero numerical/mask differences between the direct and batch
pilot, remaining unsubmitted jobs switched to normal GEE small-raster direct
retrieval followed by Drive upload. Existing batch jobs were neither cancelled
nor resubmitted. `direct_batch_comparison.json` and `transport_revision.json`
record the evidence and change. Two reviewed extraction workflows each make one
request at a time; no API quota or billing setting was changed.

Direct requests preserve the exact output CRS, affine and dimensions, validate
the TIFF before upload, and reconcile uncertain Drive responses by exact
filename/checksum. Signed URLs and tokens are never saved. Their provenance
contains graph/parameter hashes, source identity, UTC status, file size/hash and
Drive identity; it does not invent a batch task ID or zero EECU usage. Reported
batch EECU usage covers only ledgered batch tasks. Interactive usage is unmeasured.
Existing batch tasks still use the conservative 20-minute wait limit; their
ledgers allow inspection/resumption. The old 1,000 completed-batch-EECU-second
submission guard applied to the original batch driver, not to all interactive
compute. Shared helper code is in `jaguar_irl/training/gee_direct.py`.

Class indicators are formed on the native angular 300 m source grid before
area-overlap-weighted averaging onto the exact model affine. There is no extra
focal smoothing, class-code interpolation, dominant-class replacement, or
normalization over only surviving valid pixels. Unknown/unobserved source
classes cause incomplete coverage, which is rejected. Every exported TIFF has
`shrubland_fraction` and `valid_fraction` bands. Conversion checks dimensions,
CRS, affine/bounds, finite values, masks, full coverage and the unit interval,
then atomically publishes `source.tif`, `shrubland_fraction.npy`, provenance and
checksums under `products/Gxxx/YYYY/`.

`acquisition.json` is the current run inventory; `verification.json` is written
only after all 24 products pass offline identity/checksum/grid/numerical checks.
Neither proves ecological classification accuracy. Production selection and
scaling must later use the agreed training-only evidence.
