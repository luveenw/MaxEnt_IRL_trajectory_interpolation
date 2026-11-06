# Pantanal trajectory selection

This pipeline selects comparable weeks of observed movement for nearby Pantanal jaguars and exports several ranked alternatives. It prepares data for future model work; it does not train an IRL model or establish biological home ranges. The implementation is confined to `jaguar_irl/data`. The legacy model code elsewhere in `jaguar_irl`, `maxent_irl_multimap`, and `maxent_irl_single_extent` is not a dependency.

The entry point is `movement_processor_pantanal.py`. The separate original `movement_processor.py` processes full records with the legacy individual eligibility filters (100 fixes, 60 days, at most 50% empty calendar days) and rejects excessive short-fragment loss per recording bout. It shares observed-fix sampling primitives, but does not select weeks, calendar months, or clusters. Its recording-bout segmentation is separate from the Pantanal period-wide affected-point budget described below. See [README_MOVEMENT_PROCESSOR.md](README_MOVEMENT_PROCESSOR.md) for its distinct workflow and export format. The weekly loss rules described in this document apply to the Pantanal selector; full-record span and month counts are descriptive only.

## Run and configure

From the repository root, using Python with `numpy`, `pyproj`, and `matplotlib` installed:

```bash
python3 -m jaguar_irl.data.movement_processor_pantanal --help
python3 -m jaguar_irl.data.movement_processor_pantanal --top-n 7
```

The default input is `data/jaguar_movement_data.csv`; outputs go to `analysis/pantanal_selection`. CSV exports are in its `data/` subfolder and PNG figures are in `images/`. A rerun writes the output files in the chosen directory. Give sensitivity runs separate directories:

```bash
# Make only the proximity criterion more permissive, retaining the map budget.
python3 -m jaguar_irl.data.movement_processor_pantanal \
  --growth-buffer-km 10 \
  --map-padding-km 5 \
  --max-extent-side-km 40 \
  --max-extent-area-km2 1600 \
  --cell-size-m 500 \
  --output analysis/pantanal_selection_buffer10

# Stricter minimum segment length, retaining the default loss limit.
python3 -m jaguar_irl.data.movement_processor_pantanal \
  --min-subtrajectory-points 10 \
  --max-short-fragment-loss 0.05 \
  --max-affected-point-fraction 0.20 \
  --min-days-per-month 7 \
  --top-n 5 \
  --output analysis/pantanal_selection_stricter
```

`--csv` selects a different input file. `--top-n` accepts 3–7 and controls the first-ranked main candidates exported in the compact selection files; it does not change candidate generation or ranking. All configuration values are saved in `selection_manifest.json`.

The CLI exposes the main operational thresholds. Other controls are explicit dataclass fields in `TemporalConfig`, `SpatialConfig`, and `ProcessorConfig`; they can be changed in Python. For example, to tighten the accepted interval range while keeping the rest of the defaults:

```python
from jaguar_irl.data.movement_processor_pantanal import MovementProcessor, ProcessorConfig
from jaguar_irl.data.pantanal_temporal import TemporalConfig

config = ProcessorConfig(
    output_dir="analysis/pantanal_selection_tighter_intervals",
    temporal=TemporalConfig(regular_min_hours=1.75, regular_max_hours=2.25),
)
MovementProcessor(config).run_pipeline()
```

## Cohort and provenance

The default cohort contains exactly these **56 individuals**, with no duplicate 116 and with 110 included:

```text
12,13,14,15,18,19,22,23,25,27,28,29,30,31,32,33,41,51,52,53,54,55,56,
57,59,60,61,68,69,74,75,79,81,84,86,87,88,91,92,101,102,103,104,105,
106,107,108,109,110,111,112,113,114,115,116,117
```

The seven study names are `Jaguar_Taiama`, `jaguar_Oncafari Project`, `Panthera_Pantanal-Jaguar-Project`, `Pantanal`, `Paraguayan Pantanal`, `Rio Negro`, and `Sao Bento`. Explicit IDs and these study labels determine membership; older biome lookup tables are not used. The supplied CSV contains 75,396 fixes for this cohort. The parser checks that the full requested ID set agrees with the study-based cohort.

Original animal IDs, event IDs, coordinates, and timestamps remain available in the exports. Invalid dates or coordinates are counted in the parse audit. Duplicate timestamps for an individual stop the main pipeline for explicit resolution. The temporal helper can collapse duplicate timestamps if called separately, but the main parser does not silently resolve conflicting observations. The manifest records the input SHA-256 and generation time. Source timestamps have no specified time zone and are preserved without conversion.

## Temporal selection and segmentation

### Standalone per-individual reproduction specification

