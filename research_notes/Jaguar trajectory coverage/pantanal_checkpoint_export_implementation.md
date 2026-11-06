# Pantanal checkpoint/export implementation and freeze


## Current policy clarification — 2026-11-01

The next separate processor must **use the approximately two-hour [1.5,2.5]-hour thinned representation to select windows/groups**, while preserving all original parsed source observations within each selected window in immutable checkpoints. Export both fine and two-hour representations for matched model training/testing. This supersedes the source-only group-admission/ranking redesign proposed below; source coverage remains a useful diagnostic, but must not silently replace the thinned selection basis. Reuse the locked selection strategy as the baseline, including its protected cadence/fragment screens and main-versus-relaxed window criteria, unless a later change is explicitly agreed. This clarification specifies future work; no new processor or cohort regeneration is implemented here.

The separate exporter now defaults `min_final_retention_fraction` / `--min-final-retention` to **0**, disabling only the final F/M ratio gate for the two-hour representation. Require M>0 and F>0, retain the gap/affected-endpoint/fragment-length rules, and always report F/M. An explicit `.8` restores the former ratio requirement. Fine export has no F/M gate. The locked selector's 5% fragment-loss cap and weekly density/span rules remain unchanged. Existing immutable export/checkpoint artifacts retain their recorded policies; new export identity hashes capture the changed configuration and software.

Updated 2026-10-31. This records the completed checkpoint/export phase and the subsequent explicitly authorized selector/report revisions: remove the full-record tracking-span criterion and supported-year-month warning, add sex counts to group sections/rankings, and use sex-specific trajectory markers. The broader source-based selection redesign, additional diagnostic plots and model experiments remain unimplemented. See [the scientific specification](pantanal_sampling_time_and_grid.md).

## Governing decisions and freeze boundary

- Remove both the full-record 90-day criterion and the three-supported-year-month warning completely: neither is a gate, warning, ranking penalty or relaxed-membership trigger. Keep full-study dates, `tracking_span_days`, observed year-month counts and counts of year-months with at least seven observed dates as descriptive metadata. Compatibility `support_warning`/codes/text fields remain false/empty. Other temporal/spatial settings remain unchanged, including the selector's 5% fragment-loss rule and expected-schedule coverage gate. Export-only retention policy remains separate.
- The actual entry point is `jaguar_irl/data/movement_processor_pantanal.py`. Its report and checkpoint paths now join collar `Sex` metadata by original animal ID. Group tables/checkpoint metadata contain `n_males`, `n_females`, `n_unknown_sex`; member/audit rows contain sex/status. Missing or conflicting metadata is unknown, never inferred. Counts do not affect scoring.
- Implement the separate exporter, without choosing production experiment groups or animal splits. No production export profile or train/test assignment has been created. All-group exports under `/tmp` were validation artifacts only.
- Defer cell-runs entirely. There is no cell-runs CLI or file, stay action, residence model, HMM, or uncertainty-aware IRL implementation in this phase.
- Confirmed export settings: `min_source_segment_points=5`, `min_comparison_segment_points=5`, `behavior_selection=all_retained`, source gaps **greater than** four hours split. Exactly four hours is permitted. Count source/comparison observations before grid compression or inferred cells.
- The user explicitly authorized this revision of the frozen selector and regeneration of its products. After completing it, refresh the freeze inventory for the current selector/checkpoint/report state. Further changes still require an explicit switch back; checkpoint-only work should use `--checkpoint-only` to avoid report writes.
- The exporter is a separate downstream component with its own versioned configuration/artifacts. Future exporter or trainer changes must not mutate the frozen selector or its products. Preserve unrelated repository and index changes; this revision does not stage or commit anything.

## Implementation files

