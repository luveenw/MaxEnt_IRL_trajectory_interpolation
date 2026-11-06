> Current CLI default: `--gap-jitter-minutes 15` applies a 4.25-hour native and
> selected gap cap. Pass `--gap-jitter-minutes 0` to reproduce the strict four-hour
> policy documented below. `BoutConfig()` itself retains the historical strict
> default; the seasonal entry point explicitly requests 15 minutes. Retention
> percentages and per-group tables are documented in README_PANTANAL_SEASONAL.md.

# All qualifying Pantanal seasonal bouts

This is the user-approved adaptation of the seasonal processor for four separate
seasonal reward models. It uses all 56 Pantanal animals as the input cohort and
retains every qualifying bout under one deterministic observed-fix sampler.
It does not reduce an animal to its best week. The earlier weekly pipelines and
their outputs remain available as controls.

## Run and inspect

From the repository root:

```bash
python3 -m jaguar_irl.data.movement_processor_pantanal_bouts
```

Open `analysis/pantanal_seasonal_bouts/index.html`. Its organization follows the
existing seasonal report: season → collection → computational map group → animal.
The default is one complete collection per season; `--max-collections` requests
alternative covers. Each cover must retain the same complete seasonal bout set.
An assertion rejects a cover that loses bouts or repeats source observations.

The output includes the existing groups, collections, collection-members,
individual-audit, windows, group-members, trajectory-manifest and selected-points
tables, MCP95 GeoJSON, an immutable self-contained checkpoint, and SVG figures.
`window_id` now identifies a **local bout**, rather than a seven-day window.
An individual can therefore have many windows in the same group and season.

## Actual selection cutoffs

Authoritative implementation: `BoutConfig` and `scan_bouts` in
`movement_processor_pantanal_bouts.py`. Each run also writes `cutoffs.json`.

| Metric | Main policy | Meaning |
| --- | --- | --- |
| Target elapsed time to next selected fix | 2 hours | Choose an actual observed fix nearest the next target in the regular band. |
| Regular elapsed-time band | 1.5–2.5 hours inclusive | Existing observed-fix sampler's timing tolerance; not “forgiveness 2.” |
| Maximum adjacent selected-fix interval | 4 hours inclusive | If no regular fix exists, take the earliest later observed fix; split if its interval exceeds 4 h. |
| Maximum adjacent native-fix interval | 4 hours inclusive | Split before thinning, so thinning cannot hide a native hard gap. |
| Minimum selected fixes per retained bout | 3 | Applied before grid projection; two displacement vectors, at most one turn for a three-fix bout. |
| Forgiveness factor | 2 | Four-hour maximum divided by two-hour target; not ±2 hours and not a 20% missingness rule. |
| Season buffer | 0 days | No bout or observation is shared across seasons. |
| Whole-week density/span requirements | Disabled | No seven-day envelope, 80% density or 6.5-day span gate. |
| Affected-endpoint percentage budget | Disabled | A locally continuous three- or four-hour schedule is admitted even if every interval is longer than the regular band. |
| Short-fragment loss percentage gate | Disabled | Rejecting a short bout does not invalidate another bout. |

The inherited `TemporalConfig` still contains week-related fields for compatibility;
the new scanner does not use them. Main thresholds are deliberately checked against
the agreed policy; changing them requires a new explicit policy identity, rather
than silently producing results labelled as this experiment.

Sampling restarts at individual, tag, native hard-gap and season-occurrence
boundaries. Selected intervals over four hours are then additional cuts. Every
qualifying resulting bout is kept. Native observations from its first selected fix
to immediately before the next selected bout, or the end of the native run, are
preserved. This includes unselected trailing observations. These disjoint source
envelopes reproduce the same selected fixes in the exporter. Points in rejected
short bouts remain traceable in `data/rejected_bouts.csv`; the raw input is unchanged.

This is complete coverage under the specified sampler, not an optimization over
every possible sampling phase. Three-hour native increments retain their actual
three-hour durations; no two-hour acquisitions are invented. Coordinate/timestamp
validation and duplicate checks are inherited from the existing reader. This is
not an additional device-accuracy or speed-outlier filter.

## Fixed seasons across years and sites

Source: <https://www.climatestotravel.com/climate/brazil/pantanal>.
The user explicitly confirmed these operational dates on 2026-11-02:

| Season | Inclusive dates | Description supplied by user |
| --- | --- | --- |
| Winter | May 15–August 14 | Dry with rare showers. |
| Spring | August 15–November 14 | Hottest season. |
| Summer | November 15–March 21 | Hot, humid, with intense downpours or thunderstorms. |
| Autumn | March 22–May 14 | Temperature and rain decrease; rivers return to their banks. |

