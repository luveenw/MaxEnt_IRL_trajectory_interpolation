# Group-semantics audit: current disposition

Updated2026-11-04 after corrections. [Manual](../../jaguar_irl/training/README_SHARED.md)
and [current handoff](pantanal_covariate_generation_handoff.md) are authoritative.

- Group quotas, local-support constraints, singleton protections and group-weighted
  test scoring were withdrawn from the design. Animal34/9 simple random holdout
  is approved; no IDs selected. No ecological model was fitted from the old proposal.
- Fixed: preparation accepts training-empty maps, records active/empty inventories
  and skips inactive maps in the objective. A nonempty overall fit is required.
- Fixed: source-year planning supports separate train/test contexts, skips and
  records maps absent in that split. Cache all candidate year products. Test
  plans do not affect training years or coefficients. Evaluation remains pending.
- Fixed: size-only computational exceptions are warned/recorded and admitted by
  default; invalid routes, proximity violations and runtime limits are not waived.
  Historical export flags/manifests are preserved, including AutumnG324 evidence.
- Retained: spatial candidate ranking, canonical ownership and source deduplication.
  Current seasonal records assert all qualifying bursts preserved; software tests
  check preservation. Use bursts in prose, keeping technical identifiers intact.
- Retained: common coefficients/scaling and an animal-weighted objective; no
  equal-group weighting is applied during fitting.
- Known limitation: map boundaries can truncate feasible alternative paths and
  influence route partition functions/expected features/learned weights. Cells
  unreachable on a fixed-start/fixed-end/fixed-horizon bridge have zero effect.
  Full-map arrays incur computation even where mathematical contribution is zero.
  New numerical checks demonstrate both effects. No padding adequacy or ecological
  validation is claimed. Full-study-defined grids remain fixed context.

Verification:31 targeted shared-training/year-planning/burst tests passed.
Production rasters and immutable historical artifacts were not overwritten.
