# Current handoff: seasonal Pantanal covariates and animal holdout

Updated 2026-11-04. This replaces superseded conversational/design notes. The
[maintained manual](../../jaguar_irl/training/README_SHARED.md) describes current
code and contracts. Prediction/evaluation remains unimplemented.

## All six Spring covariates complete2026-11-04

Tree classes3+4:24NPYs+24eight-bandTIFFs,100402cells under
`data/pantanal_covariates/spring_mapbiomas_wooded_cover_v1`; all295priorfiles
preserved, Drivechecksums and source/repair/cross-feature QA passed.

Population GlobPOP+approved same-yearLandScan fallback:24NPYs+24four-bandTIFFs,
100402cells under `data/pantanal_covariates/spring_globpop_density_v1`. Actual
zero-count source replacements are limited to412nativepixel-years in five cases;
finiteGlobPOP valuesareunchanged.1,745targetcell-years touchfallbackareas;
763mixedcells canremainpositive. RawNaNs preserved; sourceguard/hash/coverage/
physicaloverlap QA passed. All404priorfilesunchanged;24Drivecopieschecksumverified.
Five numerical/sourceguard tests passed. Densitypeople/km² has noextra smoothing
orlogs. NativeGEEretrieval is followedbylocalphysicalpolygon-overlap integration
ontoexactpadded500m grids. No genericzero-fill or interpolation. Physicalfallback
area334654086.700854m² versusprojected334408887.992064m² acrosscachedyears.
PublishednativeGEEauditscript underseasonal_covariates/pantanal_spring_globpop_density_v1;
commitb8af9eb3876626a2f6adc94baa539f36c5c68013. DriveleafID
1YvVeDG0UkbJe48a75wQ6SL49BOprNy47. Seeverification/acquisition/manifest/README.

Combined six-feature cache index:
`data/pantanal_covariates/spring_covariate_cache_inventory_v1.json`:
24candidatepairs,13grids,144feature references,133uniqueNPYs (120annual+13static
roughness),2,220,444bytes ofNPYs excludingTIFF/source/QA. Verifiedby
`gee/verify_spring_covariate_cache.py`. Assetsare shared acrosssplits; thisindex
is not a trainingbinding. Animal IDs are now frozen as recorded below; candidate input profiles are
prepared. No reward coefficients have been fitted and no formal evaluation
has been performed. Ecological accuracy and sourceestimatedzeros arenotgroundtruth.

GlobPOPsource gaps werecheckedagainstofficialZenodo11179644 and othercomponents.
LandScan same-year0 is corroboratedbymodernGHSL:allmissingfootprintszero,including
G0572010and2015. OlderGHSL tinyfractionalestimates documented. GHSLsharescensus
ancestryanddoesnotproveabsence. UserapprovedLandScanfallback;no policydecision
remains pending forSpring. HistoricalDO_NOT_USE patchesremain diagnosticrecords;
productionuses actualrawsourceandimmutableapprovalcopy.

Read-onlyGEEJSinspector:
`gee/globpop_gap_inspector_20261104/inspect_globpop_gaps.js`, published in
users/luveenw/ColumbiaMAThesis:seasonal_covariates/globpop_gap_inspector_20261104/inspect_globpop_gaps.
LayersincludeoriginalNaNfootprints,500mcells,GlobPOP,LandScan,WorldPop,GPWandboth
GHSLreleases;itneverfillsorexportsproducts.

## Scientific design

Map groups collect nearby animal MCP95 domains for computational tractability.
They are not biological units or split strata. Spring has 43 eligible animals;
use 34 train / 9 test, sampled uniformly by original animal ID with a recorded
seed, without group quotas, singleton protections or geographic redraws. No IDs
have been drawn. All years, bursts and variants inherit an animal's seasonal
role. Separate allocations are approved for independently fitted seasonal models.
No claim of global allocation infeasibility or temporal transfer is established.

The thesis asks whether movement representations add predictive information to
landscape covariates. Proposed paired landscape-only, movement-only and combined
comparisons must share animals, observation anchors, gap masks and scoring.
They are not implemented results. Full-study telemetry defines current domains;
new-animal evaluation is conditional on those domains, not blind map construction.
[Reusable methodology](seasonal_holdout_methodology_20261104.md).

