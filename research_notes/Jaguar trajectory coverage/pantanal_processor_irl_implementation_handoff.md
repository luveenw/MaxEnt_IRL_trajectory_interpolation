# Pantanal processor and IRL implementation handoff


## Current policy clarification — 2026-11-01

The next separate processor must **use the approximately two-hour [1.5,2.5]-hour thinned representation to select windows/groups**, while preserving all original parsed source observations within each selected window in immutable checkpoints. Export both fine and two-hour representations for matched model training/testing. This supersedes the source-only group-admission/ranking redesign proposed below; source coverage remains a useful diagnostic, but must not silently replace the thinned selection basis. Reuse the locked selection strategy as the baseline, including its protected cadence/fragment screens and main-versus-relaxed window criteria, unless a later change is explicitly agreed. This selection policy is implemented in the separate seasonal pipeline. See the seasonal completion record below; the frozen original implementation remains unchanged.

The separate exporter now defaults `min_final_retention_fraction` / `--min-final-retention` to **0**, disabling only the final F/M ratio gate for the two-hour representation. Require M>0 and F>0, retain the gap/affected-endpoint/fragment-length rules, and always report F/M. An explicit `.8` restores the former ratio requirement. Fine export has no F/M gate. The locked selector's 5% fragment-loss cap and weekly density/span rules remain unchanged. Existing immutable export/checkpoint artifacts retain their recorded policies; new export identity hashes capture the changed configuration and software.

Updated 2026-10-31. This is the execution checklist for the consolidated [Pantanal sampling, grid representations, and IRL experiment specification](pantanal_sampling_time_and_grid.md). That document defines the scientific policies. The [completed checkpoint/export implementation record](pantanal_checkpoint_export_implementation.md) defines the currently implemented subset, concrete contracts, artifacts and freeze boundary. Reinspect these status records before editing code.

## Current execution status

- [x] Checkpoint/export phase completed, followed by explicitly authorized selector/report revisions removing the tracking-span criterion and supported-month warning and adding sex counts/marker styles. Other selection rules remain unchanged.
- [x] Existing selector now supports immutable source checkpoint generation and checkpoint-only execution. Production checkpoint: `analysis/pantanal_selection/checkpoints/selection_8cc3315f50f9395c0e399726/`.
- [x] Standalone fine/two-hour/paired route exporter, provenance, diagnostics and validation implemented. Export-only F/M gating is optional and disabled by default (`--min-final-retention 0`); `.8` restores the former minimum. There is no separate 5% ceiling. The selector retains its separate sampling/density policy; full-record tracking span and year-month counts are descriptive only.
- [x] Recomputed selection, scores/ranks, report assets and the current checkpoint; all 253 groups retain their memberships, periods, scores and ranks. The latest month-warning removal clears 53 group flags, following 40 cleared by tracking-span warning removal. All 222 main groups are unflagged; 31 relaxed groups retain measured window/spatial exceptions. Selector/checkpoint/report scope re-frozen with a [file-hash inventory](pantanal_processor_freeze.json); further original implementation changes require an explicit user switch back.
- [ ] Production experiment groups and animal splits remain unassigned. No model was trained.
- [x] Separate seasonal selection, ranked group collections, source-preserving checkpoints, seasonal coverage/ownership/density HTML diagnostics and collection export implemented. See [seasonal completion and artifact record](pantanal_seasonal_implementation.md) and [usage/contracts](../../jaguar_irl/data/README_PANTANAL_SEASONAL.md).
- [ ] Trainer repair/integration, fitting/evaluation, HTML integration of model/export information-loss diagnostics and future backends remain pending. The source-only selection redesign is superseded by thinned selection with source preservation.

Cell-runs are explicitly deferred, including their optional export mode. Groups are computational map domains; see [shared biome reward research](biome_shared_reward_training.md) before implementing model combination. The execution steps below remain the broader roadmap, not a claim that all have been completed.

**Initial scope:** a tractable one-week, source-versus-two-hour comparison using the repaired route-only plain-MaxEnt model. Residence-aware models, uMaxCausalEntIRL and behavioral classification are future work, not initial dependencies. No required `cell_runs.csv` or stay-action expansion. Confirmed initial settings: five retained observations in both source and two-hour fragments (`min_source_segment_points=5`, `min_comparison_segment_points=5`), before compression/interpolation, and `behavior_selection=all_retained`. The four-hour gap guard is unchanged. Five is a configurable project choice; behavioral comparisons remain deferred.

## 1. Scientific contract

The objectives are to predict jaguar routes in relation to landscape characteristics/change and quantify information and predictive performance lost through coarse observations and preprocessing.

- Preserve QC, unthinned observations as the primary source for spatial route demonstrations, including fixes less than 1.5 h apart.
- Treat two-hour thinning as an experimental treatment and a basis for standardized movement summaries. MaxEnt IRL does not inherently require regularly timed GPS fixes.
- Assess route observability explicitly: source/thinning gap durations, same-cell/nonadjacent jumps, inferred-transition fractions, excursions, GPS uncertainty and grid alignment. No one statistic proves adequate observation.
- Compare predictions against the same held-out measurements, with shared spatial resolution, maps, conditioning information and a declared prediction-horizon protocol.
- Separate a spatial step index from elapsed time. Neither a GPS fix nor a grid transition is automatically a two-hour decision.