The following specification describes the implemented Pantanal temporal selector at its defaults. Apply it independently to each individual; candidate periods and their budgets are never pooled between individuals. Spatial grouping follows this stage and is specified separately below. Non-default runs must substitute every threshold recorded in `selection_manifest.json`.

- **Input:** use the requested Pantanal cohort's valid observed fixes, sorted by individual and timestamp. Parse timestamps as `%m/%d/%y %H:%M`, preserving the source clock convention. Skip invalid dates/coordinates with an audit count; duplicate timestamps within an individual abort the main pipeline. Preserve original IDs, event IDs, and coordinates. Do not apply the general processor's 100-fix, 60-day, or empty-day filters.
- **Enumerate periods:** start a candidate at **every observed timestamp** `T`; its parent interval is `[T, T + 7 days]`, inclusive. Allow month/year crossings. Evaluate record-tail starts even when the nominal endpoint exceeds the last fix; do not shorten the nominal interval. This enumerates observation-anchored windows, not arbitrary continuous start times or every possible resampling sequence.
- **Resample observed fixes greedily:** retain the first fix. From the last retained timestamp `t`, prefer an observed fix in `[t + 1.5 h, t + 2.5 h]` closest to `t + 2 h`; break equal-distance ties toward the earlier timestamp. If that range is empty, take the earliest subsequent fix at least 1.5 hours later, including one after a gap exceeding four hours. Ignore closer fixes and stop when no eligible later fix remains inside the parent interval. The target phase follows the selected observations. Never interpolate or invent locations.
- **Freeze the denominator:** let `M` be the number of resampled fixes **before** any segmentation or fragment removal. Both percentage budgets below use this same fixed `M`; neither uses raw CSV row count, a segment's length, or the final retained count.
- **Classify consecutive resampled intervals:** `[1.5, 2.5] h` is regular; `(2.5, 4] h` is tolerated irregular; `>4 h` forces a segment boundary. Additional cuts are allowed only at tolerated irregular intervals. Preserve observations on both sides of a cut; the removed transition is not an observed movement step.
- **Count affected points:** let `A` count unique retained observations incident to at least one **retained** tolerated-irregular interval. Both endpoints count, and a shared endpoint counts once. Cutting an interval removes its contribution, but an endpoint remains affected if its other retained adjacent interval is irregular. Gaps over four hours are boundaries, not tolerated steps.
- **Enforce the pooled 20% budget:** require `A <= floor(0.20 × M + 1e-12)` across **all** retained subtrajectories in that individual's candidate period. A segment may exceed 20% locally. Do not impose or reset a separate budget for each segment, hard-gap run, or recording bout.
- **Choose a partition globally:** among partitions satisfying the hard boundaries and pooled budget, maximize final retained point count `F`, then minimize retained segment count, then minimize total retained-plus-dropped block count. Keep every block of at least five points; only blocks shorter than five may be dropped. Never duplicate fixes or join movement across discarded pieces.
- **Resolve tied partitions deterministically:** the planner uses ascending boundary endpoints, descending candidate starting boundaries, insertion order for prior budget states, and replaces a state only for a strictly better `(F, -retained_segments, -all_blocks)` score. Remove states dominated by an equal-or-better score at a lower budget; choose the lowest used budget among equal final scores. Two exact shortcuts apply: use only forced hard-gap boundaries when already feasible; for one run containing exclusively tolerated-irregular intervals, retain the first `min(M, budget)` points if that count is at least five and split the remainder into dropped blocks of at most four. These rules specify `_period_partition_plan`'s tied-cut behavior as well as its optimization objective.
- **Enforce protected fragment retention:** let `D = M - F` be the number of points in dropped short fragments. Reject the candidate if `F = 0` or `D / M > 0.05 + 1e-12`. A valid segment elsewhere in the same candidate cannot reset this loss denominator. The relaxed list also enforces this check.
- **Apply main-list schedule coverage and span:** compute the two-hour reference `E = round(7 × 24 / 2) + 1 = 85` and require `F >= ceil(0.80 × E) = 68` **after** fragment removal. Also require at least 6.5 days between the first and last retained observation. The 80% denominator is `E`, not `M`; 85 is a schedule reference rather than a strict maximum under interval tolerance. For audit reasons, test in order: resampled count, resampled first-to-last span, fragment loss, final count, final first-to-last span.
- **Separate relaxed eligibility:** a candidate passing every protected sampling, gap-budget, minimum-length, and fragment-loss rule may remain eligible for relaxed review when its final count or retained span fails the main-list threshold. The relaxed group list additionally requires an individual absent from all main groups and an explicit weekly or spatial exception; it does not waive protected temporal checks.
- **Describe full-record coverage:** report first/last dates, tracking span, observed year-month counts and year-months with at least seven observed dates. Neither span nor month count produces a threshold, warning, ranking penalty or relaxed-membership trigger; months need not be consecutive.
- **Retain monthly candidates:** separately within each individual × window-start year × window-start month, retain the strongest main candidate and, only if no main candidate exists for that key, the strongest relaxed candidate. Compare by more final fixes, lower `D/M`, higher retained regular-interval fraction, fewer segments, lower mean absolute retained-interval error from two hours, then lower maximum unsplit source gap. Complete ties retain the earliest scanned start. Regular fraction counts intervals, not affected points.
- **Populate grouping pools:** pool candidates by starting calendar month, considering both all start years together and each start year separately. For an individual's competing windows within a pool, prefer a main-quality window, then more final fixes, lower `D/M`, lower `A/M`, fewer segments, and lower mean interval error. Preserve the earlier encountered window on a complete tie. Actual observed months and years are calculated separately from retained timestamps.
- **Exclude locally, then assess the individual:** rejection of one candidate does not exclude that individual's other candidate periods. An individual is temporally unavailable to the main list only when it has no main-quality window, and unavailable to both lists when no window passes the protected rules. Temporal qualification alone does not guarantee membership in a generated spatial group; keep that outcome separate in the audit.
- **Export provenance:** retain each parent interval, source event, actual timestamp, inter-fix duration, segment boundary, `M`, `D`, `F`, `A`, both coverage denominators, flags, and rejection reasons. Keep all subtrajectories linked to the original individual for downstream train/test splitting. Preserve unsplit source-gap diagnostics even when cuts remove those transitions from the retained segments.

