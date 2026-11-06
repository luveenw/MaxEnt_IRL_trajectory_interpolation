# Train/test units and covariate cache design

Recorded 2026-11-03. Read-only design review; no split, source recipe, model,
quota, or evaluation implementation changed. The accompanying local cache-size
audit supplies counts and storage estimates; this note assesses the design.

## Measured cache scope and projected costs

The reproducible offline [audit script](../../analysis/pantanal_covariates/audit_season_cache.py)
and [JSON results](../../analysis/pantanal_covariates/season_cache_audit_20261103.json)
use the current immutable checkpoint, canonical **selected** membership,
`window_seasons.csv`, all four current exports and completed Spring ledgers.
Consumed checkpoint/export tables matched manifest hashes. The independent
Spring pair list and cell count reproduce the acquired 24-pair plan, 100,402
cells per feature, and actual NPY bytes exactly. No cloud jobs were submitted.

- Winter: 9 groups, **18 group/season-year pairs**, 57,403 cached cells per
  feature; **0.689 MB** raw for the three land-cover features.
- Spring: 13 groups, **24 pairs**, 100,402 cells; **1.205 MB** raw.
- Summer: 11 groups, **22 pairs**, 84,522 cells; **1.014 MB** raw.
- Autumn: 9 groups including G324, **14 pairs**, 54,943 cells; **0.659 MB** raw.

These are 78 collection/group/year entries, not possible combinations of splits.
No group has more than four candidate season-years. The 42 group entries use
41 distinct saved grids: Spring G312 and Summer G303 share the exact grid and
2015 epoch. Annual products can therefore reduce to **77 distinct grid/year
products** if source/recipe identity is unchanged and Summer uses its start-year
map. Raw land-cover storage is 3.567 MB without reuse, 3.533 MB with it (decimal
MB; three float32 features). Roughness adds 0.603 MB for the 41 unique grids.
Identical source products can be referenced through new season/group provenance
without copying their numeric data.

Two conservative-cache pairs have no currently optimizer-admitted routes:
Winter G231/2012 and Summer G239/2011. Using only admitted evidence reduces 78
to 76 entries. Keeping the two small extra products avoids tying a reusable
cache to current admission policy. G324 support includes the documented map-size
exception; omitting it removes one pair and 4,815 cells per feature.

Summer spans November–March. Retaining **both calendar-year annual maps** for
each candidate season increases Summer from 22 to **34** pairs, giving **90
entries / 89 distinct grid/year products** across seasons. This is an envelope
for a future epoch policy, not an instruction to average maps or add time-varying
features. Four collected features need 4.691 MB raw with this envelope versus
4.136 MB using start-year maps, after reuse. A storage-only six-feature scenario
with roughness plus five annual scalar features needs 6.492–7.417 MB;
tree-cover/population recipes and compute remain unresolved.

Completed Spring output directories occupy **6.816 MB**: MapBiomas 4.663 MB,
ESA 1.276 MB, terrain 0.877 MB, including TIFF copies, NPYs, QA, metadata and
task records. Scaling each family's bytes by cached cells gives **20.1–22.9 MB**
for the four-feature all-season output archive, excluding research/source audits,
additional replicas and new repairs. Compression and metadata sizes will vary.
Separate existing research/source-audit directories total about 18.1 MB and need
not be duplicated per season. Storage does not justify changing the assessment
target at this scale.

Compute samples are **3 MapBiomas batch jobs**, **13 ESA jobs**, and **13 terrain
jobs**, reporting respectively 59.404, 4.270 and 117.011 EECU-seconds. MapBiomas
produces both features in one request. Scaling each family's measured EECUs by
cells or job count yields **0.453–0.533 EECU-hours** for start-year products,
or **0.508–0.600 EECU-hours** retaining both Summer calendar years. These are
**batch-equivalent whole-program estimates**, including Spring, not measured
total consumption or elapsed-time predictions. Spring land cover additionally
has **32 unmetered online jobs**; these were not assigned zero cost or included
in measured batch denominators. New audits, repairs, failed requests/retries,
unresolved features and model fitting are excluded. A deliberately conservative
tenfold planning allowance is about 6 EECU-hours, not a confidence bound. Actual
project tier/remaining allowance is unverified; official reference quotas are
discussed below. Exact formulas and samples are in the linked JSON and script.

## Observed split constraints

Current eligible animal totals are Winter 29, Spring 43, Summer 33 and Autumn
23 (including G324); singleton-group counts are respectively 2, 7, 4 and 4.
Canonical **selected** membership assigns each animal to just one group within
each season in this checkpoint. Duplicate-animal lists in collection summaries
include suppressed candidate memberships and do not demonstrate identity leakage.

Saved model rectangles overlap in 1 Winter, **5 Spring**, 6 Summer and 3 Autumn
group pairs. Joining positive-area intersections gives 8, **8**, 6 and 6 connected
components, respectively. These are planning diagnostics, not independent
biological blocks or an adopted split: nearby/touching rectangles and spatial
dependence may require additional separation. Merely withholding one of the
13 Spring groups does not guarantee geographically distinct assessment.