## 2. Implement thinned-track group selection with source preservation

**Current instruction:** follow the locked thinned-track selection/ranking strategy and preserve unthinned records in checkpoints. Any source-only admission or source-coverage ranking instructions below are superseded alternatives, not the next implementation default.


Use the complete 56-ID/seven-study cohort in specification §3; audit every animal, including those that cannot enter a model comparison. Rolling windows default to seven days and allow month/year crossings and mixed years. Retain start-month candidate pools and multi-month calendar links. Source span below 6.5 days can be a relaxed candidate. Full-record tracking span and year-month counts are descriptive only, with no minimum, warning, ranking penalty or relaxed-membership trigger.

Generate groups using source coverage and full-study MCP95, independently of two-hour-track eligibility. Retain EPSG:4326 coordinates and EPSG:32721 metric calculations, 500-m cells, 5-km proximity/padding, 40-km side and 1,600-km² caps. Include selected-window source excursions in map extents; do not clip them. The precise MCP construction, chaining prevention and relaxed handling are in §3.

Replace standardized-point ranking with the proposed source-bin coverage score `sum(b_i) × Jain(b_i)`, with two-hour ranking bins, explicit tie-breaks and status ordering as defined in §3. This is a ranking recommendation, not a validated ecological quality measure or resampling requirement. Preserve actual point-count/length histograms, CV and Jain diagnostics separately. Rank positions must match their declared lists; immutable group keys must survive re-ranking.

Preserve all-candidate reporting, the unified calendar, multiple calendar links to one group, flags, section/table links and collapsed rows after seven. Add independent fields for group status, source-route usability, standardized eligibility and future latent-model feasibility (`deferred/not_assessed` initially). Full-study domains containing test-animal locations support known-domain evaluation, not independent spatial transfer.

## 3. Export three linked representations

Implement the exact contracts in specification §4:

1. **Source:** all QC fixes in candidate windows, original timestamps, coordinates, event IDs, source boundaries and GPS/error metadata; rejected records have an audit.
2. **Standardized comparison:** actual observations selected closest to +2 h within [1.5,2.5] h, with deterministic fallback/ties. Let M be selected points before segmentation. Split >4 h edges; allow additional cuts at (2.5,4] h edges. Across final segments, unique affected endpoints A must satisfy A/M ≤ 0.20 over the entire window. Apply the confirmed configurable comparison-fragment minimum of five retained observations before compression/interpolation and require nonempty retained evidence. Final F/M is diagnostic by default; `--min-final-retention .8` optionally restores the former 80% minimum. Remove the separate 5% loss cap and expected-schedule exclusion. Failures affect this representation, not source/group membership. Preserve all diagnostics and calculate common-duration movement metrics before gridding.
3. **Grid/model views:** construct independent all-source `fine` routes and derived `two_hour` routes on a common grid. Collapse consecutive repeated cells with provenance; retain leave-and-return excursions. Explicitly mark rasterized gap connections as inferred. The root model requires adjacent nonstationary `[row,col,k]` arrays. Its initial >4 h source-gap imputation guard is a baseline construction choice, not a universal source/U exclusion. Future U would receive original timestamped observations with emissions, never inferred cells as evidence.

For paired R experiments, use identical trainable intervals/endpoints from both representations, respecting all source/construction cuts. Record the intersection/exclusions without restricting the independent fine dataset to that intersection. Save source/comparison data, grid/event links, pairs and fragment/window diagnostics. Future observation packages and cell runs are derived on demand. Source same-cell fragments remain cataloged; L=0 is unsupported by the route trainer. A single adjacent move with fixed endpoints/horizon has no route choice; preserve it diagnostically and skip unnecessary optimization, with consistent normalization as specified in §6. Apply the five-source-observation floor first: shorter fragments remain checkpoint/audit records, while even five qualifying observations can collapse to a single adjacent move with no route choice.

## 4. Repair and integrate the spatial baseline

Add a contained `write_selection_checkpoint` path to `movement_processor_pantanal.py` and a separate `jaguar_irl/data/export_pantanal_irl.py` entry point. Existing selected-point/report manifests are insufficient because they omit unthinned observations and can depend on report limits. Implement specification §4D: deduplicated source events, candidate windows, all group memberships/grids, configuration/hashes/QC metadata and deterministic references. Export must run without the original CSV and must not rerun clustering for fragment-only changes. Train selected experiment groups, not all report candidates automatically. Shared pure helpers are acceptable; keep selection, export and fitting separately runnable. Do not alter the general processor's separate policy or reactivate excluded legacy model folders accidentally.

The exporter creates arrays, companion manifests, provenance and fragment diagnostics, with optional future cell-run export disabled. `pantanal_report.py` attaches per-individual fragment tables, configurable-window timelines and duration-versus-L plots from matching export diagnostics. Report bounded-gap-supported span/union coverage separately from continuously observed paths, occupied bins and trainable-route coverage. Cache assets and allow report-only regeneration.