## Corrections implemented 2026-11-04

- Training accepts maps without training routes, records active/empty maps and
  skips empty maps in the objective. An entirely empty training set still fails.
- Size-only map-budget exceptions are accepted by default, warned and recorded
  with route admission provenance. Spatial/proximity violations, invalid routes
  and runtime memory limits are not waived. The API addresses computational map
  IDs, not individual-ID flags; route manifests preserve original animal IDs.
- Source-year planning supports train/test separately and skips maps without
  evidence in that split. Pre-cache every applicable candidate year; select
  reproducible fit/test-context bindings later. Test context years do not change
  fitted weights or training years. Final evaluator support for separate bindings
  still needs implementation. Existing source-year ranking uses animals, then
  animal-days, then earliest year, and never discards routes in losing years.
- Qualifying bursts are preserved; Bout/bout remains only in historical technical
  identifiers and legacy artifact names where renaming would break provenance.
- Former split quotas/local-support requirements are withdrawn; do not resurrect
  them from prior research notes or the historical quota enumeration artifact.

## Likelihood scope and limitation

The static core conditions on observed start, endpoint and number of grid moves.
It normalizes the observed path against all feasible alternative paths on its
map with those conditions. Backward values generate conditional next-move
probabilities; forward occupancy gives expected feature totals. Unobserved cells
on feasible alternative paths can affect gradients and weights. Cells unreachable
on any such bridge have no mathematical contribution, although the full grid is
allocated in memory. Boundaries can remove alternatives and affect results;
the selected5km ecological padding is verified in assets and stands as the
current choice; no extra boundary experiment is imposed. There is no
completed held-out evaluation or free-ended forecast interface.

## Covariate status and recipes

All six features have completed Spring products on exact 500 m EPSG:32721
grids. Executable scripts belong in `gee/`; data/provenance in
`data/pantanal_covariates/`. Cloud project is `perceptive-ivy-780`; EE script repo
is `users/luveenw/ColumbiaMAThesis`. Drive parent path is
`columbia_ma_thesis/jaguar_irl/seasonal_covariates`.

- Roughness: SRTM ~30 m, fixed 30 m metric working grid, local 3x3 population
  elevation variance (90 m width, m²), then overlap-weighted mean into 500 m.
  Static elevation epoch. Products: `spring_srtm_roughness_v1` (13 maps).
- Natural grassland: MapBiomas class12, excluding managed pasture; Bolivia's
  grass/shrub mixture accepted. Narrow flooded habitats: class11, excluding
  open water and separately mapped flooded woody vegetation. Native membership
  fractions overlap-averaged into 500 m, no additional smoothing. Products:
  `spring_mapbiomas_landcover_v1` (24 candidate pairs).
- Shrubland: ESA CCI classes120/121/122, native ~300 m membership fractions,
  overlap-averaged into 500 m. Products: `spring_esa_shrubland_v1` (24 pairs).
- Forest/savanna proxy: MapBiomas classes3+4 only, excluding6/7; fraction of
  classified area, not measured canopy closure or a height threshold. Same
  area-fraction treatment. Production complete as above. Revisit the source
  outside MapBiomas coverage. Hansen preparation is superseded and unexecuted.
- Human population: GlobPOP published density plus approved same-year LandScan
  zero fallback only at audited gaps. Native30arcseconds (~1km); physical-area
  overlap mean onto500m. Products: `spring_globpop_density_v1` (24pairs). Original
  source/masks/NaNs retained; actual fallback counts guarded, observed/fallback/
  coverage fractions supplied. Annual source timestamps areJan1, so select
  calendar year explicitly and apply throughSpring. OfficialZenodo11179644
  locally agrees withGEE. Denominator/census accuracy are caveats, not claims
  of population conservation. No missing area is silentlyrenormalized away.
  Reportedfusionchangesfrom2016needreview beforelaterseasonextension.
  [Source review](globpop_production_questions_20261104.md),
  [fallback corroboration](globpop_ghsl_landscan_comparison_20261104.md).

Annual maps approximate Spring Aug15–Nov14 inclusive, not sub-season observations.
Spring caches have24 group/year pairs; do not average them. Training/test plans
may pick different cached annual contexts. Summer crosses calendar years and its
source convention remains unresolved. Future scale-sensitivity work must compare
movement-scale covariates rather than assume habitat-selection optimal scales.