To simplify implementation without changing the prediction target: freeze an
animal allocation, run the deterministic training-only year selector once per
group, and persist a run-specific manifest referencing immutable cached files.
Future folds reuse those files; they do not repeat extraction for every split.
For future seasons, extracting only the union of epochs requested by reviewed
folds is also valid; exhaustive upfront caching is optional.

## Recommendation and scope

Retain whole-animal holdout for the initial question: interpolation for a new
animal in a represented study area. Consider spatial holdout as a separate,
valuable assessment of transfer to areas excluded from reward fitting. Neither
design is universally superior. Choose the assessment target before choosing a
convenient raster-storage strategy. This recommendation applies the distinction
between prediction to new individuals and new sites in [Roberts et al. (2017),
Box 2 and steps 1–3](https://nsojournals.onlinelibrary.wiley.com/doi/full/10.1111/ecog.02881).
Their elk example compared both individual and spatially separated individual
holdouts; its result is not evidence that jaguars lack spatial dependence.

The current [manual](../../jaguar_irl/training/README_SHARED.md#11-scientific-testing-and-prediction--placeholder)
defines groups as computational domains, not independent biological populations
or validation sites. Their grids use full-study telemetry, including eventual
test animals. Consequently, merely withholding a group does not establish a
blind geographic-transfer test. Such an assessment needs an overlap/separation
audit, consistent assignment of animals spanning domains, and an explicit
domain-construction policy. Spatial blocking may also change environmental
support; this can be appropriate for transfer but answers a different question
from interpolation in represented environments (Roberts et al., above).

## Where the actual complexity lies

- **Maps are reusable across splits.** The required annual cache is the union
  of observed `(grid, year, source recipe)` products, not a Cartesian product of
  all possible animal allocations. A fold chooses one existing year per grid;
  another fold can point to the same immutable files. The current [candidate
  cache contract](../../jaguar_irl/training/README_SHARED.md#cache-all-candidate-years-choose-final-maps-from-training-evidence-later)
  already specifies this. Static roughness has no year-selection dependency.
- **Whole-group holdout does not eliminate map coverage.** Prediction still
  requires covariates throughout the test movement domain, including alternative
  cells, as specified by the manual. It may reduce the years needed only after
  a separate epoch rule is fixed; that optimization is equally available after
  freezing an animal split.
- **The current year planner cannot plan a test-only group.**
  [plan_covariates.py](../../jaguar_irl/training/plan_covariates.py) delegates
  admission to `pin_trajectories` in [shared.py](../../jaguar_irl/training/shared.py).
  That function rejects any requested group without eligible routes in the
  chosen split. The year ranking then uses distinct training animals,
  animal-days, and earliest year. Whole-group holdout would require excluding
  test groups from training planning and adding an explicit rule for their
  map epochs; using held-out trajectories in the existing training-only rule
  would violate the agreed contract.
- **Coverage constraints need explicit treatment in either design.** Singleton
  groups cannot support within-group whole-animal training and testing.
  Keeping them training-only narrows the assessed population. Animals with no
  optimizer-admitted routes cannot supply year support. Summer uses its
  November start year, not each fix's calendar year. The manual and planner
  already record these distinctions; they should remain visible in fold plans.
  The Spring-only acquisition builder in
  [shrubland.py](../../jaguar_irl/training/shrubland.py) currently reads
  `window_start[:4]`; extending it to Summer requires the season-year join and
  an explicit annual-map convention for a season spanning two calendar years.
  This is a source-time policy issue, not growth in the number of splits.
- **Year selection and learning are different operations.** Public external
  covariates on test domains are legitimate prediction inputs. A fixed external
  reference epoch chosen before assessment could simplify both split designs,
  but would change the approved training-derived epoch policy and its temporal
  approximation. This is an option for review, not an adopted change. Neither
  test scores nor withheld positions should be used to optimize that choice.

No supported shared-model evaluator or automatic split generator currently
exists. Fold-specific map bindings and training-derived scaling must be frozen
with each fit; the binder accepts supplied shared offsets/scales but does not
learn or validate their training-only derivation. These are implementation
requirements regardless of whether groups or animals are withheld.

## Earth Engine budget interpretation

Official [noncommercial-tier documentation](https://developers.google.com/earth-engine/guides/noncommercial_tiers),
checked 2026-11-03, lists Community 150, Contributor 1,000, and Partner 100,000
EECU-hours per project per month. Community is the default when no tier is
chosen; that does not establish this project's tier. Batch **and online**
compute consume the allowance. Monthly quotas reset at midnight Pacific Time
on the first day; rollout can leave legacy behavior temporarily in effect.
Exhaustion leads to restricted throughput rather than a guaranteed hard stop.
The existing project has no verified remaining monthly allowance in our records.

Reported batch EECU-seconds are only the measured component of the Spring run;
unmeasured direct-download/online compute must not be treated as zero. EECUs
measure abstract compute work, not wall-clock time, and identical requests can
cost different amounts because of caching, source data, platform, and library
changes. Thus an area-scaled extrapolation is a planning estimate, not a quota
guarantee or completion-time prediction. See Google's [computation
overview](https://developers.google.com/earth-engine/guides/computation_overview).
The [quota guide](https://developers.google.com/earth-engine/guides/usage) also
distinguishes project limits from per-request memory/time limits; small final
rasters alone do not prove a source graph is inexpensive. No new cloud requests,
billing changes, or quota changes were made for this review.
