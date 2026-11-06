# Current seasonal selection (November 2, 2026)

The default command now uses **all qualifying local bouts**, pooling each season
across study years, with a two-hour target (regular band 1.5–2.5 hours), at least
three selected fixes, and a maximum native AND selected gap of **4.25 hours**.
No weekly window, density/span gate, affected-point budget or season buffer is
applied. The implementation delegates to `BoutProcessor`; its strict four-hour
programmatic default remains available for historical comparisons.

```bash
python3 -m jaguar_irl.data.movement_processor_pantanal_seasonal
```

Open `analysis/pantanal_seasonal_selection/index.html`. `cutoffs.json` is the
active policy; the HTML uses `pantanal_bout_report.py`. One complete collection
per season is the default; `--max-collections` requests alternative map covers.
All qualifying bouts must survive each cover. Spatial settings and approved
season boundaries are unchanged. These are temporal eligibility results, not
validated model-ready trajectories or proof of habitat fidelity.

New CSVs:

- `data/season_individual_coverage.csv`: all 56 animals × four seasons, including
  zero-retention animals and seasons without observations.
- `data/group_individual_coverage.csv`: retention for each animal in each spatial
  group. Alternative group rows can repeat evidence; do not sum across groups.
- `data/group_season_coverage.csv`: pooled retention within each spatial group.
- `data/season_summary.csv`: deduplicated seasonal totals and retention.

`selected_retention_pct` is 100 × selected fixes / all QC-passed native fixes
recorded for the relevant individual(s) in that season across all years.
`native_preservation_pct` uses all native observations within accepted bouts as
its numerator, including unselected finer observations and trailing fixes.
Rejected short bouts remain in the denominator. A blank percentage means no
native fixes; zero means native fixes existed but none survived. These are not
scheduled-fix success rates or percentages of calendar time covered. Seasonal
pooled denominators include all 56 animals; group denominators include only their
member animals. Pooled ratios are calculated from summed counts.

For checkpoint export, use `export_pantanal_bouts_irl`, which reads the policy
identity and preserves the matching 4.25-hour cap. The old four-hour policy is
also supported. No real covariate maps or IRL training are generated here.

The previous weekly report is preserved under `legacy_weekly_*` in the analysis
folder; old immutable checkpoints remain in `checkpoints/`.

## Historical weekly workflow

The documentation below describes the superseded weekly selector. Reproduce it
with **`--legacy-weekly --output SOME_OTHER_DIRECTORY`** in addition to the old
options. Weekly-only options without `--legacy-weekly` are rejected.

# Seasonal Pantanal selection and plain-MaxEnt export

This pipeline selects seasonal collections of spatially bounded groups from the 56-animal Pantanal cohort. Group selection uses approximately two-hour observed tracks. Checkpoints preserve every parsed source observation inside each retained candidate window, enabling fine-cadence and two-hour model treatments from the same selected periods. Collections maximize coverage over the generated eligible groups and record which repeated windows may contribute once to training.

The entry point is [`movement_processor_pantanal_seasonal.py`](movement_processor_pantanal_seasonal.py). It reuses the established parser, temporal screens, MCP95 construction and group scoring through imports. [`pantanal_seasons.py`](pantanal_seasons.py) defines calendar boundaries; [`pantanal_seasonal_collections.py`](pantanal_seasonal_collections.py) builds collections; [`pantanal_seasonal_report.py`](pantanal_seasonal_report.py) renders the report. [`export_pantanal_seasonal_irl.py`](export_pantanal_seasonal_irl.py) exports one explicit collection by reusing the established grid and export primitives.

## 1. Generate and inspect a seasonal selection

Run from the repository root:

```bash
python3 -m jaguar_irl.data.movement_processor_pantanal_seasonal \
  --sampling-days 7 \
  --season-buffer-days 7 \
  --max-collections 7
```

The default output directory is `analysis/pantanal_seasonal_selection/`. The command prints its immutable checkpoint directory. Open `index.html` to inspect season navigation, ranked collection alternatives, collection maps and timing charts, group details and the individual audit. Generated CSVs live in `data/`; generated SVGs live in `images/`. `--no-report` produces selection/checkpoint/backing products without rendering HTML/figures.