| File | Responsibility |
|---|---|
| `jaguar_irl/data/movement_processor_pantanal.py` | Existing selection; new `write_selection_checkpoint` wrapper and checkpoint-only invocation. |
| `jaguar_irl/data/pantanal_checkpoint.py` | Streaming source/metadata capture; content-addressed checkpoint publication; integrity and reference validation. |
| `jaguar_irl/data/pantanal_irl_temporal.py` | Export-only source fragmentation, observed two-hour comparison track and exact period-wide partition optimizer. No edits to the frozen temporal helpers. |
| `jaguar_irl/data/export_pantanal_irl.py` | Standalone projection, compression, deterministic rasterization, arrays, manifests, provenance, paired cases and diagnostics. |
| `jaguar_irl/data/test_pantanal_checkpoint_export.py` | New scientific-contract, provenance, standalone-operation and immutability tests. |

## Production checkpoint

Directory:

```text
analysis/pantanal_selection/checkpoints/selection_8cc3315f50f9395c0e399726/
```

It contains **117 returned candidate windows**, **253 generated groups** (222 main, 31 relaxed), **815 group memberships**, **16,211 distinct unthinned QC events**, and support/metadata/MCP summaries for **all 56 cohort animals**. Unthinned events belong to the 20 individuals with returned candidate windows. The remaining animals have audits here, not a new exportable source selection.

The prior `selection_c5ab7b5fc6198a62f6e3844a` and `selection_0ee1ed48e956b6367001b356` checkpoints remain immutable historical snapshots; the directory above is current. Policy is `pantanal_selection_descriptive_full_record_support_v3`; new software/configuration hashes distinguish it from earlier selections. The exporter inherits this policy label from its input checkpoint, so no additional exporter changes are needed for month-warning removal.

The checkpoint covers the union of returned candidate windows, including candidates not used by any group. It does **not** contain every scanned rolling window or all full-study telemetry. Changing group selection or introducing currently absent animals still requires the source CSV and a separately authorized selection implementation. Ten returned candidate windows are not used by any generated group; an all-group export consequently covers 107 windows and 15,046 distinct source events. These counts are outputs of this selection, not hard-coded expectations.

| Checkpoint file | Contract |
|---|---|
| `checkpoint.json` | Schema `pantanal_selection_checkpoint/1`; immutable selection key; source/collar/software hashes; selection configuration; cohort, policies, counts and per-file SHA-256 hashes. |
| `source_points.csv` | One row per source event, keyed by `source_event_key`; original event/animal IDs, source row, original and parsed timestamps, timezone status, coordinates, study, tag, QC status and original record JSON. |
| `windows.csv` | Stable `window_key`, legacy window ID, animal, exact inclusive bounds, source count/bounds, and selection metadata for this version. |
| `window_events.csv` | Ordered window-to-source references; no source-row duplication across overlapping groups. Schema 1 has no context-only outside-window events. |
| `groups.csv`, `group_members.csv` | Every generated group regardless of report limit; immutable group/window/grid keys, display IDs, ranks, membership and selection metadata for this version. |
| `grids.json` | CRS, bounds, upper-left origin convention, row/column orientation, resolution, dimensions, boundary rule and eight-moving-action convention. Maps/barriers are not fabricated. |
| `cohort_audit.csv`, `qc_rejections.csv` | All cohort audit records and invalid-source-row references/reasons. The selector's duplicate-timestamp failure behavior remains unchanged. |
| `collar_metadata.csv`, `mcp_summary.csv` | Planned schedules/status, relevant collar attributes, full-study support/MCP provenance and polygon coordinates. Empty metadata rows are ignored; conflicting or missing schedules remain unavailable. Contact details are not copied. |

Publication uses a temporary sibling directory followed by rename. An identical rerun verifies/reuses the existing checkpoint. Different inputs, selection configuration or relevant code produce a different key; corrupt or conflicting artifacts fail rather than being overwritten. Report limits and top-seven presentation settings do not determine selection identity. Tables have explicit headers and CSV input is read in a stream.

Generate/reverify the checkpoint without rewriting the report:

```bash
python3 -m jaguar_irl.data.movement_processor_pantanal --checkpoint-only
```

Optional `--checkpoint-root` changes the checkpoint parent; `--collar-metadata` supplies alternative collar metadata. A normal pipeline invocation also writes a checkpoint and regenerates the report. It was used for this authorized revision; future checkpoint-only invocations should avoid report mutation.

## Export invocation and artifacts

No group selection is implicit. The CLI requires `--groups` (immutable keys or checkpoint-local G/R display IDs) or explicit `--all`. `--windows` can restrict windows inside those groups. Default output parent is `analysis/pantanal_irl_exports`, separate from the frozen report; output is an immutable `export_<hash>/` directory. There is no production export in that parent yet.

Example **for a future explicitly selected experiment**, not an assignment made in this phase:

```bash
python3 -m jaguar_irl.data.export_pantanal_irl \
  --checkpoint analysis/pantanal_selection/checkpoints/selection_8cc3315f50f9395c0e399726 \
  --groups G01 \
  --variant both \
  --output analysis/pantanal_irl_exports
```

`--variant` accepts `fine`, `two_hour`, or `both`. Gap/count/retention settings are explicit CLI parameters; the full policy is `ExportConfig` in `pantanal_irl_temporal.py`. Changing export-only parameters creates a separately identified export tied to the original selection; it does not imply re-ranked groups. The exporter reads no original movement or collar CSV.

- `arrays/<group>/<independent|paired>/<fine|two_hour>/*.npy`: integer N-by-3 `[row,col,k]` arrays. k starts at zero, advances by one per spatial move, and is not hours. Every edge is adjacent and nonstationary. These arrays satisfy the legacy trajectory format; the original trainer still needs separate repairs.
- `data/trajectory_manifest.csv`: animal/window/bout/fragment/pair/group/grid identity, source references, map binding, duration, counts, eligibility, backend/route-choice status, array path and split. `training_ready` is always false in this phase; `inputs_bound` records whether maps/splits are supplied, not validation of the trainer.
- `data/fragment_diagnostics.csv`: the same catalog with fragment geometry/provenance diagnostics, including rejected fragments. L=0 is `unsupported_residence_evidence`; one adjacent move is `no_route_choice` and excluded from optimizer candidates. A five-observation floor does not establish informative route choice.
- `data/source_points.csv`, `point_links.csv`, `observation_membership.csv`, `comparison_points.csv`: deduplicated source evidence and chronological representation/fragment references. Join by event key for original timestamps/coordinates. Comparison-point files are keyed references, not fabricated positions.
- `data/grid_steps.csv`: each edge's cell/action indices and bracketing source observations/timestamps; every edge used to connect nonadjacent anchors is marked inferred. `(0,0)->(0,3)` contributes three inferred edges, not two.
- `data/observation_edges.csv`, `comparison_edges.csv`: displacement and actual elapsed-time speed before grid compression; turning angles when both vectors are nonzero. Primary comparison metric flags require regular comparison intervals, with both adjacent intervals qualifying for an angle.
- `data/window_diagnostics.csv`, `fix_interval_summary.csv`, `cuts.csv`: M/F/A, retention/affected fractions, counts, boundaries, source gaps, scheduled-interval diagnostics and union-of-fragment-span coverage. Coverage is explicitly bounded-gap support, not continuous observation. Full-window source-gap maximum includes tag boundaries and has a separate within-tag maximum.
- `data/paired_cases.csv`: matched source/comparison intervals with identical original endpoint events, animal, window, grid and map binding. Independent fine exports remain available outside this intersection. Paired optimizer candidates require both arms to qualify.
- `data/groups.csv`, `animal_splits.csv`, `evidence_aliases.csv`, `grids.json`: selection context, explicit unassigned/default animal ownership and duplicate evidence across alternative groups.
- `lists/<group>/<independent|paired>/<variant>/<split>.txt`: relative array basenames, isolated by fit context. These are for future adapted trainer use, not safe input to the current hard-coded trainer. Never concatenate alternative-group or independent/paired lists into one fit without evidence deduplication.
- `export_manifest.json`: schema `pantanal_plain_maxent_export/1`, checkpoint/config/software/split hashes, counts, file hashes, reconstruction assumptions and deferred features.