Group section summaries and the rankings tables' `Jaguar IDs` cells show the number of unique individuals and sex counts, e.g. **7 individuals (3M / 4F)**. Counts come from `Sex` in `Jaguar_additional_information_fixed.csv`, joined by original ID; unknown or conflicting values are displayed explicitly. Group backing tables contain `n_males`, `n_females`, and `n_unknown_sex`; member/audit tables contain `sex` and `sex_metadata_status`. Maps retain individual colors and use triangles for male fixes, circles for female fixes, and crosses for unknown sex. Each legend handle has the matching shape and an M/F/? suffix with an explicit legend key, including combined overview maps. These counts and symbols do not affect selection or scoring.

### Descriptive full-record coverage

All 56 individuals are scanned for usable windows. Full-record tracking span and month availability have **no inclusion threshold, warning, ranking penalty or relaxed-membership trigger**. Preserve first/last observation dates, `tracking_span_days`, `observed_months` (distinct year-months with any observations), and `monthly_observed_days` as descriptive metadata.

`qualifying_months` and `qualifying_month_labels` retain the descriptive count/list of year-months with at least seven observed dates by default. `--min-days-per-month` changes only this descriptive definition, recorded as `month_summary_min_observed_days`; there is no required minimum number of such months. For compatibility, `support_warning=False`, `support_violation_codes=[]`, and `support_violation_text=""` remain in exports. Neither these counts nor first-to-last span establish continuous coverage or a complete home range. Selected-window quality and spatial constraints determine candidate eligibility.

### Two-hour sampling and the 20% rule

The sampler chooses actual observations closest to the next two-hour target, preferring an interval in **[1.5, 2.5] hours**. The phase follows the most recently selected timestamp so clock drift does not accumulate against an arbitrary fixed clock grid. When no regular observation is available, the earliest later observation is considered. Intervals in **(2.5, 4] hours** are tolerated irregular intervals. Intervals **over four hours** create hard breaks.

Four hours is the maximum elapsed interval between selected observations. It is not an additional four-hour allowance on top of two hours. Missing locations are not interpolated, and a four-hour interval is not relabelled as two hours.

An individual sampled consistently every 3–8 hours cannot pass these rules. All seven studies remain in the cohort audit; the pipeline checks actual local records rather than excluding an entire study on its median interval, because a collar schedule can change. A genuinely regular two-hour period within an otherwise sparse record can qualify. Weekly density and retained span distinguish main from relaxed candidates.

The 20% budget applies once per **individual candidate period**. Let `M` be the total number of observed fixes selected by two-hour resampling, before segmentation or fragment removal. Across all retained segments, count `A`, the unique retained points adjacent to an interval in `(2.5, 4]` hours. Both endpoints count, while a point shared by two such intervals counts once. Require **`A / M <= 0.20`**, or at most `floor(0.20 × M)` affected points. A segment may exceed 20% locally when the complete period stays within budget. Segment-level percentages are diagnostic; the denominator is never a segment's length or the count remaining after dropping fragments.