## Source coverage and repairs to preserve

Keep Brazil→Paraguay→Bolivia MapBiomas priority, Chaco26 water fallback only for
known G115 gaps. Chaco alone/Brazil+Chaco lacks substantial model coverage; no
replacement of completed national products is warranted. G316/2011 has one
missing native pixel, repaired by approved live Brazil2010/2012 class4 consensus,
with actual adjacent-year retrieval in GEE code and observed/imputed QA. This
contributes zero grassland/flooded habitat and one to forest/savanna membership.
Do not overwrite original failed artifacts or historical manifests.
[Chaco audit](mapbiomas_chaco_collection_review_20261103.md).

Existing selection checkpoint:
`analysis/pantanal_seasonal_selection/checkpoints/selection_5bf188474d229bb43e3efde0`.
Land-cover inventory:
`data/pantanal_covariates/spring_landcover_inventory_v1.json`.
The four collection records assert all qualifying bursts preserved. Autumn G324
adds six admissible routes/one animal under the map-size exception (174/23 versus
168/22); do not reject it for computational map size by default.

## Clarifications verified2026-11-04

Cached rasters are split-independent and shareable. The year planner reads
already labelled trajectories and writes year-selection metadata, not animal
splits or a cache registry/binding. Its availability field is not_checked.
Multiple plans can reuse the identical product/file/hash. A resolver and evaluator
are separate work; do not create train/test-owned copies of external products.

5km padding is present in saved grids and generated products. All324 candidate
map selected-fix margins exceed5km;48 land-cover and13 SRTM TIFF bounds and72
array shapes match saved padded grids. No regeneration needed for padding.
`analysis/pantanal_covariates/padding_verification_20261104.json` records checks.
The ecological padding choice stands; no new boundary audit is required here.

The10million time-expanded-state guard is a configurable, uncalibrated default,
not a hardware memory limit. Main float64 backward values use80MB at that count,
plus other arrays. Set a justified larger runtime budget for fitting rather than
rejecting otherwise admissible routes. No host-specific cap was selected here.

## Next work

Use the frozen animal allocation and candidate input profiles recorded below;
retain the completed six-feature candidate caches; create split-specific epoch
plans and bindings. Review evaluator, metrics,
conditioning information, missingness masks, inner-fold preprocessing and
uncertainty before claiming held-out results. No ecological fit, final test or
prediction is completed. Preserve existing products and provenance.

## Operating manual refresh and trainer audit2026-11-04

README_SHARED section2 now shows raster preparation and shared cache/year-plan/
manual-binding dataflow with concrete entry points. Section7 opens with a full
raster operating walkthrough: productionNPYlocations/counts, offline validation,
pinned inputs, cloud resume/repair rules, native-versus500m processing, QA and
manual epoch-to-binding steps. All five recipe verifiers and combined133NPY
inventory passed again. Older stale recipes-open/Rasterio-unavailable/test-only-
groups-fail instructions were removed; baseMapBiomasdriver is not the correct
registered-repair resume path.

Shared-reward multi-extent fitting is implemented/tested (21currenttrainer/
planner tests pass), with common coefficients, animal weighting, exact path
normalization, joint backtracking updates and atomic checkpoints/recovery.
Only synthetic current training demonstrations exist in the inspectedanalysis
runs; their iteration3completion is iteration-limit, not gradientconvergence.
The actualPantanal checkpoint has no covariatebinding sidecar or six-feature fit.
No formal heldout evaluator or separate movement-feature/kernel model exists.
See[trainer audit](shared_training_implementation_audit_20261104.md); no new
allocation,binding,ecologicalfit or evaluation was performed during this audit.

## Spring allocation and input profiles2026-11-04

