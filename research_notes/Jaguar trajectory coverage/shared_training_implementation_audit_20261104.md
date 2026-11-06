# Shared-reward multi-extent training: implementation audit

2026-11-04. Code/artifact audit and current targeted software tests. No new
animal allocation, feature binding or ecological fit was performed. The parent
agent is updating the maintained manual; this note does not change code.

## Conclusion

**Joint fitting across multiple extents is implemented and tested for the current
static, fixed-start/fixed-goal/fixed-grid-move-count MaxEnt model.** It is not
merely a proposed coordinator. Scientific prediction/interpolation, animal-level
assessment, internal CV, and the complete thesis comparison remain unimplemented
or unreviewed. The six-feature real Pantanal ecological fit has not been run in
the artifacts inspected. “Implemented trainer” is therefore more precise than
“the entire training/evaluation workflow is finished.”

## Implemented path and source locations

- [`shared.py`](../../jaguar_irl/training/shared.py), lines87–160: named feature
  bindings with units/definitions/shared affine scaling, exact checkpoint-grid
  declarations, finite numeric array/shape checks, hashes and atomic sidecar
  publication. Paths are relative to the supplied manifest, not the shell CWD.
- `shared.py`, lines285–365: `prepare` validates one seasonal collection or
  explicit group selection, bindings, export identities, source ownership,
  admitted routes and settings; publishes an immutable-input run plan. Empty
  requested maps are recorded; only an entirely empty fit fails. Size-only
  exceptions are automatically reported/recorded. Binding files are still
  required for every requested map, including maps empty in the training split.
- `shared.py`, lines394–431: `objective` loads one map at a time, applies common
  feature definitions/scales and **the same weight vector** to every active
  extent, and pools route terms with weight1/(animal count × that animal's
  route count across all extents). One L2 penalty is applied to the full
  objective. It does not optimize each map separately or average map coefficients.
- [`shared_reward.py`](../../jaguar_irl/core/shared_reward.py), lines17–60:
  exact finite-horizon backward/forward likelihood and gradient. Normalization
  includes feasible alternative paths inside each domain, not just observed
  track cells. The gradient is empirical minus expected feature totals.
- `shared.py`, lines489–551: full-objective backtracking ascent (up to40 rate
  halvings) from zero initial weights, with every candidate evaluation including
  all active maps. Updates are accepted only after complete evaluations.
  Convergence uses gradient norm; iteration exhaustion is a distinct completion
  reason. `--max-updates` limits newly accepted updates in an invocation.
- [`shared_storage.py`](../../jaguar_irl/training/shared_storage.py), lines34–114:
  nonblocking POSIX writer locks; complete hash-addressed generations with
  state/weights; fsync and atomic `current` pointer activation. An interrupted
  partial iteration is repeated, not resumed map-by-map. Inputs/software and
  checkpoints are integrity-checked on resume.
- Training schema is `shared_static_reward/2`; schema1 cumulative-stage runs
  are rejected rather than silently resumed as the joint objective. Binding
  schema remains1; those bindings may be reused for a new schema2 run.

This agrees with the essential architecture in
[ADR0001](../../docs/adr/0001-seasonal-joint-reward.md).

## Verification performed now

Command from repository root:

```bash
/tmp/pantanal-gee-venv/bin/python -m pytest \
  jaguar_irl/training/test_shared.py \
  jaguar_irl/training/test_plan_covariates.py -q
```

**21 passed**, with one expected warning for automatic size-exception admission.
Tests exercise enumeration/gradient agreement; common-weight evaluations over
all maps; animal weighting across maps; binding/export integration; resumed
versus uninterrupted identity; failures during partial map evaluation, weight
write and pointer activation; locking; tamper detection; legacy-run rejection;
training-empty maps; automatic exception safeguards; source-year split isolation;
and observed/unobserved feasible-cell versus unreachable-cell/boundary effects.
The helper behind the test named `test_real_checkpoint_binding_export_training`
uses the real checkpoint/export *format and machinery* with synthetic telemetry
and random synthetic features; it is not a fit to the actual jaguar dataset.

## Persisted runs inspected

The current `analysis/` tree contains four trainer `plan.json` paths found by
recursive inventory. Two are legacy schema1 synthetic demonstrations. The two
schema2 plans are:

- `analysis/shared_reward_joint_verified_20261103/run/plan.json`
- `analysis/shared_reward_joint_verified_20261103/uninterrupted/plan.json`

Both use `synthetic_a`/`synthetic_b` features and three synthetic extents. Their
active checkpoints reach iteration3 with `complete=true` and
`stop_reason=iteration_limit`; this is neither a demonstrated gradient-converged
optimum nor ecological validation. Their local README explicitly labels all
telemetry and features synthetic. The real checkpoint
`analysis/pantanal_seasonal_selection/checkpoints/selection_5bf188474d229bb43e3efde0`
has no `covariates/` binding sidecar as of this audit. No inspected trainer plan
uses its six completed Spring ecological feature caches. This conclusion is
scoped to the inspected workspace, not a claim about every external machine.

## Documentation corrections/clarifications for the parent

1. Components table's raster-preparation row is still an unspecified external
   GIS workflow, despite actual GEE drivers, NPY conversion, recovery ledgers
   and verifiers. Update to the concrete cache/index/binding pipeline.
2. Last-checked date and section1 statements that recipes remain open are stale.
   All six Spring recipes/products are complete; IDs/scales/bindings remain open.
3. Preparation CLI table still says every selected map must have eligible routes;
   code now allows training-empty maps while requiring all requested bindings.
4. Generic TIFF conversion example claims Rasterio unavailable and never tested
   on actual covariates. Actual production conversion has been tested, including
   native GEE retrieval plus local polygon aggregation for population. Keep the
   generic single-band example distinct from the verified recipe-specific tools.
5. Terminology correction refers to legacy filenames containing `bursts`; the
   actual compatibility names contain `bout`/`bouts`. Preserve identifiers while
   using bursts in scientific prose.
6. Cached-product inventory is **not** a representative-year selector, array
   resolver or trainer binding. The existing year planner emits choices and
   identities but does not generate split allocations or automatically populate
   the binding manifest from the shared cache. These remaining handoff steps
   should be explicit rather than implied complete by raster availability.
7. “Every update includes all groups” means active groups with training routes;
   empty maps stay in the pinned inventory and contribute zero objective.
8. A read-only view of weights is not an evaluator. `inference/predictor.py` is
   a legacy interface, not demonstrated support for schema2 per-group bindings.
   Endpoint-conditioned route scoring does not supply unrestricted forecasting.
9. The currently implemented reward is linear in the supplied landscape
   covariates with an eight-neighbour route model. There is no separately learned
   step-length/turn-angle kernel, duration correction or independent movement
   feature module. Those aspects of the thesis hypothesis require explicit
   model/ablation design beyond having a working joint optimizer.

## Scientific and operational limits to retain

Shared static weights do not certify ecological adequacy, identifiability,
missingness robustness or transfer. Routes condition on endpoints and move count,
use all-traversable internal cells/no stay action, and can contain inferred
connecting grid steps. Boundary alternatives influence likelihoods; existing
5km padding is already included. The temporal-static representation across years
is approximate. The configurable time-expanded-state guard is not a calibrated
RAM ceiling. Equal-animal mean whole-route likelihood differs from the older
per-step/window research proposal. The formal evaluation protocol must resolve
its target/metrics before scientific conclusions are drawn.