Gaps over four hours always force a split. Additional cuts may be made only at tolerated irregular intervals. A cut removes that transition from the affected-point numerator, preserving its observed endpoints in their respective pieces unless a resulting short fragment is dropped. A point remains affected if its other retained neighbor still forms an irregular interval. One pooled dynamic program maximizes retained points across all runs, then minimizes retained segment count and total block count under the fixed period budget. No points are duplicated, and only blocks below the five-point floor can be discarded. The interval-category partition plan is cached independently of timestamp jitter.

For example, a period containing 75 resampled fixes can retain ten affected points in a ten-point segment together with 65 regular fixes in another segment: `10/75 = 13.3%` satisfies the budget, although that segment's local fraction is 100%. If one short fragment is removed from 20 resampled fixes, four affected retained points still use the original denominator: `4/20 = 20%`, rather than `4/19`.

The parent-window metrics remain visible even when cutting removes troublesome transitions from individual segments. Use `retained_affected_points`, `affected_point_denominator`, `affected_point_budget`, and `affected_point_fraction` for compliance. `parent_affected_point_fraction`, `max_source_gap_hours`, `hard_gaps`, and `source_dt_hours` describe the unsplit source. `retained_affected_point_fraction` and `max_segment_affected_fraction` are diagnostic fractions with other denominators. A clean-looking segment does not imply an uninterrupted original week.