No `cell_runs.csv`, HTML, chart, reward weights or prediction outputs are generated.

## Export scientific policy

Source fragments use all unthinned observations, cutting gaps >4 h and changes in known tag identifier. A tag change is a construction boundary, not proof of a biological trip; same-tag deployment boundaries are unavailable in the source file. Short fragments remain in the source/catalog and do not remove other fragments or animals.

The comparison sampler chooses actual observations closest to +2 h within inclusive [1.5,2.5] h (earlier timestamp/event tie-break); otherwise it takes the earliest later observation at least 1.5 h away. It restarts at hard source/tag boundaries. M is the count before comparison fragmentation. Hard gaps >4 h split; optional cuts are confined to (2.5,4] h edges. Across retained comparison fragments, unique irregular-edge endpoints A satisfy A/M <=0.20. The exact partition maximizes F, then minimizes kept blocks, total cuts, and chronological cut positions. Keep fragments with at least five observations and require nonempty retained evidence. Record F/M diagnostically; `--min-final-retention` is configurable in [0,1], defaults to `0` (ratio gate disabled), and `.8` restores the former F/M >=0.80 policy. **There is no separate 5% loss cap, implicit 95% minimum, or expected-schedule coverage gate in this export policy.** A synthetic 9/10 retained case verifies acceptance. Fine evidence survives comparison failure.

Gridding uses the checkpoint's EPSG:32721 500-m transform. Exact external boundaries enter the last cell; genuine out-of-bounds points are never clipped. An out-of-bounds fragment is cataloged as unsupported and not exported as an array; changing its map requires a separately versioned map/selection decision. Consecutive repeats collapse but leave-and-return excursions remain. Bresenham ties are fixed (`e2 >= dy`, `e2 <= dx`) and versioned. No barrier mask is supplied in this phase; diagonal corner crossing is allowed. Inferred edges are assumptions, not additional observed decisions, and receive no invented per-step timestamps.

An optional `--animal-splits` JSON maps original IDs to `train`, `validation`, `test`, or `unassigned` and must cover every selected animal. Every group/variant inherits that assignment. Without it all animals are unassigned. Optional `--feature-map-manifest` JSON is keyed by grid key, with one or a list of entries containing `feature_map_key`, NPY `path`, and either `temporal_scope=static_declared` or `temporal_scope=bounded_period` plus `valid_from`/`valid_to`. Period bounds are [from,to), in the source's unspecified clock convention. A fragment must fit entirely in one declared period; no match remains unbound, multiple matches fail. Array dimensions and hashes are checked. Feature definitions/units/scaling and ecological applicability still require verification at trainer integration.

## Verification and known limits

