# Primary evidence for a jaguar missingness experiment

Research checked 2026-11-02. Literature evidence and proposed diagnostics only; no data analysis or pipeline changes were performed.

## What Hofmann, Cozzi and Fieberg (2024) actually tested

All entries below refer to the [primary article](https://pmc.ncbi.nlm.nih.gov/articles/PMC11081933/), with section locators.

| Topic | Evidence |
| --- | --- |
| Simulation | 300 trajectories, 1,000 nominal-duration steps each; fixed gamma/von-Mises movement parameters and habitat coefficients. Randomly delete 0–50% of fixes in 10% increments; 100 rarefactions per trajectory. (“Movement simulation”, “Data rarefication”) |
| Assumptions | Missing fixes independent of habitat/time; unchanging movement kernel. These are simulation assumptions, not established properties of wildlife data. (“Discussion”) |
| Duration | Dynamic+Model fits duration-specific proposals and interactions of duration with `sl`, `log(sl)`, `cos(ta)`. Longer-duration classes require ≥5 steps for numerical stability. (“Step-selection functions”) |
| Predecessor | Turning angles depend on both adjacent durations; omitted predecessor duration probably explains remaining concentration bias. Continuous-duration, low-complexity effects are suggested. (“Discussion”) |
| Empirical illustration | One hyena, Apollo: 9,316 fixes, 2007–2011, <10% original missingness; retain nighttime two-hour bursts, remove noon observations, randomly delete 25%. Additional 10% thinning helps fit two-/four-/six-hour proposals. (“Case study”) |
| Limits | No power-derived minimum animal count or universal dense-track eligibility rule is specified. The five-step rule concerns duration classes, not animals or fragments. |

The [author-code DOI](https://doi.org/10.13020/6wcd-6s43) did not resolve through available retrieval tools. Scripts were **not inspected**; implementation details above come from the article.

## Jaguar evidence that changes interpretation

| Issue | Primary evidence | Implication for this project (inference) |
| --- | --- | --- |
| Database provenance | Morato et al.'s [Dryad record](https://datadryad.org/dataset/doi:10.5061/dryad.2dh0223) reports 134,690 locations from 117 jaguars, 54 males and 63 females, across five countries. The archive includes animal/collar metadata and location data. The [author repository](https://github.com/ICMBio-CENAP/jaguar_movement) identifies the 1999–2016 collection period. | An animal count in the archive is not a count eligible for one temporal resolution, season, or model. Preserve individual, deployment, site, sex and date metadata. |
| Prior filtering | The authors' [ICMBio-published database metadata](https://www.gbif.org/dataset/06e98c3e-2801-4d29-8e81-943a13bb3785), Methodology, reports filtering to 3D fixes and DOP <10 where those fields existed. This is a later publication of the database metadata, not a new analysis of the local file. | A timestamp gap may reflect unsuccessful acquisition, transfer loss, or quality exclusion. Do not label all gaps as random collar failures. |
| Diel and monthly variation | [Garcia Fontes et al. (2021)](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0246233), Results and Discussion, analyzed nine Taiamã jaguars from this database. Their trajectory-derived states showed more foraging around midnight–08:00 and more resting early in the year; they associated the latter period with heat and flooding. These are inferred states, not direct observations of every behavior. | Assess local-hour and seasonal movement patterns. A nighttime-only hyena design is not a jaguar default. |
| Seasonal space use | [Cavalcanti and Gese (2009)](https://digitalcommons.unl.edu/icwdm_usdanwrc/880/) tracked ten southern Pantanal jaguars. Dry-season ranges were generally larger, and range stability/site fidelity differed among individuals and seasons. | A dense segment can still straddle a behavioral or spatial change. Assess stability at the intended fitting scale. |
| Habitat and behavior | [Gese et al. (2018)](https://esajournals.onlinelibrary.wiley.com/doi/10.1002/ecs2.2341) modeled ten Pantanal jaguars by sex, wet/dry season and movement/predation state. Dense cover or proximity to cover, and water proximity, repeatedly mattered. | Examine habitat-associated movement and observation availability; density selection could alter represented habitats. This paper does not estimate local GPS missingness bias. |
| Fix reliability | [de la Torre and Rivero (2019), p. 222](https://r.jordan.im/download/conservation/torre2019.pdf) report poor fix success for five Mexican forest jaguars, tentatively attributing it to closed canopy; some records were also limited by collar recovery/transmission. [Hofman et al. (2019)](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0216223), “Unit performance”, explicitly separates acquisition, transfer and overall success. | Random deletion measures one controlled observation mechanism. Add clustered-dropout sensitivity tests and assess actual acquisition schedules where metadata permit. |
| Residency | [Morato et al. (2016)](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0168176), Methods and Results, used variogram asymptotes: 33 residents, eight non-residents, three records too short to classify. One non-resident was monitored for 591 days. | Long or densely sampled does not imply resident. Residency is relevant to a resident/home-range target, not a universal prerequisite for local movement inference. |

## Proposed selection logic, not author-prescribed thresholds

Choose reference segments by observation support at the **target interval**, not total fixes alone. Require enough known, sequential reference locations to construct each planned mask and score withheld coordinates. Keep actual timestamps; distinguish scheduled gaps from additional deletion; exclude deployment changes and invalid coordinates. Record eligible steps, defined turns, duration-class support, original completeness, largest gaps and usable span per animal and segment. A dense reference remains sampled GPS evidence, not continuous-path truth.

Assess biological consistency separately from completeness: local-hour, seasonal and habitat patterns; movement-state changes; and residency where relevant. A stationary/time-homogeneous **conditional** movement model can still react to changing location or covariates; it does not mean constant speed or no spatial structure. If effects change over time, model/stratify them or bound the inference to a more consistent period. Do not require a non-significant diagnostic as proof of homogeneity.

Prespecify the cohort and animal-level development/evaluation split before masking. Repeated masks quantify sensitivity to observation removal on those same animals; they do not create new biological replicates. Evaluate enough animals to cover the intended target population and quantify between-animal variation, rather than borrowing a universal count from the simulation. Report both reference-cohort performance and its selection/coverage limitations. Select numerical cutoffs using development data and stability/precision checks, keeping the evaluation set fixed.
