# Seasonal Pantanal implementation checkpoint

Implementation completed 2026-11-01. This record describes the separate seasonal selection/report/checkpoint/export pipeline. The original processor, its checkpoint, backing files, HTML and figures remain governed by `pantanal_processor_freeze.json`; no original frozen file was changed.

## Scope and entry points

- `jaguar_irl/data/movement_processor_pantanal_seasonal.py`: scan the complete 56-animal cohort, select seasonal windows, build/rank spatial groups and seasonal collection alternatives, publish source-preserving checkpoints and render the report.
- `jaguar_irl/data/pantanal_seasons.py`: exact configurable season definitions and buffered containment.
- `jaguar_irl/data/pantanal_seasonal_collections.py`: bounded rank-seeded covers and canonical evidence ownership.
- `jaguar_irl/data/pantanal_seasonal_report.py`: offline HTML, external SVG figures and supporting chart data.
- `jaguar_irl/data/export_pantanal_seasonal_irl.py`: explicitly selected collection → fine, two-hour and paired grid-route arrays, manifests and provenance.
- [README_PANTANAL_SEASONAL.md](../../jaguar_irl/data/README_PANTANAL_SEASONAL.md): exhaustive configuration, field/join, selection and export walkthrough.

The implementation imports frozen parsing, temporal, spatial and export primitives. Those imported implementations and defaults remain unchanged. The new processor explicitly refuses the original `analysis/pantanal_selection` output directory or any child directory. Source/configuration/software identities are recorded; changing imported primitives requires respecting their original freeze boundary.

## Confirmed decisions