Currentcode nowincludes`jaguar_irl.training.animal_splits` and`cache_bindings`.
Splitfrozen34/9seed20261104,no groupconstraints orredraw. TestIDs32,41,74,81,84,
108,109,111,117; trainingother34eligible;54unassigneddiagnostic(fiveresidence-only
bursts,noadmissibleroutes). Allocation+metadata+exportreceipt+verification under
`analysis/pantanal_splits/spring_whole_animal_v1`. All3086numericarrays unchanged;
534eligibletrainroutes/149test,all3692manifestrows retained. Originalunsplitexport
pointerisnotchanged;usenewreceipt. Train/testyearplans andfourcandidateprofiles
(rawunits/zscore×train/test) under`data/pantanal_covariates/bindings/spring_whole_animal_v1`.
PreparationJSONrecordsselected_scaling=null,selected_regularization=0;
no optimizer preparation/fit. Trainuses13maps,test5active; G057train2014/test2015,
G225train2013/test2012. Profilesuseexistingarrays,not split-ownedcopies.

Userrequestedconceptualbinding/connector/L2andHirakawapreprocessingreviewbefore
choosing transforms. Bindingisoursmanifest/provenance layer; originalauthorcode
loadsastackdirectly. HirakawaAppendixS2p1uses[−1,0]features; nopublishedL2term
ortrain-onlyzscore. Author`lam=.01`islearningrate. Our`--l2 .01`isoptionaladded
modelchoice,notpaperdefault orselectedsetting. One-SDzscorehasgeneralecological
regressionliterature,butexactequal-animaldeparture-stateweighting(including
inferredconnectors)isoursproposal,notestablishedIRLrecipe. Sourceaudit:
[Hirakawa review](hirakawa_feature_scaling_regularization_review_20261104.md).
Newcode27targetedtests passed. MainmanualupdatedCLI/inputprofilecontracts.


## Baseline decision and bounded scaling discussion — 2026-11-04

User selected an unregularized baseline (`--l2 0`). L2 and z-score scaling
are potential adjustments for later runs, not baseline requirements. Scaling
remains unresolved; no optimizer preparation or fit has started. A proposed
Hirakawa-inspired increasing affine transform is `f-1` for the four cover
fractions, and `x/U-1` for roughness and population density, with positive
feature-specific bounds U shared across maps. This is our proposed mapping,
not a recovered exact Hirakawa GIS formula. Fit any empirical U using complete
selected training maps only, freeze for test, and do not clip out-of-range test
values. Training-only bounds cannot guarantee future values remain in [-1,0].
Signed coefficients retain preference/avoidance under this mapping. No new
scaling profile or bounds have been selected or produced.


## Frozen Hirakawa-style baseline scaling — 2026-11-04

User selected the increasing affine recipe and zero L2. Full 13 selected training
map maxima, including padding: roughness U=513.5153198242188 m² (G316/2011);
population U=158.58111572265625 people/km² (G078/2013). Cover fractions U=1.
Use `(x-U)/U` for train/test, no clipping. Source-array hashes and full-map ranges
are frozen under `data/pantanal_covariates/bindings/spring_whole_animal_v1/`
`hirakawa_bounds/scaling.json`; train/test profile bindings exist alongside it.
`preparation.json` now selects `hirakawa_bounds`, regularization=0; no optimizer
preparation or fitting has started. `cache_bindings fit-bounds` reproduces bounds
from a train plan and rejects test fitting. Five cache-binding tests passed,
including an unvisited-cell maximum and identical train/test parameters.
Earlier statements that scaling is unresolved are superseded by this decision.


## Final current scaling policy — hull maxima, 2026-11-04

Supersedes the training-map-only profile: selected `hirakawa_hull_bounds/scaling.json`
under the existing Spring binding directory. Uroughness=631.602294921875 m²;
Upopulation=7018.03466796875 people/km²; cover fractions U=1. Same `(x-U)/U`
for train/test, no clipping, zero L2. Hull includes all 13 padded Spring extents
and intervening landscape (76280 km²). Population uses selected training years
only: 2005,2008,2009,2010,2011,2013,2014,2015. No hull raster was cached.
Population native maxima are attained by complete 500m cells; a 2km boundary
halo check found no larger values. Roughness valid fraction is 1 throughout
the reduction domain. Metadata/witnesses at `data/pantanal_covariates/`
`spring_hull_scaling_v1`; query/freeze scripts at `gee/spring_hull_scaling_v1`.

User requires this as a final before-training step: first determine **all** group
extents for a season and finish their covariate extraction, then construct their
hull, query model-scale maxima, and freeze profiles. Recompute in a new version
when extents, recipes, grids or selected training years change. Current README
contains background, commands, artifacts, stopping conditions and reuse rules.
Previous immutable profiles remain historical; `preparation.json` selects the
new one. No optimizer preparation or fitting has started.


