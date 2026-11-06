# Reusable methodology: animal-level seasonal holdout and computational maps

Updated 2026-11-04 following the user's clarification. This supersedes earlier group-stratified proposals. The approximately 80/20 Spring count (34 train / 9 test from 43 animals) remains accepted; group quotas and singleton protections are withdrawn. No animal identities have been drawn. Evaluation and fold-aware prediction remain unimplemented.

## Reusable methodology text

We partition eligible animals within each season using simple random sampling without replacement, targeting approximately 80% training and 20% testing. Spring has 34 training and nine test animals. All observations, years, bursts and trajectory variants of an original animal inherit its assignment within that season. We use a prespecified recorded seed, stable ID ordering and a versioned allocation; identities are not selected using model performance. The 80/20 target is a practical training/assessment compromise rather than a theoretically optimal ratio.

Whole-animal separation matches the primary objective: evaluating whether a model fitted to some animals predicts or interpolates movement of other animals. Repeated relocations share individual behavior and exposure, so randomly partitioning steps does not provide the same test of new-animal generalization (Fieberg et al., 2010; Roberts et al., 2017; Northrup et al., 2022). Prediction and interpolation will have separately specified conditioning information and missingness designs.

Spatial map groups collect nearby MCP95 domains for computational tractability. They do not represent biological populations, statistical strata or mandatory training-support units, and have no influence on animal allocation or fold formation. Animals from singleton groups are eligible for either partition. A domain may have no training animal; that domain then contributes no training trajectories, while the shared fitted policy can be evaluated there using its required environmental inputs. We do not redraw the split to improve local support. Novel or shared landscape exposure can be reported diagnostically, but it is not an allocation constraint. Existing domains were constructed from full-study telemetry, so the experiment is conditional on those domains rather than a prospective test of blind domain construction.

Separate allocations are used for independently fitted seasonal models because membership and the fitting targets differ by season; a common cross-season animal lock is not required by this isolation design. Each fitted seasonal pipeline excludes its own held-out animals from fitting, learned preprocessing and model selection. Parameters or test-informed tuning decisions must not be transferred between seasonal pipelines in ways that defeat that separation. An animal used in a different seasonal model does not thereby contaminate the focal model's test. Seasonal performance estimates can nevertheless be dependent because animals recur. Neither seasonal partitioning nor recurrence establishes temporal transferability; that requires a distinct train-time/test-time experiment.

Proposed reporting first summarizes performance for each test animal and averages those animal scores for the primary animal-level summary. All 43 animals have equal test inclusion probability, 9/43, under this simple random design; the former group-quota weighting and exclusion of singleton domains no longer apply. Individual and environmental-support diagnostics remain useful. Nine test animals limit precision, regardless of the number of recorded steps. Exact metrics, uncertainty estimation, interpolation masks and tuning folds remain subject to review. Animal-blocked internal tuning, if used, must exclude the outer test animals (Cawley and Talbot, 2010).

## What the thesis experiment can establish

Successful held-out prediction supports generalization to other sampled animals under the stated observation/landscape conditions. It does not alone show that movement contributes predictive information beyond landscape covariates. A proposed paired ablation compares a landscape-only model, a movement-only model and a combined model on identical animal splits, observation anchors, gap masks, data support and scoring, with comparable tuning effort. Improvement of the combined model over the landscape-only model would support incremental predictive information from the movement representation. A movement-only baseline helps interpret that improvement. Predictive improvement does not prove causal or statistical independence between movement and landscape; claims should match the tested conditional contribution. These comparisons are design proposals, not implemented models or results.

## Allocation feasibility and temporal transfer

A shared global assignment can, for some seasonal membership patterns, conflict with exact seasonal test quotas or minimum-size requirements. For example, overlapping subsets can impose incompatible count constraints; proving infeasibility requires the actual membership matrix and explicit constraints. Even when feasible, exact balance or precision may be poor. We have not demonstrated either mathematical infeasibility or statistical invalidity for our dataset. Removing local group-support constraints removes one previously asserted source of conflict. The direct justification for separate allocations is isolated seasonal fitting and the within-season generalization target, not an unverified impossibility claim.

No temporal-transfer experiment is needed merely to justify independently fitted seasonal models. Such an experiment is optional if the thesis asks whether a learned policy transfers between seasons or years; model transfer, animal identity, time ordering and available covariates would then need explicit control.

## Covariate acquisition and unresolved source-year policy

Cache fixed, versioned external products for all candidate grid/season-years; Spring currently has 24 combinations. Acquisition need not wait for animal allocation. The binding and any learned preprocessing used by each fit must be reproducible and respect its declared validation boundary.

The implemented planner ranks years by animals, then animal-days, then earliest
year separately for `--split train` and `--split test`. It skips maps without
evidence in the requested split and records those omissions. Use training-only
plans for fitting and separate test-context plans for testing; test plans do not
change training inputs, coefficients or learned scaling. Known date/context
metadata is distinct from selecting source years based on prediction performance.
The evaluator must support separate bindings with the same learned weights;
that interface remains unimplemented. An all-empty split still raises an error.

Size-only computational map-budget exceptions are automatically admitted and
called out in warnings/manifests. Other validity and runtime limits remain.
Qualifying bursts must be retained. Each route's likelihood includes alternative
fixed-start/fixed-goal/fixed-move-count paths within the map, not just observed
cells. Unreachable cells have zero contribution; boundaries truncating feasible
alternatives can change gradients/weights. Boundary sensitivity is a known
limitation with no scientific validation yet.

## References and historical record

- Fieberg et al. (2010): https://pmc.ncbi.nlm.nih.gov/articles/PMC2894958/
- Roberts et al. (2017): https://doi.org/10.1111/ecog.02881
- Northrup et al. (2022): https://doi.org/10.1002/eap.2470
- Cawley and Talbot (2010): https://www.jmlr.org/papers/v11/cawley10a.html
- [Earlier literature review](train_test_split_literature_review_20261104.md): general blocking rationale remains useful; group quotas, training-only singleton policy and unequal-probability weighting are superseded.
- [Historical quota audit](../../analysis/pantanal_covariates/plans/spring_split_quota_review_20261104.json): retained as evidence about a rejected allocation design, not the operative split.