1. Select on the established observed two-hour thinning: inclusive 1.5–2.5-hour regular band, cuts above four hours, pooled irregular-endpoint fraction at most 20%, at least five observations per retained selector segment, and at most 5% short-fragment loss. Main windows also meet the configured schedule count and observed-span screens; relaxed windows can fail density/span or spatial budget checks with measured flags. Full-record duration/month support is descriptive.
2. Preserve every parsed original observation inside each returned window in the checkpoint. The exporter derives its fine and two-hour tracks from that source; it does not re-thin the selected report track. Its optional final two-hour F/M gate defaults off and does not change selector eligibility.
3. Operational core dates: winter May 15–Aug 14; spring Aug 15–Nov 14; summer Nov 15–Mar 21; autumn Mar 22–May 14. The user approved March 22 autumn onset for continuous seasons. The [climate source](https://www.climatestotravel.com/climate/brazil/pantanal), verified in the open browser on 2026-11-01, says late March/April and does not specify this exact transition date.
4. The entire inclusive configured-duration window must lie inside the half-open core season expanded by seven days at each end. Duration and buffer are independently configurable, defaulting to seven days. Groups can mix season-years; summer's season-year is its November start year. Every observed start competes before seasonal reduction; monthly winner filtering is not applied.
5. Use full-study MCP95 proximity and the established bounded-growth spatial rules. Fit map bounds around those MCPs and all selected-window source excursions, then pad and snap to 500-m cells in EPSG:32721. Original longitude/latitude is EPSG:4326.
6. Generate up to seven distinct collections per season (`--max-collections`). Cover the eligible candidate union, then prefer fewer repeated memberships/fewer groups and better ranks. A bounded greedy search makes compactness heuristic; no minimum-set-cover optimality is asserted. Singleton groups can rescue eligible isolated animals. Relaxed groups add animals absent from that season's main-group union.
7. Keep distinct nonoverlapping windows for an animal. Identical or overlapping windows have one owner selected by group rank; suppressed memberships remain in the roster. Alternatives are alternative cohorts, not datasets to concatenate. All observations, groups, representations and sensitivities of an original animal require one consistent fold assignment.
8. Navigation uses the compact individual-column/month-row tick chart, with three-letter month labels. Detailed timelines show dates and selected/suppressed ownership. The optional individual-by-week density view counts canonically selected, deduplicated retained two-hour observations; it is not an expected-schedule coverage percentage. Full-study group-envelope maps show spatial coverage. Source observation coverage can exceed selected export ownership; these are explicitly labeled.
9. No production collection, animal split or feature maps were chosen. No trainer was repaired or executed. Cell-runs remain deferred. The shared biome-and-season reward should use one jointly optimized reward vector across local group maps, with consistent feature scaling and documented animal/window weighting; see [shared-reward research](biome_shared_reward_training.md).

## Reproduction and contracts

From the repository root:

```bash
python3 -m jaguar_irl.data.movement_processor_pantanal_seasonal \
  --sampling-days 7 --season-buffer-days 7 --max-collections 7

python3 -m jaguar_irl.data.export_pantanal_seasonal_irl \
  --checkpoint analysis/pantanal_seasonal_selection/checkpoints/selection_<HASH> \
  --collection <COLLECTION_ID> --variant both
```

Report assets live in `analysis/pantanal_seasonal_selection/`: `index.html`, `images/*.svg`, `data/*.csv`, `seasons.json`, `selection_manifest.json`, `mcp95_full_study.geojson`, and immutable `checkpoints/selection_<hash>/`.

Checkpoint joins are collection → selected membership → group/map and window → ordered window events → source points. `selector_points.csv` links selector segment IDs to source event keys. Exported `selector_export_crosswalk.csv` links those keys to fine/two-hour fragment IDs and array paths. Suppressed aliases never create duplicate exported demonstrations. Separate local maps retain separate grid keys.

Array folders default to `data/tracking/<season>-<collection>-<UTC-run-timestamp>-<export-hash>/`. Each `.npy` is integer `[row, col, k]`, where k counts spatial moves. It is not an elapsed-time coordinate. Manifests preserve timestamps, source links and inferred grid-edge diagnostics separately. Compatible arrays do not imply that the legacy root trainer is ready for use.

The renderer can be rerun from its saved `selection_manifest.json` without scanning telemetry. A changed renderer has a new software hash on a subsequent full selection run. Existing checkpoints remain immutable.

## Current run and validation

- Published checkpoint: `selection_2174c0f80ad3933ac06358e9`.
- Source SHA-256: `feab575a3bcc7636960af87767590132995a49543d0805c11905ff33b72209e5`.
- Source cohort audited: 56 animals, seven studies, 75,396 parsed observations.
- Checkpoint: 54 candidate windows, 193 groups (154 main, 39 relaxed), 675 group memberships, and 7,831 deduplicated original source observations. Twenty distinct animals occur in generated groups across seasons; they are not 56 independent training contributors.
- Report: 21 collection alternatives, 470 external SVG assets and 5,041 backing weekly-density rows, including blank/zero-count bins. Current data contains duplicate-window suppression and no partial-overlap suppression; synthetic tests exercise both.

| Season | Alternatives | Unique animals per alternative | Groups in rank 1 | First collection |
|---|---:|---:|---:|---|
| Winter | 6 | 9 | 2 | WIN-C01 |
| Spring | 7 | 15 | 2 | SPR-C01 |
| Summer | 7 | 16 | 3 | SUM-C01 |
| Autumn | 1 | 12 | 3 | AUT-C01 |

All retained alternatives cover their season's generated eligible animal union. Counts are selection coverage before zero-move/unique-route or other export-specific exclusions. Autumn has one distinct cover and winter six under the bounded search; the maximum of seven does not manufacture duplicate alternatives.

Validation:

- 117 relevant selector, spatial, calendar, checkpoint/export, seasonal collection and report tests passed. The seven report tests also passed after the final explanatory-text update.
- End-to-end fixture reconstructs fine/two-hour arrays from the checkpoint after removing the original CSV and collar metadata.
- First-ranked collections in all four seasons exported successfully to temporary validation directories: winter 44 arrays, spring 110, summer 102, autumn 67, including independent/paired outputs. Every emitted array has selector provenance and no fragment is out of grid. Splits remain unassigned and training readiness is false.
- Final report links/IDs/assets, SVG syntax, source-to-density count sums, checkpoint integrity and exact seasonal software hashes verified. All 579 original frozen files still match their recorded hashes.
- An unrelated general-purpose processor test module requires pandas, unavailable in the current Python environment; it was excluded from the targeted suite. General-processor code was not modified.
- Browser security policy disallowed local-file HTML preview. SVG charts were rasterized locally with installed librsvg/cairo and visually inspected; HTML links, backing references and generated structure were checked directly. Interactive browser behavior was not exercised.

Implementation-only intermediate seasonal checkpoints were moved to `/tmp/pantanal-seasonal-intermediate-checkpoints/`; the production output retains the single final checkpoint above. Temporary export validations are not selected production training cohorts.

Remaining work requires explicit experiment choices: collection(s), animal and geographic split manifests, period-specific covariate maps and the separately scoped plain-MaxEnt trainer integration. Collection alternatives, independent/paired representations and seasonal experiments must not be concatenated silently.

## Presentation-only update — 2026-11-01

Omit zero repeated-ID/extra-membership summaries, empty period labels and no-flag placeholder text. Regenerated the seasonal report from its existing selection manifest; selection data and immutable checkpoints were preserved. Seven report tests passed. Renderer SHA-256 after this update: `8c6af39fa4af0c898978a9833c1e6840820d73d0c1991448b73b3229aba77cea`. Checkpoint software hashes describe the renderer at selection generation; this later report-only rendering has the hash recorded here.

Density-legend clarification: added a labeled numerical color bar and explicit lighter/fewer, darker/more explanation, including collection-specific scale limits. Report regenerated without changing selection data. Seven report tests passed. Renderer SHA-256: `6de6ba8d1d99a3f71de951631d7b2f5be29f467a170eb562d043f1b4ecbe8837`.

Month-label presentation update: any month with buffer observations now has its month name styled red/bold/italic; parenthetical buffer labels are omitted and years remain unstyled. Updated explanatory text and regenerated the report only. Seven report tests passed. Renderer SHA-256: `8224c3992844913808b7662f8e2367fe1d839d4e5bb037f6ca82ddd988d4346e`.

Floating navigation now includes direct bookmarks to every configured season, in configuration order. Regenerated the report and verified all season targets. Seven report tests passed. Renderer SHA-256: `95f7afa37d1115b7f5ee8253f467ea3e6636c6ba1481b790d0a8ccad2a3aa8b6`.

Season bylines now display inclusive last dates (exclusive boundary minus one day), without the end-exclusive parenthetical. Computational season boundaries remain half-open. Regenerated report; all four labels verified and seven report tests passed. Renderer SHA-256: `a0ddb02749a72c54fb86c867cf39d054264a55ae32395bc163b644937b2eff89`.

## Visual hierarchy and duration sensitivity — 2026-11-01

Restyled seasonal reports with serif headings, larger monospaced metric values, pastel season-specific header bands, heavier section boundaries, and season/collection/group/membership/spatial icons. Navigation selection behavior is retained. Regenerated baseline presentation and generated independent 10-, 15- and 20-day reports with the same seven-day season buffers and existing quality/spatial rules. Added `compare_pantanal_sampling_windows.py` for a coverage table, per-animal eligibility CSV and selectable side-by-side report panes. Seven report tests pass; all report anchors/assets, new checkpoint integrity/software hashes and the original 579-file freeze inventory were verified. No production splits or model fits were created.

Reports: `analysis/pantanal_window_comparison/index.html`, with `10d`, `15d` and `20d` subfolders. Coverage remains winter9/summer16/autumn12; spring falls from15 to14 (ID19 lost) for all longer windows. No new individual-season memberships are recovered. Longer windows can pool quality budgets differently, so this outcome is empirical rather than an eligibility monotonicity assumption. Main density/span counts scale with duration; relaxed group membership increases as some windows fail those main screens.

- 10 days: `selection_9e6dd5a423a5e934cde312f8`, 181 groups, 22 collections.
- 15 days: `selection_477a992213ccc94fe6daec48`, 171 groups, 24 collections.
- 20 days: `selection_1a2e25e30e6cf11962ceb4e3`, 169 groups, 24 collections.

Current renderer SHA-256: `e2d54d79ff7f431462d8539e2a0764f20b445355fa988b60f155de99e9e21fe6`. The seven-day report is a presentation-only rerender of its existing selection manifest; the longer-duration checkpoints record this renderer at generation.