Root `train.py`/`test.py` integration must follow specification §6: configurable manifests/paths/checkpoints/splits; Python/NumPy compatibility; matching empirical/expected feature normalization and departure-state convention; verified gradients; dynamic horizon allocation instead of 610; memory limits; per-period maps with common features; shared animal/window weighting; and isolated caches.

Fit `R_fine` and `R_2h` with the same repaired spatial architecture. Standardized coordinates are not directly valid training input until converted to adjacent grid routes. All versions and windows of an animal stay in one saved partition across groups. Select parameters/checkpoints on validation animals. Keep held-out reference paths separate from prediction inputs.

Use the same training-fitted operational horizon distribution for both R arms. A shared true reference length is allowed only as a labeled oracle-horizon diagnostic. Save complete sampled routes as well as distributions; cumulative occupancy is not cell-visitation probability.

## 5. Deferred uMaxCausalEntIRL implementation

This section is a future work package. It must not block or enlarge the initial plain-MaxEnt implementation. The separate residence/rate roadmap and supporting movement-model literature are in specification §6; neither future approach is assumed to improve jaguar predictive performance before testing.

Use [Bogert, Gui and Doshi (2022)](https://arxiv.org/pdf/2208.06988), particularly §3.1/Algorithm 1 and §5. Reproduce its discrete observation-noise example before extending it. The variable-count clock and bridge below are explicit project extensions, not already-established jaguar results.

Implement all three mathematical components in specification §7:

- **Observation likelihood:** `e_i(s)=p(omega_i|s,Sigma_i)`, including cell support and GPS uncertainty at both endpoints. Distinguish unobserved time from known fix failure. Keep error/detection parameters fixed initially; estimate/calibrate only from permitted training evidence.
- **Elapsed-time kernel:** induce `P_theta(s,s')=sum_a pi_theta(a|s)T(s'|s,a)` and marginalize unknown counts: `K_theta(Delta)=sum_n q(n|Delta) P_theta^n`. The proposed stationary prototype uses a calibrated Poisson clock, giving `exp(lambda*Delta*(P_theta-I))`. Hours are not the exponent n. Self-transitions/opportunities and physical cell moves must be counted separately. Use ordered kernels/state augmentation when the policy or duration process is not stationary.
- **Trajectory bridge:** forward–backward over all pings, marginalizing uncertain boundary cells and latent counts; accumulate expected state/action features and sample complete paths, including loops and zero-move cases. Use distributions rather than a single imputed path. Update a causal-entropy policy with the correct expected complete-data objective; do not transplant the legacy gradient blindly.

Use a separate U backend with explicit clock, dynamics, emission, discount, feature and termination semantics. Validate sparse computation, posterior count-tail convergence, observation likelihood and gradients. A two-hour gap must never silently become one latent move. The homogeneous clock is a starting approximation requiring empirical validation; it does not encode a hard speed bound. See §7 for alternatives and identifiability limits.

Fit `U_fine`/`U_2h` where feasible and include fully observed/ordinary causal-entropy controls. Comparing only U with legacy R mixes observation treatment with architecture changes. Freeze common calibration choices across paired arms; do not estimate clock/error parameters from hidden test routes.

## 6. Evaluate and regenerate deliverables

Specification §§5 and 8 define four separate experiments: practical native-versus-two-hour, controlled common-cadence, missing/noisy-data handling, and cohort/spatial sensitivity. The fine model is not evaluation truth.

Report information loss; hidden-point-to-route distance; secondary geometry/cell/habitat recovery; ensemble coverage–area and spread; and paired animal-level uncertainty. Keep spatial-route likelihood diagnostics separate from U observation predictive density. Avoid supplied-endpoint error, best-of-samples scoring against truth, or time-aligned metrics for models without a clock. Preserve historical map dates and distinguish landscape association from causality.

Execution order:

1. Record the confirmed five-observation minima and all-retained behavioral selection, then thinned-track selection/ranking with source preservation and audit tests; regenerate groups/backing files/HTML in a versioned output directory.
2. Lossless checkpoint, standalone linked-representation export, pairing and observability reconciliation; freeze the experiment manifest.
3. Root trainer repairs verified on tiny grids; profile bounded workloads and fit/evaluate matched R arms.
4. Attach per-individual diagnostics and export initial information-loss, case, animal, paired-comparison and coverage–area results, prediction routes and comparison report. This completes the initial model experiment without residence or U implementations.
5. Later, explicitly scope residence/rate or behavioral prototypes, or discrete-paper U reproduction and clock/emission/bridge validation; evaluate gains and computational cost before expanding the pipeline.

Before initial production, satisfy specification §9's initial acceptance list: checkpoint completeness/standalone operation, source preservation, accepted count floors, no 5%/68-of-85 exclusions, period-wide ratios, animal-disjoint splits, common test evidence, route-gradient/action/horizon checks and memory bounds. Bridge/clock/residence/posterior tests belong only to the deferred stages. Keep actual completion status separate from this specification. No implementation, staging or commit is implied by these document edits.
