# General movement processor

`movement_processor.py` processes each individual's **full available record** in the input CSV. It selects observed fixes near a two-hour cadence, splits the sampled record into valid subtrajectories, and exports their grid coordinates with actual timing and source identifiers. Month boundaries and seven-day windows do not limit this processor. Its defaults apply to all individuals in the input, rather than a fixed Pantanal ID list.

The separate `movement_processor_pantanal.py` selects comparable weeks and spatial groups for Pantanal animals; see [README_PANTANAL.md](README_PANTANAL.md). The general processor does not calculate MCPs or form shared cluster maps. Both entry points use the sampling and segmentation primitives in `movement_temporal.py`. Neither trains a model or uses the old model code elsewhere in this repository.

## Run

Run from the repository root with `pandas`, `numpy`, and `pyproj` installed. Tests additionally require `pytest`.

```bash
python3 -m jaguar_irl.data.movement_processor --help
python3 -m jaguar_irl.data.movement_processor \
  --csv data/jaguar_movement_data.csv \
  --output data/processed \
  --cell-size-m 500 \
  --tile-buffer-m 20000 \
  --max-short-fragment-loss 0.05
```

Programmatic configuration exposes the remaining thresholds:

```python
from jaguar_irl.data.movement_processor import MovementProcessor, ProcessorConfig

config = ProcessorConfig(
    csv_path="data/jaguar_movement_data.csv",
    output_dir="data/processed",
    min_fixes=100,
    min_duration_days=60,
    max_gap_fraction=0.50,
    resample_interval_hours=2.0,
    regular_min_hours=1.5,
    regular_max_hours=2.5,
    max_interval_hours=4.0,
    max_affected_point_fraction=0.20,
    min_subtrajectory_points=5,
    max_short_fragment_loss=0.05,
    cell_size_m=500.0,
    tile_buffer_m=20000.0,
)
processor = MovementProcessor(config)
grid_data = processor.run_pipeline()
```

Use separate output directories when comparing settings so that outputs from different configurations remain distinguishable.

## Original individual eligibility

Eligibility is assessed on cleaned observations **before two-hour sampling**. All three original requirements remain in effect:

| Configuration field | Default | Requirement |
|---|---:|---|
| `min_fixes` | 100 | At least this many cleaned observations |
| `min_duration_days` | 60 | At least this many elapsed days between the first and last observation |
| `max_gap_fraction` | 0.50 | At most this fraction of calendar dates have no observation |

The empty-day calculation uses the **inclusive calendar-date span**:

```text
calendar_days = (last_observation.date - first_observation.date).days + 1
empty_day_fraction = 1 - distinct_observed_dates / calendar_days
```

For example, observations on 1 and 3 January span three calendar dates, with one empty date: the fraction is 1/3. This calendar-date denominator is separate from the elapsed-time calculation used for `min_duration_days`.

There is no additional 90-day or three-qualifying-month requirement in this entry point. Passing individual eligibility does not guarantee an export: an animal can still have no valid subtrajectories after cadence and bout-quality checks.

The parser removes rows with unparseable timestamps, missing coordinates, or coordinates outside valid longitude/latitude ranges. Conflicting or repeated timestamps within an individual require explicit resolution; the pipeline raises an error instead of silently choosing among them. Source timestamps retain the CSV clock convention; the processor does not infer a time zone.

## Sampling, bouts, and subtrajectories

The sampler chooses **existing observations** closest to the next two-hour target. Regular selected intervals are in **[1.5, 2.5] hours**. When no regular observation is available, a later observation may be retained; intervals in **(2.5, 4] hours** are tolerated irregular intervals, and intervals **over four hours** separate recording bouts. The cadence follows the previous selected observation rather than a fixed clock grid. No positions are interpolated.

Within a final subtrajectory, no more than **20% of unique points** may touch a tolerated irregular interval. Both endpoints count. One four-hour interval therefore affects two points; two adjacent four-hour intervals affect three points. This is neither an irregular-interval fraction nor a missing-time fraction. A four-hour interval remains four hours in the exported timing.

A bout that exceeds the affected-point limit can be split at irregular transitions. The partition maximizes retained points, then prefers fewer retained segments and fewer total blocks. Each retained segment independently satisfies the 20% limit and contains at least **five points**. Points are not duplicated between segments, and no movement transition is created across a cut.

Five points provide four observed transitions, nominally eight hours at a two-hour cadence. With the allowed 1.5-hour lower bound, five points can span six hours. This is a configurable technical minimum; it is not a guarantee of ecological representativeness or sufficient training information.

### Five-percent loss is checked separately for each bout

For each recording bout, the processor computes:

```text
short_fragment_loss = points discarded by segmentation / sampled points before segmentation
```

The denominator includes every sampled point in that bout before short fragments are removed. It excludes raw high-frequency observations intentionally skipped during cadence sampling.

- At or below **5% loss**, retain the bout's valid subtrajectories.
- Above **5% loss**, reject that entire bout, including otherwise valid segments within it.
- Other bouts from the same individual are assessed independently.

