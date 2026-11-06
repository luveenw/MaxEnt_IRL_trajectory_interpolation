# Variable-duration seasonal windows: discussion and evidence

Discussion dated 2026-11-01. **Proposals pending user decision.** No processor, thresholds, reports, accepted training contract or split assignments are changed by this note.

## What changes animal coverage?

The seasonal scan already considers all observed starts within the buffered season and retains its best candidate per animal/season occurrence. Keeping more nonoverlapping windows under exactly the same seven-day eligibility rule can increase observations, modeled moves and within-season coverage for represented animals. It cannot create a qualifying seven-day window for an animal that has none. This conclusion concerns temporal eligibility; a new implementation must still preserve spatial feasibility and singleton coverage.

Allowing variable durations changes the eligibility search. A shorter clean period can qualify when a longer period fails, while a longer period can absorb boundary-truncated fragments or alter pooled quality budgets. A maximum duration of 20 days therefore should include an otherwise valid seven-day period if the minimum permitted duration is at most seven days. The density reference and minimum observed-span rule must be evaluated for the candidate's actual duration, not against a 20-day schedule. Four-hour hard cuts and the other protected rules remain explicit.

Observed comparisons from `analysis/pantanal_window_comparison/data/window_coverage_comparison.csv`:

| Duration | Winter | Spring | Summer | Autumn |
|---|---:|---:|---:|---:|
| 7 days | 9 | 15 | 16 | 12 |
| 10 days | 9 | 14 | 16 | 12 |
| 15 days | 9 | 14 | 16 | 12 |
| 20 days | 9 | 14 | 16 | 12 |

The fixed duration is the candidate envelope. Relaxed candidates can already have a shorter observed span: ID 69 has a seven-day-envelope candidate containing 49 retained fixes over approximately 5.4993 observed days. Thus an “up-to” proposal must distinguish a shorter envelope from shorter observation support already present in a relaxed envelope.

The longer runs recover no additional individual-season memberships; ID 19 drops from spring. The union of the tested durations consequently restores the seven-day membership counts. Durations between these values and durations below seven days have **not** been tested. These results do not establish monotonic eligibility or show that an exhaustive 7–20-day search could never admit another animal.

## Literature-supported principles

