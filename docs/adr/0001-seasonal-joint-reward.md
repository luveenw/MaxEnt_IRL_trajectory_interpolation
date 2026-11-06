---
status: accepted
recorded: 2026-11-03
---

# One seasonal shared reward across local spatial domains

We fit one shared reward parameter vector to all selected spatial groups in a
Pantanal season, using separately evaluated local maps and multiple routes per
original individual. This accommodates manageable raster extents and a static-map
solver while retaining locally usable bursts; it avoids repeatedly fitting
successive prefixes of groups or requiring a whole-biome raster in memory.

The [operating manual](../../jaguar_irl/training/README_SHARED.md) is the maintained
source of input/output contracts, commands, thresholds and recovery procedures.

## Consequences

- Clarified 2026-11-04: map groups are computational partitions based on nearby
  MCP95 domains, not split strata. Whole animals are allocated independently of
  group membership; domains with no training animals are allowed. The shared
  policy is fitted from training routes and will be evaluated on held-out routes
  in their required maps. Split-specific environmental-epoch plans now support train/test separately;
  the evaluator remains unimplemented; training-support constraints must not be added
  to the animal split to compensate for those missing interfaces.

- Seasonal maps pool years under an explicit approximation; the implementation
  does not switch feature maps by movement date or correct irregular durations.
  A representative season-year is selected per extent for covariate queries only;
  it never restricts the trajectory years. The local planner ranks distinct
  contributing animals, then animal-days, then the earliest tied season-year,
  and preserves the full multi-year evidence roster and candidate-year counts.
  Product availability and ecological temporal fidelity remain separate checks.
- Identity, seasons, source-event ownership and map mappings are preserved in
  metadata. The training coordinator uses them; the numerical likelihood core
  evaluates one route/map without animal or calendar semantics.
- Every optimizer update evaluates all groups at the same coefficients. The
  implemented objective averages trajectory likelihoods within individuals and
  then across individuals. Its difference from the older per-step/window
  proposal is recorded as an unresolved scientific choice in the manual.
- A selection checkpoint describes source evidence; a training checkpoint stores
  optimizer progress. They remain distinct artifacts.
  Group exclusions and explicit map-size exceptions belong to the new run plan,
  without relabelling historical export diagnostics. The user-approved G324
  exception waives only side/area limits; other spatial/route checks and runtime
  memory limits remain enforced. Inclusion/exclusion defines separate joint fits.
- Training saves only fully evaluated optimizer iterations. A complete immutable
  weight/metadata generation is activated atomically; unfinished group work is
  repeated after interruption. Partial-group state and stage-lineage rollback
  were rejected to keep resumption simple and reproducible.
- Scientific testing/prediction integration is pending. Operational fitting and
  numerical verification are not evidence of ecological adequacy or transfer.

- Size-only map-budget exceptions are accepted automatically and reported;
  historical export admission flags are preserved. Other validity and runtime
  limits are unchanged. Training-empty maps are retained in the inventory and
  skipped by the fitting objective.
- Each route is normalized over feasible fixed-start/fixed-goal/fixed-move-count
  alternative paths in its map. Domain boundaries may affect learned weights;
  unreachable cells have zero mathematical contribution. Boundary sensitivity
  is a known limitation, not a completed scientific validation.

## Split and input-profile preparation2026-11-04

The Spring34/9 animal-only allocation is now frozen with seed20261104; no
map-group constraints apply. The split-labelled export preserves original arrays.
Separate train/test epoch plans resolve through the shared cache inventory.
`animal_splits.py` generates the reproducible allocation and `cache_bindings.py`
creates file references and optional candidate scaling statistics. Binder
`--binding-dir` and trainer-preparation `--binding-state` support isolated
version roots without cloning checkpoints or moving/duplicating arrays.
Default checkpoint-sidecar behavior remains compatible with existing callers.
Candidate raw-unit and z-score profiles are prepared. The user selected an
unregularized baseline (`--l2 0`) with Hirakawa-style full-training-map upper-bound
scaling, subsequently superseded by hull-wide maxima across all selected seasonal
extents (population selected training years only), frozen for test; no ecological
optimizer run has started. L2 and z-score scaling are potential later adjustments.