This does not require every fragment in an individual's study to have five points, and a poor bout does not by itself reject the animal's other bouts. Conversely, good bouts cannot dilute a poor bout's loss fraction. The bout audit distinguishes discarded fragments from the additional points rejected when the entire bout fails.

An otherwise sparse individual can retain a small number of valid segments under this local policy. Consult retained-point totals, segment counts, dates, and bout outcomes rather than interpreting an exported individual as evidence of uniformly good coverage throughout its record.

`sample_individual(individual_dataframe)` is a diagnostic helper: it returns sampled observations, bouts, candidate segments, and losses before eligibility or bout-loss rejection. Use `run_pipeline()` for the complete processing and export rules.

## Per-individual spatial grids

Input coordinates are WGS84 longitude/latitude, EPSG:4326. Each individual's coordinates are projected to a UTM zone determined from that individual's mean longitude and latitude; the exported EPSG identifies the actual metric CRS. Grid cells are **500 metres** by default.

The existing **20,000-metre buffer** pads each side of the rectangle enclosing that individual's retained observations. The grid is rounded outward to whole cells. This buffer is controlled by `tile_buffer_m` / `--tile-buffer-m`; it is independent of the five-kilometre MCP proximity and padding settings in the Pantanal selector. The general processor applies no MCP trimming, shared-cluster growth, or Pantanal map-area budget.

Subtrajectories from one animal share that animal's grid metadata. Row zero is at the northern edge; columns increase eastward. A row/column pair in another animal's grid does not necessarily refer to the same geographic location. Use the grid origin, cell size, shape, and CRS when constructing covariate maps or converting coordinates back to geography. Consecutive fixes in the same cell are retained observations.

## Export identity and actual time

Every subtrajectory has its own identifier while preserving the original individual ID and observation event IDs. A trajectory ID is `jaguar_<ID>_<segment-start-YYYYmmddTHHMMSS>`; a recording-bout ID is `jaguar_<ID>_b<bout-start-YYYYmmddTHHMMSS>`. Changing thresholds can change the segmentation and identifiers. Use original event IDs and timestamps to trace points back to the source CSV.

| Export | Contents |
|---|---|
| `basename.txt` | Authoritative list of trajectory basenames for the current run |
| `tracking/<trajectory_id>.npy` | Integer array with columns `[row, col, step_index]` |
| `tracking/<trajectory_id>_meta.json` | Grid, CRS, original individual ID, bout ID, source event IDs, timestamps, elapsed times, and quality metrics |
| `tracking/<trajectory_id>_meta.npy` | The same metadata dictionary in NumPy format |
| `trajectory_manifest.csv` | One row per retained segment, including dates, duration, source individual, quality metrics, and grid dimensions |
| `selected_points.csv` | Retained observations with original source columns and added identity, timing, quality, projection, and grid columns |
| `bout_audit.csv` | Every assessed bout of eligible animals, its sampled count, fragment loss, acceptance status, and rejected-point counts |
| `individual_summary.csv` | All input individuals, original eligibility, cleaned `raw_fixes`, retained `n_fixes`, retained dates, and `n_subtrajectories` |
| `processing_config.json` | Effective configuration, loss scope, source clock convention, and array-column definitions |

In the individual summary, `eligible` means the original individual-level checks passed; `retained` means at least one segment survived the later processing. Files from earlier runs can remain in `tracking/`; loaders must follow `basename.txt` instead of globbing every `.npy` file.

The integer step index in a trajectory array is an **ordinal position within that segment**, starting at zero. Metadata labels it `time_axis="observation_index_not_elapsed_time"`. It does not establish that every transition lasted exactly two hours. `dt_hours` is the interval from the preceding point within the retained segment and is empty/null for its first point; `elapsed_hours` is measured from the segment's first timestamp. In `selected_points.csv`, `source_dt_hours` also preserves the gap from the preceding sampled observation before segmentation, including breaks. Downstream code must read these timing fields when time matters; it must not infer elapsed time solely as `step_index × 2 hours`.

Training and validation assignments should be grouped by the **original individual ID** when evaluating prediction for unseen individuals. Keep all of an animal's subtrajectories in the same train, validation, or test partition. Splitting one record creates additional sequences, not additional independent animals. This processor records the identifiers needed for grouped splitting; it does not choose or execute a model-validation split.

## Checks

```bash
python3 -m pytest jaguar_irl/data/test_movement_processor.py
```

The checks cover full-record sampling across month boundaries, preservation of observed events and elapsed time, hard-gap separation, segment validity, bout-level loss handling, individual eligibility, and export metadata.

Validation against the supplied CSV (134,690 observations, 117 individuals) with the defaults above gives 76 eligible individuals and 31 individuals with retained data: 41,682 observations in 1,307 subtrajectories. Within the 56-ID Pantanal subset, 37 pass individual eligibility and 16 retain 26,755 observations. These are full-record results; they are not the Pantanal selector's week/cluster results. The inclusive empty-day correction changes no eligibility decisions on this supplied dataset.