Useful settings:

- `--csv PATH`: source movement CSV; default `data/jaguar_movement_data.csv`.
- `--collar-metadata PATH`: sex/schedule metadata; default `data/Jaguar_additional_information_fixed.csv`.
- `--output PATH`: separate report/backing/checkpoint directory. The implementation rejects the locked `analysis/pantanal_selection/` directory and its descendants.
- `--sampling-days D`: duration of each individual candidate period; default 7. Candidate periods may cross month/year/season boundaries subject to buffered-season membership.
- `--season-buffer-days B`: extension before and after each season; default 7. This is independent of sampling duration.
- `--min-observed-span-days D`: main-window first-to-last retained span. When omitted, it scales as `sampling_days * 6.5/7`; the default is 6.5 days. It measures observed span, not continuous monitoring coverage.
- `--max-collections N`: maximum distinct alternatives retained per season; default 7. Fewer may exist.
- `--seasons-json PATH`: JSON list of season definitions, or an object containing a `seasons` list. Each definition supplies `name`, `start_month`, `start_day`, `end_month`, `end_day` and a description. Definitions must partition the year without gaps or overlaps.
- `--growth-buffer-km`, `--map-padding-km`, `--max-side-km`, `--max-area-km2`: spatial settings; defaults 5 km, 5 km, 40 km and 1,600 km². Distances are converted to metres for the projected calculations.

Other temporal/spatial settings are explicit in `TemporalConfig` and `SpatialConfig`, used by `SeasonalConfig`. Change them through a separately recorded configuration/version; do not silently alter the locked module defaults. The 500-m cell size is recorded in every grid contract.

## 2. Season attribution