Code uses midnight at the following date as the exclusive endpoint. Summer's
season-year is its November start year. All years are pooled into each season's
collection. Source timestamps have unspecified timezone; no timezone conversion
or local-hour interpretation is assumed. The source describes broad climatic
periods; the exact March 22 boundary is the user's operational choice.

## Reading the comparison tables

`data/season_summary.csv` contains unique seasonal totals.
`data/sensitivity.csv` has one row per animal × season, including animals with
no data or no eligible bout in a season. Its columns mean:

- `main_selected_fixes`: fixes selected by the main two-hour-target policy.
- `main_source_fixes`: all original fixes preserved within those accepted bouts,
  including the selected fixes. Do not add this to the selected-fix count.
- `five_point_*`: the subset of the same main bouts containing at least five
  selected fixes. This tests the observation floor alone.
- `native_three_point_*`: runs containing at least three original fixes with
  native intervals ≤4 h, before two-hour thinning. These are an alternative
  evidence set, not additional selected trajectories.
- `native_eligible_fixes_outside_main`: original fixes eligible under that native
  alternative but outside the main pipeline's preserved source envelopes.
- `eight_hour_*`: rerun two-hour selection with an eight-hour cap and three-fix
  minimum, for sensitivity only. `gained` and `lost` compare selected event IDs;
  a changed hard-gap boundary can change sampling phase. Fewer bouts can mean
  that previously separate bouts joined, not that evidence was lost.
- `main_defined_turns`: adjacent nonzero observed displacement pairs. This is
  geometric support, not an effective sample size or proof of iSSA adequacy.

`data/windows.csv` lists unique retained bouts. In contrast, group-members and
selected-points tables may repeat those bouts in alternative map contexts.
For one collection, use only `selection_status=selected` in collection-members.
Exact aliases are marked `duplicate_window`; no overlapping windows are admitted.

## Export for the existing IRL data contract

Use the new adapter so the old exporter defaults do not reapply a five-fix minimum
and 20% affected-point budget:

```bash
python3 -m jaguar_irl.data.export_pantanal_bouts_irl \
  --checkpoint analysis/pantanal_seasonal_bouts/checkpoints/SELECTION_KEY \
  --collection WIN-C01 \
  --output analysis/pantanal_seasonal_bouts/exports
```

Replace `SELECTION_KEY` with the folder printed by the processor. Other collection
IDs are `SPR-C01`, `SUM-C01` and `AUT-C01`. The completed run's four export paths are
listed in `analysis/pantanal_seasonal_bouts/exports.json`.

Exports retain fine and two-hour variants, paired cases, source-event links,
actual durations, grid-step construction metadata, and integer `[row, col, k]`
arrays. Here `k` indexes spatial moves, **not hours**. Straight grid connections
between nonadjacent observed cells are inferred connections, not recovered paths.

Read each export's `data/trajectory_manifest.csv`, selecting
`collection=independent` and `variant=two_hour` for the main bout counts:

- `data_eligible=True` means the temporal selection is retained.
- `optimizer_candidate=True` additionally passes the current route/grid checks.
  These checks exclude zero-move and one-move routes and over-budget map contexts;
  they do not establish habitat support or prove informative reward gradients.
- `unsupported_residence_evidence` means fixes collapsed to one grid cell; it is
  **not** a claim that the animal was nonresident, or that it never moved.
- `training_ready=False` is a legacy exporter placeholder, not a live check.
  The shared trainer validates its own maps, split and routes through `prepare`;
  this column is not updated after binding or training. See the maintained
  [operating manual](../training/README_SHARED.md) for readiness and eligibility.

Full-study MCP95 grouping, 500 m cells, 5 km map padding, 40 km maximum side and
1,600 km² maximum area retain the previous spatial settings. Evidence requiring
an exception remains in the checkpoint and is flagged, rather than silently
dropped from temporal coverage. Group envelopes are map-planning proxies, not
tests of seasonal residency or habitat fidelity.

## Relation to Hofmann and ecological interpretation

This adaptation follows Hofmann's motivation to retain short locally usable
bursts and preserve irregular durations. The three-fix floor, four-hour cap and
calendar boundaries are project choices, not ecologically calibrated thresholds
from the paper. Hofmann's five-step duration-class support rule is not a universal
five-fix fragment requirement. See
`research_notes/Jaguar trajectory coverage/hofmann_missingness_primary_evidence.md`.

The pipeline does **not** implement duration-aware iSSA, certify random natural
missingness, or demonstrate a constant movement kernel. Fine observations and
paired exports make subsequent spatial checks possible. Habitat fidelity has
not been measured because seasonal feature maps have not been bound. Seasonal
averaging also does not eliminate within-season or between-year flooding changes.
Those limits belong to interpretation and subsequent validation; they do not
silently remove otherwise qualifying observations from this retention experiment.

Verification: `python3 -m pytest -q jaguar_irl/data/test_pantanal_bouts.py`.