## Static feature representation versus time stacks — 2026-11-04

Hirakawa's make_3d_feature_map.py explicitly copies [F,H,W] into [F,H,W,610].
Our shared trainer instead loads [6,H,W] per extent and reuses the same reward
at every route step. Dynamic-programming values have [L,H,W] for each retained
burst separately: L exported states, L-1 transitions, no terminal reward.
Training routes currently have L=3..188; no 610 default or per-animal/extent
common stack is needed. This preserves static feature replication, not original
physical-time semantics: k is grid moves after collapse/connectors, not elapsed
two-hour observations. README_SHARED Array requirements now explains exact code
locations, shapes, and the known limitation. No algorithm change was made.


## First Spring training launch — 2026-11-04

User authorized immutable plan preparation, live progress logging, a short pilot,
and subsequent full training if pilot checks pass. Implemented JSONL/live snapshot
telemetry in shared.py; 29 targeted tests pass, including numerical resume
equality and progress lifecycle. Frozen plan at `analysis/pantanal_training/`
`spring_whole_animal_hirakawa_hull_unregularized_v1/plan.json`: 34 animals,
534 routes, 13 maps, selected hull scaling, zero L2, signed zero-initialized
weights, equal-animal mean whole-route likelihood, 50-update cap, learning
rate .1, tolerance 1e-6. Pilot invocation uses --max-updates 2 and redirects
to pilot.console.log; continuation must reuse this plan/current checkpoint.
No changes to shared.py/core/storage may be made during the run because software
hashes are pinned. Live progress.json and append-only progress.jsonl are
non-authoritative; current/state.json and weights.npy are authoritative.
No evaluation/prediction implementation or scientific validation added.


## Pilot passed and full continuation launched — 2026-11-04

Supersedes all earlier "not started" status statements. Plan SHA256
8b4c5ec04521443990398ba3541ff11f52bf0e63487b7a9c3e6e7199588397b7.
Pilot completed two updates in 21.33s, process peak RSS52.14MiB. Objectives
−26.0819143→−26.0757661→−26.0729671; update2 gradientnorm .1241396. All
three evaluations included534routes. Pilot verification and immutablecheckpoint
checks passed; this is software/runtime evidence, not ecological validation.
Full baseline continuation launched from iteration2, same immutableplan, cap50
or earlier gradient convergence. See run progress.json/progress.jsonl and
training.console.log for live status; do not infer completion from this launch
record. Test animals remain excluded. No need to rerun extraction or split.


## Baseline completion and terminal monitoring — 2026-11-04

Baseline reached update50: objective−26.07027638521933, gradientnorm
0.0030871249929154882; stop_reason=iteration_limit, not tolerance convergence.
Full continuation elapsed312.0s plus21.3s pilot. Immutable final checkpoint
integrity checked. No test evaluation. Shared manual now includes standalone
absolute-path tail command for readable training.console.log, JSON snapshot
and checkpoint inspection; tail can wait after completion, Ctrl+C only exitsviewer.


## Default convergence and uncapped continuation launched — 2026-11-04

User explicitly requires convergence-only stopping by default. prepare now
defaults iterations=None (JSONnull); CLI --iterations is an optional explicitcap.
New `shared continue --from-run OLD --run NEW` preserves old plan/checkpoints
and seeds a new immutable plan/current from original weights+fullhistory.
Core/storage hashes must match; wrapper migration reevaluates/checks objective
and gradient. Parent plan/state/weights hashes pinned. 31 targeted tests pass
including default uncapped preparation, continuation/source preservation,
interrupted publication recovery, and changed-core rejection.

Uncapped real continuation launched at `analysis/pantanal_training/`
`spring_whole_animal_hirakawa_hull_unregularized_convergence_v1` from update50.
No data, scaling, weighting, learning rate, tolerance or L2 changes. Same
1e-6 gradient tolerance; no iteration cap. Objective/gradient recheck passed
and seedweights/history exactly match old update50. Live progress and console
log are now in the new directory. Original50-update run is historical.
No claim convergence is guaranteed; failure/interruption remain possible.
Do not edit pinned code during live training. No test evaluation.