Hirakawa's author code loads a prepared feature stack, without our manifest
registry. AppendixS2's feature range is[−1,0]; noL2 term appears in the checked
paper/trainer. Our optional L2 and proposed equal-animal z-score are explicit
adaptations needing review rather than paper requirements.
[Source review](../../research_notes/Jaguar%20trajectory%20coverage/hirakawa_feature_scaling_regularization_review_20261104.md).

## Implementation audit2026-11-04

Joint fitting is implemented in `jaguar_irl/training/shared.py` and the exact
likelihood core, with atomic storage in `shared_storage.py`. Current21trainer/
planner tests pass. Persisted schema2 demonstrations use synthetic features on
three extents, with resume/uninterrupted agreement. Their completion reason is
iteration limit, not proof of a converged ecological optimum. All six real
Spring raster caches are now prepared, but separate ecological input-profile candidates have since been prepared; no
ecological optimizer fit has been run in the inspected workspace. The current model uses a linear landscape
reward; a separate learned movement-feature/kernel component and formal
prediction/evaluation/CV/ablation interfaces remain future work.
[Implementation audit](../../research_notes/Jaguar%20trajectory%20coverage/shared_training_implementation_audit_20261104.md).

## Considered alternatives

Cumulative A, A+B, A+B+C fits repeat earlier optimization and create stage-order
and restart dependencies. Independent per-group fits followed by coefficient
averaging do not optimize the joint objective. A single geographic mega-raster
creates avoidable asset and computation burdens. Time-varying maps could address
finer environmental changes, but require a separately designed model/input
extension and are outside the present seasonal-static decision.


Seasonal scaling bounds are finalized only after all group extents and their
covariate extractions are complete. The convex hull is a scaling reference
domain; it does not expand the training domains or require a hull raster cache.
Spring selects `hirakawa_hull_bounds`, with roughness U=631.602294921875 m² and
population U=7018.03466796875 people/km². Historical profiles are preserved.


Training observability (2026-11-04): JSONL event history and an atomic live
progress snapshot are operational sidecars, separate from immutable plan and
optimizer generations. They never determine recovery or enter checkpoint
identity. Log route/evaluation, line-search, iteration and checkpoint progress;
only the published `current` generation resumes numerical work. The first
unregularized Spring run uses a two-update pilot then the same checkpoint for
continuation, preserving one joint objective and cohort.


## Convergence and immutable continuation — 2026-11-04

New training plans default to no iteration cap (`optimizer.iterations=null`),
stopping successfully at the frozen gradient tolerance. Explicit total-update
caps and per-invocation pauses remain supported. An uncapped run may still fail,
be interrupted or have no finite unregularized optimum. A cap is not convergence.

An existing capped experiment is extended through a new immutable continuation
plan, not mutation of its historical plan/checkpoints. Parent hashes, state,
weights and iteration/history are retained. Core/storage code hashes must match;
wrapper migrations reevaluate and verify objective/gradient at the source weights.
The source remains untouched; the new plan and logs track continuation separately.
Source inputs, model, scaling and all optimizer settings other than the cap remain
identical. Tests cover warm start, uncapped updates, idempotence, interrupted
publication recovery, source preservation and changed-core rejection.

## Training artifact retention

The trainer retains five recent complete checkpoints and any pins while
training. At a terminal criterion it retains the final generation and the
pins. Continuations register their source checkpoint under the source writer
lock before publishing a child plan. Explicit pin markers support analysis
and older cross-directory continuations, and sibling plans protect their
legacy references. Pruning runs under the writer lock after publication and
on resume.

The live snapshot continues to report route progress. The durable JSONL log
records accepted updates, failures, and pause or completion status by default.
Full event tracing is available through `--trace-routes`.

The training harness runs storage housekeeping under its writer lock and
records log rotation, compression, archive expiry and checkpoint pruning in
`housekeeping.jsonl`. It retries interrupted compression from the intact
closed segment on resume. Jobs can opt into a compressed archive count limit
per stream using `--keep-log-archives`. The audit stream also rotates and
compresses and follows the same archive count limit. The checkpoint policy
continues to protect downstream pins.

For a cluster transfer, continuation can map paths from the original repository
root to the copied root. It checks the immutable source plan and checkpoint
identity using their original contents, verifies the relocated inputs by hash,
and re-evaluates the saved objective and gradient before publishing a new plan.
The new continuation pins the copied source generation. New training plans
store executable references relative to their run directory, and new binding
states store raster paths relative to the state file. Runtime resolution
leaves the stored plan and checkpoint identity intact when the workspace moves.