The source is [Climates to Travel: Pantanal](https://www.climatestotravel.com/climate/brazil/pantanal). The page contents were verified in the user's open browser on 2026-11-01. It describes summer through late March and autumn from April to mid-May. The exact continuous date interpretation was separately approved by the user: summer ends March 21 and autumn begins March 22. This March boundary is an operational definition that differs from the page's approximate seasonal wording, not an exact date quoted from the source.

Core periods are half-open, with the ending boundary belonging to the next season:

- **Winter:** May 15 through August 14; `[May 15, August 15)`.
- **Spring:** August 15 through November 14; `[August 15, November 15)`.
- **Summer:** November 15 through March 21 of the following year; `[November 15, March 22)`.
- **Autumn:** March 22 through May 14; `[March 22, May 15)`.

`season_year` is the core period's starting year. Thus summer 2013 includes early 2014. Groups and collections may combine different calendar years within the same season. The initial model comparison is season-specific; animal folds do not need additional seasonal balancing within that experiment.

For a configured window `[start,end]`, membership requires the **entire inclusive sampling window** to fit inside `[core_start - buffer, core_end + buffer)`. A period extending beyond that envelope does not qualify through a small overlap. A window fitting two neighboring buffered seasons may be attributed to both; its source identity remains shared. `window_seasons.csv` records every applicable occurrence and all four boundaries.

Actual observed months/years come from timestamps, including partial months. The HTML highlights out-of-core observations in red and marks affected month labels in bold italic. A mid-month transition can make one month contain both core and buffer observations; that label does not mean the whole month lies outside the season. Calendar envelopes must not be used to invent observations between disjoint years or windows.

## 3. Selection, maps and collections

Each actual source fix is evaluated as a potential start. Qualifying candidates compete by rank per animal, season occurrence and main/relaxed category. Monthly preselection does not restrict this scan. Main windows supersede relaxed alternatives for the same animal/season occurrence. Group pools include both common-season-year and mixed-year alternatives.

Selection uses the established rules:

1. Retain the first observation, then choose the observation closest to +2 hours within inclusive `[1.5,2.5]` hours; ties prefer the earlier observation. If no regular observation exists, choose the earliest later observation at least 1.5 hours away. Actual times remain attached.
2. Split gaps greater than four hours. Exactly four hours may remain. Additional cuts can occur at `(2.5,4]`-hour edges to meet a pooled budget: unique endpoints of retained irregular edges must be at most 20% of all thinned observations in the entire candidate period before fragment removal.
3. Retained selector subtrajectories contain at least five observations. Reject a candidate if dropping shorter fragments loses more than 5% of its thinned observations. Cuts themselves do not remove observations.
4. Main windows satisfy the computed 80% expected-schedule count and observed-span minimum. For seven days at two hours, the inclusive reference is 85 observations and the minimum retained count is 68. Relaxed windows may carry measured density/span exceptions; protected cadence, segmentation and fragment-loss rules still apply.
5. Full-record duration and month availability remain descriptive. They do not reintroduce the removed 90-day/three-supported-month filters.

Full-study MCP95s use each animal's complete parsed record, independently of candidate weeks. The radial trimming convention retains points at/below the 95th percentile of distance from the mean projected location, including ties, then forms a convex hull. These MCPs are proximity proxies. Group maps include the MCPs plus selected-window **fine source excursions**, then padding. Coordinates are transformed from WGS84 longitude/latitude (`EPSG:4326`) to `EPSG:32721`; rectangle bounds are snapped outward to the 500-m grid. Grid rows run southward and columns eastward from the upper-left origin.

Group growth uses the existing proximity and map-budget constraints, preventing unlimited chains of nearby ranges. An otherwise eligible animal absent from multi-animal groups can have a singleton group. Relaxed groups supplement individuals absent from the main-group union for that season. Rankings retain point-count/evenness and quality priorities, with main groups preceding relaxed groups.

Collection construction considers groups in rank order, with bounded rank-seeded alternatives. It covers the attainable union of eligible generated-group members, removes groups whose members are already fully represented by other retained groups, and ranks distinct alternatives by unique animals covered, extra memberships, group count and constituent ranks. Coverage is maximal over the supplied candidate union. Compactness is a deterministic greedy heuristic, not a proven minimum set cover. `compactness_is_optimal=False` and the seed limit make this explicit.

An animal may contribute several **nonoverlapping** windows. Identical windows and any inclusive-bound overlap are assigned to the first accepted window in main-first group-rank order. Suppressed memberships remain visible as `duplicate_window` or `overlapping_window`, with the canonical group/window identified. Counts distinguish unique animals, animals repeated across groups and extra group memberships. A repeated group membership is not automatically an additional independent training example.

## 4. Report and backing data

The report navigation links seasons to collections and collections to canonical group sections. A group attributed to multiple seasons has one section. Collections show membership/coverage metrics, a compact month-by-animal chart, a detailed dated timeline, full-study MCP95 locations and selector subtrajectory IDs. Repeated individuals are visually marked. Compact charts use three-letter months ordered from the configured buffered season start. Detailed timelines separate year panels, display exact dates in a companion table, and distinguish selected windows from suppressed duplicate/overlapping windows with solid versus dashed outlines. Ranking rows beyond the first seven are expandable; floating shortcuts link to top, seasons, collections and tables.

Each collection also has an **optional expandable weekly density view**. Rows identify animals; columns are exact Monday-start calendar weeks, `[week_start, week_end_exclusive)`. Panels use `season_year`, the season's starting year, so a summer spanning November through March stays in one panel. Only `collection_members.selection_status == "selected"` contributes. Counts use retained selector `window.points` observations, deduplicated per animal by original source-event key/source-row/event ID (timestamp fallback); suppressed memberships and additional fine-source fixes do not inflate counts.

A shared observed-count color scale applies across all panels of one collection, with numeric counts shown inside populated cells. The scale is not a percent-coverage scale; counts can exceed the nominal 85-fix seven-day reference under tolerated interval variation. Dashed cell outlines indicate that the union of selected parent-window envelopes occupies less than 168 hours of that calendar week. This exposure is an envelope duration, not proof of uninterrupted telemetry. Red underlines identify buffer-only observations; half-width red underlines identify cells containing both core and buffer observations. Empty cells mean no retained selected observations. Duplicate membership badges remain descriptive even though their observations are counted only once. Exact bin dates/counts/exposure are supplied in the CSV, without requiring hover interaction.

Report backing files under `data/`:

- `groups.csv`: group display ID/rank, `grouping_calendar_season`, season memberships, animal IDs, quality flags, retained counts/CV/Jain, selected/full-study spans, sex counts, map rectangle and grid dimensions.
- `collections.csv`: collection display/key/season/rank, group IDs, unique individuals, repeated-individual IDs, membership counts, extra memberships, selected/suppressed window counts, attainable union, unrepresented cohort IDs and actual month/year coverage.
- `collection_weekly_density.csv`: one collection/season-year/individual/calendar-week row, including zero-count rows within each represented season-year’s buffered interval. Fields include exact `week_start`/`week_end_exclusive`, `retained_fix_count`, `core_fix_count`, `buffer_fix_count`, `season_support` (`core_only`, `buffer_only`, `mixed`, `none`), `selected_window_overlap_hours`, `partial_selected_week`, exact first/last retained timestamps, contributing group/window IDs and descriptive membership multiplicity. Summing counts per collection reconciles to its unique canonically owned selector observations. This report diagnostic is derived from selection data; it does not modify the immutable checkpoint or export eligibility.
- `collection_members.csv`: one collection/group/animal/window relationship, its `selection_status`, canonical group/window, date bounds and selector subtrajectory IDs.
- `windows.csv`: returned candidate window identity, animal, bounds, quality/retention metrics, flags and season attributions.
- `group_members.csv`: group/window/animal relationships and window diagnostics.
- `trajectory_manifest.csv`: selector subtrajectory summaries linked to group, window and `grouping_calendar_season`.
- `selected_points.csv`: thinned selected observations with group/window/selector-trajectory identity and original event/source references.
- `individual_audit.csv`: all requested individuals, study, source counts/span, scan counts, protected rejection reasons and season-specific qualifying counts. The `season_diagnostics` JSON object records per-season scanned/main/relaxed/protected-rejected counts, strict and density/span rejection-code counts, a concise `summary`, and numeric `best_protected_rejected_window` / `best_relaxed_window` evidence. Evidence includes exact start/end, season-year attribution, M/F counts, affected-endpoint budget, short-fragment loss and ceiling, hard-gap count/maximum, reference density and observed-span requirements, and fragment/cadence thresholds. Best protected-rejected evidence maximizes retained fixes, then minimizes fragment loss, then maximizes resampled count and retained span; best relaxed evidence follows the existing window score. These diagnostic choices do not alter window selection. A window may count in adjoining seasons, so seasonal totals need not sum to the overall scan count.

JSON arrays/dictionaries inside CSV cells must be parsed as JSON. `selection_manifest.json` is renderer input and full run configuration. `seasons.json` records exact boundaries, provenance, buffer, duration and membership semantics. `mcp95_full_study.geojson` contains full-study hulls. The immutable checkpoint is the authoritative input to the exporter; the thinned report CSV alone cannot reconstruct fine observations.

## 5. Immutable checkpoint contract and joins

Each run publishes `checkpoints/selection_<hash>/`. Its `checkpoint.json` retains the compatible base checkpoint schema plus `seasonal_schema="pantanal_seasonal_checkpoint/1"`, source/configuration/software identities, counts, selection policy and file hashes. The seasonal code hashes are part of configuration identity. Report limits do not determine checkpoint coverage.

The checkpoint contains:

- `source_points.csv`: deduplicated original parsed observations, keyed by `source_event_key`, with animal/event/source-row identity, timestamps/timezone status, coordinates, study, country, tag, QC status and original-record JSON. It includes the union of returned windows, not every scanned window or all full records.
- `windows.csv`: `window_key` and human-readable `window_id`, animal, inclusive bounds, source count and selection metadata.
- `window_events.csv`: ordered `window_key → source_event_key` links. Join to `source_points.csv` to reconstruct every original observation in each selected period.
- `groups.csv`: `group_key`, display `group_id`, rank/category, `grid_key` and selection metadata.
- `group_members.csv`: `group_key → window_key → individual_id` ownership.
- `grids.json`: keyed grid CRS, bounds, row/column dimensions, cell size, origin/directions, action offsets and boundary conventions. Each group's coordinates must be interpreted using its own grid.
- `collections.csv`: collection identity/season/rank and `group_ids_json`, plus coverage and duplicate metrics.
- `collection_weekly_density.csv`: one collection/season-year/individual/calendar-week row, including zero-count rows within each represented season-year’s buffered interval. Fields include exact `week_start`/`week_end_exclusive`, `retained_fix_count`, `core_fix_count`, `buffer_fix_count`, `season_support` (`core_only`, `buffer_only`, `mixed`, `none`), `selected_window_overlap_hours`, `partial_selected_week`, exact first/last retained timestamps, contributing group/window IDs and descriptive membership multiplicity. Summing counts per collection reconciles to its unique canonically owned selector observations. This report diagnostic is derived from selection data; it does not modify the immutable checkpoint or export eligibility.
- `collection_members.csv`: report membership fields plus `group_key`, `window_key` and `selector_subtrajectory_ids_json`. **Only `selection_status="selected"` enters the collection export.** The other rows explain suppressed overlapping evidence.
- `selector_points.csv`: `group_id`, `window_key`, `individual_id`, `selector_subtrajectory_id`, `source_event_key`; this supplies exact selector-segment provenance.
- `selector_subtrajectories.csv`: selector segment summaries, group/window/animal keys, counts, dates and cadence diagnostics.
- `window_seasons.csv`: `window_key`, season/season-year and core/buffer date bounds.
- `seasons.json`: exact season definitions and membership/provenance metadata.
- `cohort_audit.csv`, `qc_rejections.csv`, `collar_metadata.csv`, `mcp_summary.csv`: cohort/QC/schedule/sex/full-study spatial context.

Start with a collection row, resolve its selected membership rows, join group and window keys, and then reconstruct source observations through `window_events.csv`. The exporter performs and validates these joins. Display IDs such as `G001` and `WIN-C01` are meaningful only within their checkpoint; retain the checkpoint key and stable content keys with every script/result.

## 6. Export one collection

Choose a collection from the report and use the checkpoint path printed by the processor. Replace the placeholders explicitly:

```bash
python3 -m jaguar_irl.data.export_pantanal_seasonal_irl \
  --checkpoint analysis/pantanal_seasonal_selection/checkpoints/selection_<HASH> \
  --collection <COLLECTION_ID> \
  --variant both
```

The default destination is `data/tracking/<season>-<collection>-<UTC-run-timestamp>-<export-hash>/`. Each invocation gets a distinct timestamped directory; configuration/content identity is recorded separately. Override the root with `--output PATH`. Use `--variant fine`, `two_hour` or `both`. No collection, animal split or production model fit is chosen implicitly.

The exporter invokes the existing per-group export API with only that group's canonically owned windows, then assembles one portable collection bundle. It rejects selected source-event duplication and overlapping windows for the same animal. Nonoverlapping periods can coexist. Suppressed group/window contexts remain in backing data.

Output array paths are `fine/`, `two_hour/`, `paired/fine/` and `paired/two_hour/`. Filenames contain animal ID, parent-window hash, fragment hash, grid discriminator and trajectory discriminator. These keys prevent collisions across periods, representations and local maps; the manifest provides their full forms.

Exporter settings include `--source-gap-hours` (4), `--min-source-segment-points` (5), `--min-comparison-segment-points` (5), `--max-affected-fraction` (0.2) and `--min-final-retention` (0). The optional final two-hour F/M ratio gate is **disabled by default**. `--min-final-retention .8` requests the former 80% gate. M counts comparison observations after thinning and before fragmentation; F counts observations after fragment removal. Empty retained evidence remains ineligible. The exporter's setting does not relax or regenerate selector groups; the selector retains its protected 5% loss cap.

Fine export retains source cadence, splits gaps greater than four hours and tag changes, and catalogs fragments below the source minimum. Two-hour export reconstructs its comparison track from original source observations, with the standard regular band, hard cuts, pooled irregular-endpoint budget and fragment minimum. It does not thin an already-thinned checkpoint track. Paired representations share original endpoints and parent context. Independent fine export can include evidence outside paired intervals.

## 7. Bundle fields and plain-MaxEnt input preparation

Each NumPy array is integer `N × 3`, with columns **`[row, col, k]`**. `k=0,1,...` counts spatial moves; it is not elapsed hours or a third physical coordinate. Consecutive same-cell repetitions collapse, while revisits remain. Nonadjacent cell anchors are connected by deterministic eight-neighbor Bresenham paths; inserted connecting edges are explicitly flagged as inferred. Real source timestamps remain in provenance. The current grid contract has no barrier mask and allows diagonal corner crossing.

Read these bundle files before training:

- `data/trajectory_manifest.csv`: `trajectory_id`, original animal, group/grid/window, `segment_id` (export fragment), variant, independent/paired collection, pair ID, first/last events/times, counts, grid moves, inferred fraction, eligibility/rejection reason, array path, split, feature-map status and optimizer-candidate status. Added `season`, `seasonal_collection_id` and `selector_subtrajectory_ids_json` bind the seasonal context.
- `data/selector_export_crosswalk.csv`: exact source-event intersections between `selector_subtrajectory_id` and exporter `segment_id`/`trajectory_id`, with window/group/animal/variant and shared-event counts/keys. Selector segments and exporter fragments can differ because source/tag boundaries and representation-specific segmentation differ; do not equate their IDs.
- `data/point_links.csv`: trajectory/event order and grid assignment; join to `data/source_points.csv` for original observations.
- `data/grid_steps.csv`: cell-edge/action sequence, observed bracketing events/times and inferred-connection flags.
- `data/paired_cases.csv`: paired fine/two-hour trajectory IDs, common endpoints and pair eligibility.
- `data/fragment_diagnostics.csv`, `window_diagnostics.csv`, `fix_interval_summary.csv`, `cuts.csv`, `observation_edges.csv`, `comparison_edges.csv`, `comparison_points.csv`, `observation_membership.csv`: route support, actual cadence, F/M and A/M, losses, displacement/speed, segmentation boundaries and representation provenance.
- `data/collections.csv`, `collection_members.csv`, `collection_groups.csv`, `collection_windows.csv`: chosen collection and every canonical/suppressed context. `data/groups.csv` describes groups that actually exported canonical evidence.
- `data/animal_splits.csv`, `evidence_aliases.csv`, `grids.json`, `seasons.json`: split ownership, alias diagnostics and spatial/season contracts.
- `provenance/selection_checkpoint_manifest.json` and `upstream_export_manifests.json`: original identities and construction provenance. Their inventories describe their original artifacts; the bundle's own `export_manifest.json` inventories portable bundle files.

Lists under `lists/<independent|paired>/<fine|two_hour>/<split>.txt` contain bundle-relative array basenames. Choose **one representation collection per fit**. Do not concatenate independent and paired lists, and do not combine fine/two-hour demonstrations into one fit merely because they share a bundle. For a controlled fine-versus-two-hour comparison, use paired eligible cases and the same held-out reference and animal assignments; independent exports support separately declared broader-coverage experiments.

`--animal-splits PATH` accepts JSON mapping every selected original animal ID to `train`, `validation`, `test` or `unassigned`. Every window/group/variant inherits that assignment. Omission leaves animals unassigned. `--feature-map-manifest PATH` binds `grid_key` to feature-map entries with a feature-map key, array path and explicit `static_declared` or `bounded_period` applicability (`valid_from`, `valid_to`, half-open). Maps must match grid dimensions; their feature order/units/scaling must also match the training contract.

Zero-move fragments are cataloged as unsupported residence evidence. A one-move endpoint-conditioned route supplies no route-choice information and is excluded from optimizer candidates. Spatially over-budget or unsupported-geometry fragments remain diagnosed. Counts of selected individuals and source fragments therefore do not guarantee equal counts of informative training contributions.

**`training_ready` is a legacy placeholder hard-coded to false.** It does not
track input readiness for the new shared trainer and is not updated after a fit.
Use the shared trainer's `prepare` checks and frozen plan for that experiment's
input contract. Current joint training averages trajectory likelihoods within
animals and then across animals; the older animal/window/step-normalized proposal
has not been implemented. Preserve original-animal assignments across groups
and variants. The maintained [architecture and operating manual](../training/README_SHARED.md)
documents these distinctions and leaves scientific evaluation as a placeholder
pending review; the [earlier research note](../../research_notes/Jaguar%20trajectory%20coverage/biome_shared_reward_training.md)
remains background for proposed alternatives.

## 8. Verification and coexistence

Validate an exported bundle without the original movement CSV:

```python
from jaguar_irl.data.export_pantanal_irl import validate_export
validate_export("data/tracking/<RUN_DIRECTORY>")
```

Checkpoint loading verifies inventoried files and source/window/group ownership. Collection export additionally verifies inventoried season/collection/selector files, season dates, canonical evidence ownership and selector-event intersections. Array validation checks integer layout, bounds, consecutive move indices and adjacency. Fine observations remain available even when the two-hour representation fails an optional gate.

The locked entry points remain separately callable:

```bash
python3 -m jaguar_irl.data.movement_processor_pantanal --help
python3 -m jaguar_irl.data.export_pantanal_irl --help
```

Seasonal processing writes its own selection directory and immutable checkpoints. Export writes a timestamped tracking run. Existing locked HTML, backing files, figures and checkpoints are preserved. Neither command trains a reward model, assigns folds automatically or converts a sampling gap into proof of a separate biological trip.

## Sampling-duration sensitivity reports

The selection search already covers each entire buffered season. `--sampling-days` changes the duration screened for each animal. It can recover boundary-truncated fragments and alter the pooled endpoint/fragment-loss budgets, while also exposing additional irregularities. Eligibility need not vary monotonically with duration. Gaps above four hours still split trajectories. The full individual window must fit the seasonal envelope.

Generate independent duration reports, preserving the same seven-day seasonal buffer and spatial settings:

```bash
python3 -m jaguar_irl.data.movement_processor_pantanal_seasonal --sampling-days 10 --output analysis/pantanal_window_comparison/10d
python3 -m jaguar_irl.data.movement_processor_pantanal_seasonal --sampling-days 15 --output analysis/pantanal_window_comparison/15d
python3 -m jaguar_irl.data.movement_processor_pantanal_seasonal --sampling-days 20 --output analysis/pantanal_window_comparison/20d
python3 -m jaguar_irl.data.compare_pantanal_sampling_windows
```

The comparison entry point reads those three reports and the existing seven-day report. It generates `analysis/pantanal_window_comparison/index.html`, report links, two independently selectable report panes, `data/window_coverage_comparison.csv`, and `data/individual_window_eligibility.csv`. `--reports PATH ... --output PATH` accepts other already-generated reports. Source, seasons, seasonal buffer and spatial configurations must match. The main observed-span threshold scales as `sampling_days * 6.5/7`; schedule counts also scale. Relaxed windows retain explicit exceptions. This compares the existing selection procedure at different durations; it does not freeze the seven-day absolute count/span thresholds.

Observed unique group members (main plus relaxed):

| Duration | Winter | Spring | Summer | Autumn |
|---|---:|---:|---:|---:|
| 7 days | 9 | 15 | 16 | 12 |
| 10 days | 9 | 14 | 16 | 12 |
| 15 days | 9 | 14 | 16 | 12 |
| 20 days | 9 | 14 | 16 | 12 |

No new individual-season memberships were recovered in these runs. ID 19 is absent from spring for 10/15/20 days; its seven-day spring membership is retained in the baseline. These are pre-export counts. Collection/group IDs and local grids belong to their respective checkpoints; matching labels across reports do not establish matching evidence or maps. Training comparisons require consistent original-animal splits and an explicit evaluation design.