- **90 relevant tests passed** for this revision, covering temporal selection, spatial/calendar logic, ranking/reporting, checkpoint/export integrity and sex/flag regressions. Changing the descriptive month-count definition does not change selected windows. The general processor was not modified. Every generated section/table was checked against metadata counts; the new checkpoint passed integrity validation and a standalone G01 export was verified under `/tmp` without assigning production splits.
- Partition optimization was checked against exhaustive enumeration of regular/optional/hard boundary patterns, including chronological tie-breaks.
- Tested five-versus-four observation boundaries, exactly-four-hour versus larger gaps, native fine-fix retention, F/M=90% acceptance, comparison failure without deleting fine evidence, tag boundaries, repeated-cell compression/revisits, inferred edge counts, bounds, paired endpoints, split ownership, temporal map applicability, hash tampering and restart behavior.
- A standalone synthetic export succeeded after deleting its original source CSV. Checkpoint/report-limit independence and metadata blank/conflicting/missing values were tested.
- A temporary all-group validation export produced 6,125 catalog fragments, 5,813 arrays, and 1,532 pairs across 107 group-member windows. Counts include independent and paired collections and must not be summed as independent evidence. All splits were unassigned and zero fragments were declared training-ready. This was validation, not production experiment selection.
- For both authorized revisions, all windows were rescanned, groups regenerated and scores/ranks recomputed. Membership, selected periods, scores and ranks match the original 253-group result; the removed full-record criteria were advisory. The first revision removed 17 animal span warnings and cleared 40 group flags. The subsequent month-warning removal cleared the remaining 13 animal support warnings and 53 additional group flags. All 222 main groups are unflagged; the 31 relaxed groups retain their measured window/spatial exceptions. Calendar styling reflects these current flags; table ranks are unchanged.
- Every group section and both rankings tables show total/M/F counts. All 56 animals have known metadata sex (25 males, 31 females); each group's counts reconcile to unique members. Maps use triangles for males, circles for females, crosses for unknown sex, and matching individual legend handles/labels. The first-seven overview uses the same symbols.
- Regenerated the current CSVs, selection manifest, HTML, GeoJSON, map/count PNGs and immutable checkpoint; refreshed the freeze inventory after validation. No production export profile, animal split or model fit was introduced.

Not implemented: the broader source-based selection/ranking redesign and planned fragment/cadence diagnostic figures, source fragments for currently unrepresented animals, cell runs, general feasible-route enumeration, barrier-aware rerouting, trainer/gradient repairs, biome-level optimization, statistical split choice, predictive validation or future residence/U models. These must not be marked complete merely because the exporter emits compatible arrays.

For the future biome model, see [shared reward training recommendations](biome_shared_reward_training.md). Spatial groups are computational domains; retain one shared reward objective across unique animal/window evidence, rather than weighting overlapping generated groups as independent populations.

## Freeze verification

[The freeze inventory](pantanal_processor_freeze.json) enumerates every protected file with its SHA-256 and byte size. This is a recorded content freeze, not an operating-system permission change or Git commit. Verify it from the repository root:

```bash
python3 - <<'PY'
import json
from pathlib import Path
from jaguar_irl.data.pantanal_checkpoint import verify_inventory
lock = Path('research_notes/Jaguar trajectory coverage/pantanal_processor_freeze.json')
verify_inventory(Path.cwd(), json.loads(lock.read_text()))
print('Frozen Pantanal files verified')
PY
```

Use each version's source/config/code hashes in `checkpoint.json` and the separate export hashes in `export_manifest.json` to distinguish selector versions from export sensitivities. Updating the exporter alone does not authorize replacing an immutable selection checkpoint or changing the current report. The freeze inventory records the current selection key and preserves the prior checkpoint as a superseded snapshot.

## Export-only retention update — 2026-11-01

The final-retention setting already existed. Its CLI and Python defaults changed from 0.8 to 0.0: the two-hour F/M gate is now optional and disabled unless explicitly requested. The positive M/F checks, affected-endpoint budget, hard gaps, minimum fragment lengths and fine treatment are unchanged. Configuration/software hashes create new export identities; no existing export, selection checkpoint, report or backing asset was overwritten. `--min-final-retention .8` requests the former ratio policy.

The shared-biome research note and consolidated specification record the user's renewed instruction to use approximately two-hour thinning for future group selection while preserving source observations for both model treatments. The source-only selection/ranking redesign is superseded. No new processor has been implemented in this update.

Validation for this export-only update: 91 relevant tests passed, including default-off versus explicit-80% retention, empty/short evidence rejection and threshold bounds. G01 checkpoint exports with thresholds 0 and .8 both passed integrity validation under `/tmp/pantanal-optional-retention-validation`; their identities differ. Production outputs were not regenerated.
