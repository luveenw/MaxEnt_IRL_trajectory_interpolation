# Seasonal checkpoint and exports

Selection checkpoint: `checkpoints/selection_5bf188474d229bb43e3efde0`.
Policy: two-hour target, minimum three selected fixes, maximum native and
selected gap 4.25 hours. `exports.json` lists the latest generated export per
season. Each export is validated and published as a separate directory.

The integer trajectory arrays have columns `[row, column, spatial_move_index]`.
Actual timestamps, selected/native observations, durations, inferred grid
connections, group membership and grid definitions remain in CSV/JSON sidecars.
Keep the entire export directory, not only its `.npy` files. Arrays are movement
inputs. In `data/trajectory_manifest.csv`, `optimizer_candidate` records actual
route/grid eligibility and `inputs_bound` checks the exporter's older map/split
binding interface. **`training_ready` is a legacy placeholder hard-coded to false**;
it is not used or updated by the shared trainer, even after a successful fit.
The selection HTML reports temporal eligibility; optimizer eligibility is only
reported downstream in these export tables.

Maps and animal splits have not been supplied for the initial exports. The new
`jaguar_irl.training.shared` entry point validates run-specific inputs through
`prepare`, using named covariate bindings attached to the selection checkpoint.
See the maintained [architecture and operating manual](../../jaguar_irl/training/README_SHARED.md)
for the full workflow, eligibility summaries and the proposed replacement of
the old readiness placeholder with run-specific reporting.

## Attach feature maps later

Use the bout adapter so historical five-fix and strict four-hour defaults are
not accidentally reapplied:

```bash
python3 -m jaguar_irl.data.export_pantanal_bouts_irl \
  --checkpoint analysis/pantanal_seasonal_selection/checkpoints/selection_5bf188474d229bb43e3efde0 \
  --collection SPR-C01 \
  --output analysis/pantanal_seasonal_selection/exports \
  --feature-maps /absolute/path/feature_maps.json \
  --split /absolute/path/animal_splits.json
```

Collection IDs: WIN-C01, SPR-C01, SUM-C01, AUT-C01. The adapter calls
`export_pantanal_seasonal_irl.export_collection` with the checkpoint's rules.
It writes a new export, leaving the checkpoint and earlier exports intact.
There is no in-place rebinding command. `exports.json` is a convenience index;
when manually creating a later export, record its printed directory there or
keep it in the experiment's own manifest.

Feature-map manifest structure (replace the placeholder grid key and paths):

```json
{
  "GRID_KEY_FROM_CHECKPOINT_GRIDS_JSON": {
    "feature_map_key": "spring_covariates_v1",
    "path": "features/spring_group.npy",
    "temporal_scope": "static_declared"
  }
}
```

Each key is a checkpoint grid key, not a display group ID. The path may be
absolute or relative to this manifest. The feature array has shape
`[features, rows, columns]` or `[features, rows, columns, model_steps]`.
Six ecological covariates remain separate feature bands. Tile merging,
reprojection, spatial alignment, class coding and common feature scaling occur
before export; this exporter does not ingest GeoTIFF tile catalogs. Its map
validation checks array dimensions, not a raster's geographic transform or
biological correctness. Keep tile IDs, dates, band order, units and processing
provenance with the feature products.

`static_declared` explicitly applies one stack across the exported fragments.
For one genuinely bounded date interval, use `temporal_scope: bounded_period`
and `valid_from`, `valid_to` (start included, end excluded). A fragment must fit
entirely within that interval. This is not a recurring-season rule or automatic
map switching. Use the source timestamps' existing unspecified-clock convention.

Raster-derived feature paths, shapes and SHA-256 hashes are recorded in
`provenance/upstream_export_manifests.json`; trajectory rows contain
`feature_map_key` and `feature_map_status`. Missing maps are `not_supplied`.
Replacing feature arrays requires a new export to bind the new hashes.

## Retention diagnostics

The additional `data/season_individual_coverage.csv`,
`data/group_individual_coverage.csv`, `data/group_season_coverage.csv`, and
`data/season_summary.csv` are report diagnostics outside the immutable checkpoint.
Keep these with `selection_manifest.json`, `cutoffs.json`, and the original source
CSV for the full seasonal retention denominators. The checkpoint stores native
observations within candidate windows, not all rejected seasonal observations.
No trajectory array schema change is required for this static seasonal run.