[Fieberg et al. (2010), §§2–3 and 4b](https://pmc.ncbi.nlm.nih.gov/articles/PMC2894958/) treats animals as the population-level sampling units, discusses variable sampling intensity/duration and nonrepresentative telemetry samples, and warns that excluding briefly monitored animals can reduce population representativeness when monitoring duration relates to animal type. Its two-stage and mixed-model discussion distinguishes animal-level uncertainty from telemetry volume. Missing fixes can depend on habitat, so choosing the cleanest observation periods can affect inference. These principles support an effort-aware analysis; they do not validate this project's numerical window, loss or weighting thresholds.

[Muff, Signer and Fieberg (2020)](https://doi.org/10.1111/1365-2656.13087) demonstrates random-coefficient habitat-selection models using mountain-goat and otter data and simulations. Individual-specific slopes model heterogeneity and borrow information across animals. This provides precedent for addressing real inter-individual differences instead of assuming that equal sample counts remove them. Its RSF/SSF implementation is not a ready-made hierarchical MaxEnt IRL model.

[Hofmann, Cozzi and Fieberg (2024)](https://doi.org/10.1186/s40462-024-00476-8) defines steps, step duration and bursts separately. Its simulations and hyena example investigate retaining irregularly timed steps with model-specific adjustments. This distinguishes changing the time between observations from changing the total length of a recording period. A variable-length window can retain the same nominal two-hour sampling scale; longer total records alone do not introduce a new step interval. Their results do not establish that this project's tolerated 2.5–4-hour steps are equivalent to exact two-hour observations.

## Ecological interpretation and remaining choices

A common 500-m grid and nominal two-hour sampling treatment preserve the declared spatial/observational comparison scale across window lengths. Different individuals can still be observed in different habitats, hydrological phases, behavioral states and years. Seven calendar days is an operational design choice; no source reviewed here establishes it as a biological minimum for jaguar fine-scale route learning. Equal seven-day durations do not establish ecological equivalence either.

The key issue for a season-level reward is which within-season situations are represented. Several nonoverlapping periods dispersed through a season could expose more environmental/behavioral variation than one particularly clean period. This is an inference about the design, not a demonstrated performance benefit. More periods from one animal increase evidence, not the number of independent animals. Keep the original animal in one fold across every window and representation; preserve the geographic-transfer assessment separately.

An unrestricted “any positive duration up to 20 days” rule would allow very short clean islands to satisfy a percentage screen. Five regular observations can be only about eight hours apart from first to last; that fragment floor does not establish a representative seasonal contribution. Such cases may contain usable route information, but assigning them a full equal-animal influence deserves explicit sensitivity analysis. A lower duration or minimum informative-evidence rule is unavoidable unless the inferential target explicitly includes these cases. Its value should be justified with data diagnostics and validation, not labeled biologically mandated.

## Weighting proposal for discussion

The current research contract gives each animal equal total weight and each of its accepted windows equal weight after normalizing by contributing model moves. With variable-duration windows, equal-window weighting makes a short episode as influential as a long episode within the same animal. It can also change assigned weight merely because equivalent accepted evidence was packaged into more windows.

A simpler alternative for an **average represented-animal, per-modeled-move** target is

`J(theta) = (1/N) sum_i [sum_s log P_theta(tau_is | context_is) / sum_s L_is] - lambda R(theta)`.

Here s ranges over all unique informative segments across the animal's included windows, and L is spatial-move count. Each segment's empirical and expected feature totals receive the same animal coefficient `1/(N * sum_s L_is)`. This removes an extra equal-window normalization; accepted windows remain provenance and scheduling units. It is an explicit project proposal, not a formula prescribed by the cited ecology papers, and does not change the accepted contract until approved.

The coefficient assignment is insensitive to how unchanged segments are assigned to windows. **Splitting a route itself can still change its endpoint/horizon-conditioned likelihood**, so this is not a guarantee of model invariance to arbitrary segmentation. Raw grid-move count also includes inferred edges and is not effective independent sample size. Inspect inference burden and route information separately. A spatial route model that compresses residence cannot acquire a time-use interpretation just by multiplying by calendar duration.

Equal-animal weighting prevents long-monitored animals from dominating solely through more modeled moves. It does not reconstruct unobserved seasons, fix nonrandom missingness or make short records as informative as long ones. Precision weighting would deliberately favor better-estimated animals; hierarchical modeling is another way to balance uncertainty and heterogeneity. Neither is automatically superior for the user's target. Choose the target before choosing the weights.

## A restrained next experiment

1. Preserve the seven-day result as the reference cohort.
2. Audit excluded animals' available clean bouts and candidate durations to determine whether shorter windows would recover meaningful new evidence. Report which rule changes each animal's status and how many informative routes/moves remain after export.
3. Compare retaining multiple nonoverlapping seven-day windows with a prespecified bounded-duration alternative. Include the seven-day candidates unchanged in that candidate set, so selection cannot accidentally discard baseline eligibility. Any reduction through map/rank choices must be diagnosed separately.
4. Deduplicate source observations/edges and choose one map owner for overlapping evidence. Decide deterministic overlap resolution without model-test outcomes; do not concatenate all overlapping candidate windows.
5. Track new animals separately from added observations for existing animals, calendar-phase coverage, sex/site representation, inferred-edge burden, fragment lengths and exporter exclusions.
6. Evaluate a small declared weighting sensitivity with shared original-animal folds and common held-out cases, plus full-cohort coverage. Avoid tuning a growing family of duration/weighting choices against the final test results.

These steps aim to expose which choices matter. They do not promise coverage of all 56 animals, a complete seasonal behavioral distribution, or improved prediction from more data.