Resampling to regular bursts is an established movement-data preparation approach; see [Signer, Fieberg & Avgar (2019), section 2.1](https://doi.org/10.1002/ece3.4823). Research on irregular iSSF data shows that retaining longer-duration steps can help when the model accounts for their durations; it does not validate treating them as regular steps in an arbitrary IRL implementation. See [Hofmann, Cozzi & Fieberg (2024)](https://link.springer.com/article/10.1186/s40462-024-00476-8). A future fixed-time IRL model must handle these exported durations explicitly or use a stricter regular-step training view.

### Minimum length, short fragments, and week acceptance

The default minimum is **five observations per subtrajectory**: four transitions, nominally eight hours at the target cadence. Because intervals down to 1.5 hours are accepted, the mathematical minimum duration is six hours. There is no separate eight-hour duration check. Five observations are a modest technical floor for retaining movement structure, not a literature-derived guarantee of ecological representativeness or sufficient training information. Compare against a stricter minimum, such as ten observations, during model validation.

Shorter fragments may be dropped. The loss denominator is the number of selected observations in that candidate week **before segmentation**, not all raw fixes and not the surviving points. A window is rejected if short-fragment loss exceeds **5%**. The ceiling is configurable; if raised to 10%, loss above 5% produces an audit warning. Individuals are not required to have every fragment throughout their study meet the five-point threshold.

The main and relaxed lists both preserve the same five-point segment floor and 5% loss ceiling. The relaxed list never makes an otherwise invalid cadence or fragmentation pattern admissible. Sensitivity analyses should use the complete candidate population and record the full configuration for each comparison.

A main-list candidate is a complete seven-day interval that may cross calendar-month or calendar-year boundaries. At a two-hour cadence, its reference count is **85 observations**, including both endpoints. At least **68 final retained observations after short-fragment removal** are required (80% of 85), and retained first-to-last coverage must span at least **6.5 days**. Counts refer to observed fixes, not unique occupied grid cells; repeated locations are legitimate observations. The coverage fraction is capped at one and is a count-based quality indicator, not a fraction of continuously observed time.

The **main list** keeps the weekly density and retained-span checks. The **relaxed list** may include a protected-compliant window with fewer than 68 fixes and/or less than 6.5 days of retained coverage. Both lists evaluate all observations within the complete configured window, including observations after any month or year boundary. Boundary crossing does not produce a violation flag or alter the sampling, density, segmentation, or loss calculation. A record ending before the window endpoint can have a shorter observed span; density still uses the complete-window reference count. Violation text states each failed threshold and its observed value. Actual timestamps, counts, and segment boundaries remain available, and no missing fixes are synthesized.

Every candidate still observes the same protected sampling, segment-length, affected-point, and short-fragment-loss rules. The denominator for the loss test is the entire thinned parent window before segmentation; selecting a surviving fragment does not reset it. A shorter retained span is an explicit exception to the weekly comparison, not a complete week of movement.

The temporal stage scans every observation-anchored start and evaluates the complete interval from that timestamp through `week_days` later, including both endpoints. It retains the best window per **individual × start year × start month**, prioritizing retained fixes, lower short-fragment loss, more regular intervals, fewer subtrajectories, and lower interval error. Start month and year identify the candidate pool; actual coverage is calculated separately from retained observations. When a main-quality window exists for that individual/start-year/start-month, it takes precedence over a weaker relaxed window. `data/all_week_candidates.csv` contains the best main-quality windows; `data/relaxed_week_candidates.csv` contains the lower-density or shorter-span alternatives. Neither file is a dump of every scanned start.

Window duration is configurable through `TemporalConfig.week_days`, which can represent multiple weeks or any specified number of days. The reference count is derived from that duration and the target sampling interval; the required retained span is controlled independently by `min_week_observed_span_days` and should be set appropriately for longer windows. Calendar summarization accepts any number of observed months and years and does not assume that a window covers at most two months. This duration setting selects one best window per start-year/start-month pool; it does not request multiple disjoint windows per animal.

`data/individual_audit.csv` records descriptive full-record coverage, main and relaxed window availability, rejection counts, and quantitative evidence for protected-rule failures. `eligible` indicates that the animal was eligible to be scanned; use `has_candidate` and `has_relaxed_candidate` for window availability. Animals with no protected-compliant window remain excluded from both lists and are explained in the audit. Lack of spatial group membership is a separate outcome, not automatically a cadence or data-quality failure.

## MCP95 and spatial grouping

### Full-study footprints and CRS

Each individual's MCP is computed from its entire cleaned study record, before any cadence, week, or month restriction. Coordinates enter and leave as WGS84 longitude/latitude (**EPSG:4326**). Geometry, distance, radial trimming, area, and 500 m grid calculations use **WGS84 / UTM zone 21S, EPSG:32721**, whose units are metres. All 56 animals lie within this UTM zone. A kilometre parameter is multiplied by 1,000 internally; it is never applied as a degree buffer.

MCP95 uses the mean projected location, computes each fix's distance from that mean, retains distances at or below the 95th percentile using the linear/type-7 quantile, and forms their convex hull. Boundary ties are retained. This follows the radial convention described in the [adehabitatHR vignette, sections 3.1–3.2, pp. 8–9](https://stat.ethz.ch/CRAN/web/packages/adehabitatHR/vignettes/adehabitatHR.pdf). It is not a 95% probability contour or a confidence interval.

The excluded outer fixes remain in the telemetry. Trimming defines only the spatial grouping footprint. The final map extent must also enclose every selected observation, including excursions outside MCP95; the same map-budget checks are repeated after these points are added.

Existing `data/mcps/mcp_95_*.gpkg` filenames are misleading: `home_ranges/create_mcps.py` computes an all-point QGIS convex hull without a 95% trimming step. `home_ranges/home_range_analysis.R` also computes all-point MCPs and explicitly labels their contour level 100. These legacy scripts and artifacts are left unchanged. This pipeline recomputes its own MCP95 geometries and provenance.

### Explicit proximity and map limits

| Control | Default | Meaning |
|---|---:|---|
| `growth_buffer_km` / `--growth-buffer-km` | 5 km | Maximum polygon-to-polygon gap from a new MCP to the union of current members |
| `export_padding_km` / `--map-padding-km` | 5 km | Separate margin around the rectangle enclosing MCPs and selected observations |
| `max_extent_side_km` / `--max-extent-side-km` | 40 km | Hard maximum on each padded, grid-aligned map dimension |
| `max_extent_area_km2` / `--max-extent-area-km2` | 1,600 km² | Hard maximum on the padded map rectangle's area |
| `cell_size_m` / `--cell-size-m` | 500 m | Projected grid-cell size |

A five-kilometre growth buffer permits a gap of five kilometres, not ten kilometres from buffering both polygons. The next member must intersect the existing MCP union's buffer; map padding does not create membership. Starting from each possible seed, growth chooses the admissible addition producing the smallest map rectangle, then the smallest gap, then the lowest ID. Every accepted growth prefix can become a candidate, and identical memberships are deduplicated.

Every addition must satisfy both final extent caps. Thus a chain of nearby animals cannot grow across the Pantanal merely because successive neighbors are close. A 40 × 40 km padded map contains at most **80 × 80 = 6,400 cells** at 500 m resolution. The cap bounds spatial state count; actual training memory and runtime also depend on trajectory horizons, actions, features, and algorithm. The grid is aligned to global multiples of the cell size, so outward rounding can add an edge cell.

Reported `area_km2` is the **padded rectangle width × height**, not the sum or union of MCP areas. Individual MCP areas are reported separately. The default two five-kilometre margins leave about 30 km of core span per axis within the 40 km budget. The distance and map caps are explicit operational choices, not an estimated ecological boundary.

Shrinking a fixed individual's MCP100 to MCP95 cannot create additional polygon overlap. The proximity rule can add nearby non-overlapping individuals, and smaller hulls can make some combined rectangles fit the computational budget; these are separate effects.

### Scale justification and limitations

Across the supplied 56 full-study MCP95s, areas range from **4.58 to 288.73 km²**, with median **61.29 km²**, interquartile range **32.54–106.82 km²**, and mean **77.13 km²**. The median equivalent circular radius is about **4.4 km**. This supports five kilometres as an initial proximity/margin scale to test, not a proven optimum.

[Cavalcanti & Gese (2009)](https://digitalcommons.unl.edu/icwdm_usdanwrc/880/) report southern Pantanal **90% kernel** seasonal home ranges of **34.1–262.9 km²**, generally larger during the dry season. Those values give ecological scale context but cannot be substituted for full-duration MCP95 estimates: estimator, contour percentage, sex composition, season, and observation duration differ.

[Morato et al. (2016)](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0168176) distinguish range residency using variograms and note that MCPs have no underlying probabilistic model. Here the full-study hull is a spatial footprint proxy; a dispersing animal or an individual whose range shifted may have a large footprint without a single stable home range. No minimum home-range crossing count is imposed because home-range estimation is not the training objective.

Changing only the growth gap to 2.5/5/10 km on all 56 spatial footprints gives 192/194/198 greedy prefix candidates, with a largest group of 12 at each setting under the default map caps. These are spatial sensitivity checks before temporal eligibility, not the final candidate counts. Rerun temporal selection and ranking for a meaningful comparison of actual training alternatives.

## Ranking and alternative selections

Candidates share the calendar month in which their windows **start**, with all start months and years in the study searched. For each start month, the pipeline considers both a pool across all start years and each individual start-year pool, retaining each animal's strongest available candidate within that pool. A December-start window can therefore contain January observations in the next year. For example, a mixed-start-year group can combine one individual's December 2009–January 2010 window with another's December 2013–January 2014 window; both share the December start-month pool, and their actual observation years remain distinct in the exported coverage. Start-month matching provides a broad seasonal alignment; windows can extend into adjacent months or seasons, and matching start months does not establish identical flood stage, vegetation, or weather across sites and years. Use the actual observation dates for environmental covariates and inspect seasonal conditions before treating alternatives as interchangeable.

For per-animal retained counts `n_i`, with `k` animals:

```text
Jain evenness = (sum(n_i))² / (k × sum(n_i²))
balanced_fixes_score = sum(n_i) × Jain evenness
```

Evenness is one for equal contributions and decreases when a few animals dominate. This compares total retained trajectory lengths **per individual within its selected week**, not the lengths of every individual subtrajectory. Count CV and minimum/maximum count ratio provide additional diagnostics. Higher score is preferred, followed by greater median density, lower median affected-point fraction, smaller map area, then deterministic month/ID ordering. This score prioritizes quantity adjusted for balance; it is not measured predictive accuracy.

Each list has **one displayed rank**: the main list uses G01, G02, … and the relaxed list uses R01, R02, …. Rank matches the group's position in its section list and rankings table. The compact selection contains the first-ranked main groups.

The report displays every generated main group, then every generated relaxed group. Each group has one ID, rank, rankings-table entry, detailed section, MCP/trajectory map, per-animal count chart and histogram, date/quality tables, and explanation of any window-quality or spatial exceptions. The rankings tables initially show seven rows, with the remaining rows expandable.

The single January–December navigation combines both lists. A group appears under **every calendar month containing at least one of its retained observations**, with repeated links pointing to the same section. Within each month, unflagged main groups appear first, followed by flagged main groups, then relaxed groups, with rank order maintained within each category. A month-specific link lists the years actually represented in that month and the number of distinct members contributing observations there. An animal observed in the same calendar month in multiple years counts once in that month's member count. Monthly group counts can overlap; the report-wide count is the number of unique groups.

Calendar labels use actual retained year-month pairs. Consecutive periods can be compressed, such as “Dec 2014–Jan 2015,” while separated periods remain separate, such as “Jan 2014; Jan 2016.” Unobserved intervening months are not inferred from the group's full date envelope. These summaries are shared by navigation, rankings, section titles, and figure labels, and support arbitrary numbers of observed months and years. All navigation copies of the current group receive the selected styling.

`--report-limit` optionally caps the detailed output; omitting it reports all generated candidates. The compact exports `data/ranked_groups.csv`, `data/group_members.csv`, `data/selected_points.csv`, and `data/trajectory_manifest.csv` contain the first-ranked main selections. The main `report_*` exports and separate `relaxed_*` files contain the wider review data. Support warnings do not impose a hidden ranking penalty; rank remains the documented count/evenness score order. Alternative groups can repeat source events; more displayed candidates do not create additional independent training data.

### Groups containing individuals absent from the main list

Secondary candidate generation starts from individuals absent from **all main groups**, not just those absent from the first seven. A relaxed group must contain at least one such individual and document a relaxed weekly or spatial requirement. Its companions can be individuals already present in main groups. Start-month matching, full-study MCP95 construction, 500 m cells, and the protected temporal rules apply to both lists.

The pipeline first attempts ordinary 5 km growth and the 40 km / 1,600 km² map caps using protected-compliant temporal candidates. For an otherwise unrepresented animal, a bounded fallback selects a minimum-extent **pair** within a common start-month candidate pool, preferring a pair within the 5 km MCP gap. Pair-only fallback prevents uncontrolled chains of nearby MCPs. If the pair needs a larger map or a greater gap, the group records its actual padded width, height, area, and/or polygon gap against the main threshold. The map still includes all selected fixes, including excursions beyond MCP95.

These are review alternatives with explicit exceptions, not automatically approved training inputs. A large spatial exception, short observed span, or unequal point contributions can affect both ecological comparability and computation. Animals with no protected-compliant window cannot be rescued by relaxing the spatial or weekly criteria.

With the supplied data and default configuration, the output contains **222 main groups representing 18 individuals**, with no full-record support warnings. The **31 relaxed groups add IDs 12 and 19**, giving 20 represented individuals across both lists. The remaining **36 individuals** have no scanned window satisfying the protected sampling, segmentation, and loss requirements. ID 88's highest-retained rejected week retains 49 of 55 sampled points, requiring 10.9% short-fragment loss against the 5% ceiling. The 253 unique groups generate 420 monthly navigation links. These counts describe this input and configuration.

Point CV and Jain are dimensionless descriptions of per-animal observation-count balance. The report uses population standard deviation, so they satisfy **Jain = 1 / (1 + CV²)** exactly; they are not independent quality metrics. Only Jain affects the balance penalty in the score. The report explains their definitions, why count balance is useful here, and limitations, with links to NIST, Jain et al. (1984), the dataset-size CV case study in Hönig et al. (2022, DAdaQuant), and selection-count Jain case study in Jeong & Kim (2022, CATA-Fed). Those are methodological analogies, not evidence that equal jaguar fix counts improve IRL accuracy. Source-backed wording and bibliography are maintained in `pantanal_metric_notes.py`.

Spatial growth is a deterministic greedy heuristic, and only one configured window per animal/start-year/start-month survives the temporal stage. The resulting ranking is not an exhaustive optimum over all possible member subsets, weekly combinations, or covariate-map extents.

## Dates, IDs, validation, and later model use

`data/group_members.csv` gives each member's selected start/end, observed duration, exact candidate-window bounds, and full-study start/end/duration. `data/ranked_groups.csv` gives corresponding group envelopes, year membership, and shared week overlap. A group's earliest start to latest end is a **date envelope**, not continuous data coverage. For mixed-year groups it can span years even though each main-list member contributes only approximately one week; relaxed-list members may contribute substantially shorter spans. `same_year=true` means that **all retained observations in the group occur in one calendar year**, determined from the observed-year union rather than the windows' start years. A December–January group therefore spans two years even if every member has the same start year. `shared_years` lists the intersection of the members' observed-year sets. `grouping_years` and `same_start_year` describe only the start-year pools. Neither measure establishes that selected windows overlap in time; inspect `shared_week_overlap_days` for the overlap of their first-to-last date envelopes.

Build covariate maps for the actual member dates and the shared spatial rectangle. Full-study MCP dates explain the spatial footprint's provenance, not the time period over which dynamic training covariates should be averaged. Segment durations sum only retained within-segment intervals; gaps between segments are not observed movement coverage.

Each subtrajectory has a stable ID such as `jaguar_12_20100101T000000_s001`, alongside the original `individual_id`, `window_id`, and source event IDs. `data/trajectory_manifest.csv` records `split_group_id=individual_id`. All weeks and subtrajectories from an individual must remain together in training or held-out data when evaluating generalization to new animals. Segmentation does not create independent biological replicates. Training and uncertainty estimates should also consider unequal per-animal contributions.

Animal-level splitting prevents direct reuse of the same individual's movement in both folds; it does not eliminate shared-site environmental dependence. If the intended claim is transfer to new areas or years, use additional spatial or temporal blocking. Structured validation must reflect the prediction target; see [Roberts et al. (2017)](https://doi.org/10.1111/ecog.02881). Spatial footprints made from the full study, including held-out trajectories, are acceptable for exploratory cohort design but should not be mistaken for a completely blind new-region evaluation. Freeze the evaluation design and preprocessing appropriately before reporting predictive performance.

All groups in both lists are **alternatives**, and can overlap in animals, weeks, and source fixes. Do not concatenate exported alternatives without deduplicating their original events and deciding the intended weighting. For a biome-wide model, future work can jointly train a common reward model across compatible maps, with consistent feature definitions/scaling and animal-level splits, or evaluate an ensemble of separately fitted models. Naively averaging learned parameter vectors does not generally create a valid pooled model, especially when feature scaling, map support, or reward identifiability differs. No such training or combination is implemented here.

## Files and implementation

| Output under `analysis/pantanal_selection/` | Contents |
|---|---|
| `index.html` | Main and relaxed candidate lists, ranked tables, calendar navigation, and quantitative exception explanations |
| `images/` | Per-group and first-ranked overview PNG figures; HTML embeds its figures and links to overview files here |
| `data/ranked_groups.csv` | First-ranked main groups, dates, balance metrics, flags, and map dimensions/area |
| `data/report_groups.csv` | Main groups displayed in rank order, with quantitative violation fields |
| `data/report_group_members.csv` | Individual-level dates, counts, and quality for every displayed group |
| `data/report_points.csv` | Observations for every displayed group, including their group-specific grid cells |
| `data/report_trajectory_manifest.csv` | Segment metadata for every displayed group |
| `data/group_members.csv` | Individual-level dates, quality, study provenance, and counts per selected group |
| `data/trajectory_manifest.csv` | Segment IDs, original individual/split IDs, lengths, durations, and interval quality |
| `data/selected_points.csv` | Observed selected fixes, original events, elapsed times, group IDs, metric coordinates, and grid cells |
| `data/all_week_candidates.csv` | Best main-quality window per individual/start-year/start-month, with descriptive full-record coverage, actual calendar coverage, and audit metrics |
| `data/all_group_candidates.csv` | All enumerated main groups in score order |
| `data/relaxed_week_candidates.csv` | Protected-compliant lower-density or shorter-span windows and exact threshold exceptions |
| `data/relaxed_group_candidates.csv` | All generated secondary groups in their separate rank order, with exact exceptions |
| `data/relaxed_report_groups.csv` | Secondary groups included in the HTML report |
| `data/relaxed_group_members.csv` | Per-individual dates, counts, weekly/spatial flags for secondary groups |
| `data/relaxed_points.csv` | Secondary observations with original source events and group-specific grid cells |
| `data/relaxed_trajectory_manifest.csv` | Secondary segment metadata, original animal/split IDs, lengths, and interval quality |
| `data/group_month_coverage.csv` | One row per group and observed calendar month, including that month's years, distinct members, and fix count |
| `data/group_year_month_coverage.csv` | One row per group and observed year-month, including members, fix count, observed dates, and first/last retained fix |
| `data/individual_audit.csv` | All 56 individuals, study support, candidate availability, and rejection reasons |
| `data/cohort_audit.csv` | Seven-study membership, fix counts, and date spans |
| `mcp95_full_study.geojson` | Full-study MCP95 polygons in WGS84, with method and trimming provenance |
| `data/mcp95_summary.csv` | Per-individual areas, full dates, and raw versus hull-input fix counts |
| `selection_manifest.json` | Saved configuration, source checksum, audit, selected data, and source references |

The `observed_months`, `observed_years`, and `observed_year_months` fields summarize retained observations, while `grouping_month`, `grouping_year`, and `grouping_years` identify the start-month/year pools. The legacy `month` and per-window `year` fields also refer to the window start. `calendar_coverage` provides per-year-month member IDs and fix counts; `month_coverage` combines each calendar month across its represented years, deduplicating member IDs. These fields are calculated from retained timestamps and remain valid for windows spanning multiple months or years. Repeated observations from overlapping windows are counted once per individual and timestamp in calendar coverage.

`movement_processor_pantanal.py` orchestrates parsing, ranking, and exports. `movement_temporal.py` provides observed-fix sampling, the Pantanal pooled-period segmenter, and the separate general-processor segmenter. `pantanal_temporal.py` uses those primitives for week selection and descriptive full-record coverage. `pantanal_calendar.py` summarizes calendar coverage from retained observations. `pantanal_spatial.py` handles true MCP95 geometry, projection, candidate growth, and map extents. `pantanal_report.py` renders the local report. These modules preserve the data needed for a later model implementation to make explicit decisions about irregular durations and train/test membership.

Run the targeted synthetic regression checks with:

```bash
python3 -m pytest jaguar_irl/data/test_pantanal_temporal.py jaguar_irl/data/test_pantanal_spatial.py jaguar_irl/data/test_pantanal_calendar.py jaguar_irl/data/test_movement_processor_pantanal.py jaguar_irl/data/test_pantanal_report.py -q
```

All numeric screening choices should be assessed through sensitivity analysis and held-out model performance. Density-based selection can favor particular collar schedules and habitats; it is a useful training-data screen, not a correction for habitat-dependent missing observations.
