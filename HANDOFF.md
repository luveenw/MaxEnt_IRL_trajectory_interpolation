# Handoff notes — ctmm baseline & open methodology questions

Written to resync a fresh Claude Code session (e.g. on another machine) with where
this line of work stood. Not a project-wide status doc — see `task_list_v1.md` and
`implementation_plan_v4.md` for that. This covers one thread: building a `ctmm`
interpolation baseline to benchmark against the eventual MaxEnt IRL model, and the
methodology questions that came out of it.

## Context already established (don't re-derive)

- **Grid discretization is already per-individual** (`grid_analysis.py`): cell size
  picked from a step-length-percentile ladder per animal, not a global Hirakawa-style
  grid. Good, matches the thesis's needs already.
- **Biome pipeline exists but its output CSV does not yet exist on disk**
  (`jaguar_movement_data_with_biome.csv` — pending manual GEE ecoregion review via
  `gee/01_biome_review_app.js`). RESOLVE Ecoregions 2017, human-reviewed, weighted by
  `hours_represented`. No biome-*similarity* metric is defined anywhere yet.
- **Migratory/dispersing individuals**: no exclusion decision exists.
  `segclust2d`-based `is_range_shift` flag (from `home_range_analysis.R`) currently
  only feeds the GEE biome-review UI, not a filter. 85/117 individuals show *some*
  detected range shift, so a hard exclusion would gut the training set.
- **Behavioral states**: Schoen et al. (2025) found a **"masking effect"** — an RSF
  trained on all points is statistically indistinguishable from a resting+local-only
  model, because those states dominate numerically (~69% of fixes); exploratory
  behavior's (often opposite-signed) habitat preferences get averaged away. MaxEnt
  IRL's feature-expectation-matching objective has the same shape as an RSF
  likelihood, so it's likely to suffer the same masking unless trained per-state
  (separate reward functions) rather than pooled — matches
  `implementation_plan_v4.md`'s "try both" plan, but this is now evidence it's
  probably necessary, not just an ablation.
- **Movement-parameter summary across all 117 individuals** now exists:
  `ctmm_baseline_output/movement_parameter_summary.csv` — τ_position (days),
  τ_velocity (min), speed (km/day), AKDE-95 home range area (km²), extracted from
  every `home_range_output/individual_rds/individual_*.rds` checkpoint. This is the
  basis for a real, computable "movement-similarity" metric (see below) — more
  precise than biome label alone for deciding which individuals are comparable.

## What `ctmm_interpolation_baseline.R` does

Benchmarks `ctmm`'s Kriging-based gap interpolation (`predict.ctmm`) against naive
linear interpolation on synthetic gaps, per individual. Usage:

```bash
Rscript ctmm_interpolation_baseline.R --id 13
Rscript ctmm_interpolation_baseline.R --id 20 --gap-bins 24,48,120,192,360,504,720,960 --n-reps 2
```

`--gap-bins` (hour lo,hi pairs) and `--n-reps` let you rescale the test to an
individual's own movement timescale — necessary, see findings below. Outputs go to
`ctmm_baseline_output/individual_<ID>_{per_point,per_gap,bin_summary}.csv` and a
4-panel diagnostic PNG. **This output folder is gitignored/not committed** — rerun
the script to regenerate it.

## Key findings so far (all empirically verified, not theoretical)

1. **ctmm does NOT reliably beat linear interpolation**, at least for the two
   individuals and gap ranges tested so far. Individual 13 (53 km² home range, τ_position
   ≈ 3.2 days): overall paired Wilcoxon p=0.60 across 46 gaps. Individual 20 (2,700 km²
   home range, τ_position ≈ 53–73 days): p=0.46 across 8 gaps. Don't assume ctmm is a
   strictly better baseline without checking — report both.
2. **Why**: ctmm's edge over linear only shows up when the *true* movement during a
   gap is confined/looping (home-range wandering) rather than a directed transit.
   Individual 20's large gaps are near-straight-line transits — linear is already
   near-optimal there, nothing for ctmm's mean-reversion to fix. This ties directly to
   Schoen's behavioral states: resting/local movement (confined) vs. exploratory
   (directed transit) probably predicts *which* baseline wins, not gap duration alone.
3. **Within-individual synthetic-gap benchmarking is structurally underpowered for
   large gaps**: a large gap eats a big fraction of a finite track, capping how many
   non-overlapping replicates fit (individual 13 only yielded 1 replicate in the
   168–240h bin even after relaxing everything else). This is the strongest argument
   for pooling gap-evaluation across *multiple similar individuals* rather than
   relying on one track.
4. **Naive cross-individual model transfer crashes outright** in `ctmm` —
   `predict(FIT_from_individual_A, data=individual_B_telemetry, ...)` fails because a
   fitted model's mean location (`mu`) lives in a projection centered on the
   individual it was fit to. Movement-*style* parameters (τ_position, τ_velocity,
   speed, diffusion) are the transferable, projection-invariant quantities; `mu`
   is not and should always be re-estimated from the target individual's own data.
   Individual 13's nearest neighbor in movement-parameter space is **#117** (same
   study, nearly identical home-range area/timescale); individuals #20/#17/#67/#24
   are 50–70x too large in scale to be reasonable donors.

## Open / proposed next steps (not yet built)

**Priority order**: finish the Task 1 (occurrence()-mode for `ctmm_interpolation_baseline.R`)
and Task 2 (batch predict+occurrence across all individuals, insights/pooling plan)
implementation plans currently being drafted *first*. The `rsf.fit()` + `occurrence()`
direction below is queued to start immediately after those — confirmed as the
priority next investigation, not a someday-maybe.

### QUEUED NEXT: `rsf.fit()` + `occurrence()` for cross-individual predictive power

This is the one concrete, already-built (not proposed/custom) mechanism found so far
for giving a ctmm-based interpolation genuine cross-individual predictive power
without the raw-telemetry-pooling problems described above. Two prior "borrow
strength across individuals" ideas were dead ends or unverified:
- `ctmm::mean.ctmm()` / `ctmm::meta()`: population-level *parameter inference*
  (debiased mean + between-individual variance of τ, area, speed, diffusion via a
  χ²-inverse-gamma hierarchical model). Real and correctly-calibrated for what it
  does, but `ctmm.fit()` has no prior/shrinkage argument (checked its formals) — so
  turning `meta()`'s population mean+variance into actual regularization of a
  data-poor individual's own fit would be custom, unverified work, not a function
  call. `mean.ctmm()` produces a composite "typical individual" (including an
  averaged, not-physically-meaningful `mu`) for reporting, not for predicting a
  *specific* individual's trajectory.
- Naive model transplant (`predict(FIT_from_A, data=B, ...)`): confirmed crashes
  outright (`'names' attribute [2] must be the same length as the vector [1]`) — a
  fitted model's `mu` lives in a projection centered on the individual it was fit to.

**`rsf.fit()` sidesteps this entirely** because it estimates preference coefficients
over *environmental covariate rasters* (translation-invariant feature space), not
raw coordinates — structurally the same kind of object as a MaxEnt IRL reward
function, and the same reasoning about why IRL can legitimately pool across
individuals (see the co-occurrence discussion above) applies to it, not the "doesn't
even make sense" objection that applies to pooling raw OU/OUF telemetry.

**The concrete, already-documented mechanism**: `occurrence()`'s own signature has an
`R` argument — *"Named list of raster covariates, required only if CTMM contains a
Resource Selection Function (RSF) model"* (verbatim from the Rd doc / package
reference). This means `occurrence()` already supports being called with an
RSF-augmented CTMM object, blending an individual's own fitted movement kernel with
habitat-preference information that can legitimately be estimated from *pooled* data
across individuals. This was not designed as an interpolation-improvement trick by
us — it's the package's own built-in integration point for exactly this.

**Sources**:
- `ctmm::rsf.fit()` — package doc (title/description, extracted via `tools::Rd_db("ctmm")`):
  > "Fit integrated resource selection functions (iRSFs) with autocorrelation-adjusted
  > weighted likelihood... Integrated resource selection functions simultaneously
  > estimate the spatially constraining (availability) parameters with the resource
  > selection parameters, rather than first estimating the availability parameters
  > (usually via MCP) and then holding those parameters fixed... The 'integrated'
  > analysis reduces estimation bias, exposes correlations in the resource and
  > availability estimate uncertainties, and propagates the availability estimate
  > uncertainties into the final outputs."
- **Alston, J.M., Fleming, C.H., Kays, R., et al. (2022).** "Mitigating
  pseudoreplication and bias in resource selection functions with
  autocorrelation‐informed weighting." *Methods in Ecology and Evolution*, 14(2),
  643–654. doi:10.1111/2041-210X.14025. **This is the methods paper behind
  `rsf.fit()`** — introduces the autocorrelation-weighted-likelihood scheme
  specifically to fix the pseudoreplication/bias problem that plain IID-assuming RSFs
  have with autocorrelated tracking data (i.e., it's the ctmm-ecosystem answer to
  exactly the co-occurrence/pseudoreplication concern raised for IRL/RSF pooling —
  worth reading alongside that discussion, not separately). Open access
  (CC-BY, hybrid OA) — full text should be retrievable directly.
- `ctmm::occurrence()` — Rd doc, `R` argument: *"A named list of raster covariates if
  CTMM contains an RSF model."*
- **Fleming, C.H., Fagan, W.F., Mueller, T., et al. (2016).** "Estimating where and
  how animals travel: An optimal framework for path reconstruction from
  autocorrelated tracking data." *Ecology*, 97(3), 576–588. doi:10.1890/15-1607.
  Theoretical basis for `occurrence()`'s Kriging framework itself (closed access, no
  full-text excerpts retrieved — abstract only).
- **Calabrese, J.M., Fleming, C.H., & Gurarie, E. (2016).** "ctmm: an R package for
  analyzing animal relocation data as a continuous‐time stochastic process."
  *Methods in Ecology and Evolution*, 7(9), 1124–1132. doi:10.1111/2041-210X.12559.
  The package paper; open access (bronze OA).

**Not yet done**: actually running `rsf.fit()` on any jaguar individual, checking
what raster covariates are actually available/needed (ties back to the GEE covariate
pipeline — `jaguar_movement_data_with_biome.csv` doesn't exist on disk yet, and full
environmental raster layers for `rsf.fit()`'s `R` argument are a separate, larger ask
than the biome label alone), confirming `occurrence(..., R=...)` actually works
end-to-end with a fitted RSF-CTMM object, and designing what "improves predictive
power for interpolation" would even mean to measure here (probably: does an
RSF-augmented `occurrence()` UD assign more density to true held-out points than a
plain movement-only `occurrence()` UD, for the same individual and gap — a natural
extension of the isopleth-coverage metric already planned for Task 1).

- **Donor-informed fitting test** (proposed, unverified, lower priority than the
  above): take a deliberately data-starved subset of individual 13's track, fit ctmm
  with and without using individual #117's τ/σ as an informative prior/starting value
  in `ctmm.fit()`, and see whether borrowing improves interpolation on the same
  held-out gaps. Needs verifying the correct way to fix/seed parameters in
  `ctmm.fit()`.
- **Bout/excursion segmentation**: Hirakawa's "50% removed from the middle of the
  trajectory" protocol doesn't map cleanly onto a multi-month jaguar deployment (their
  unit was a discrete multi-day round trip). The correct translation is a discrete
  behavioral bout (an exploratory excursion away from a core area and back), which
  requires the Schoen-style 3-state HMM segmentation to exist first. Once
  `jaguar_irl/data/hmm_classifier.py` (planned in `implementation_plan_v4.md` §2.2) is
  built, redo the gap-benchmark using bout boundaries as the natural "trajectory" unit
  instead of arbitrary hour-based bins.
- **Biome-similarity metric**: proposed but not implemented — a Multivariate
  Environmental Similarity Surface (MESS; Elith, Kearney & Phillips 2010, *Methods in
  Ecology and Evolution*, doi:10.1111/j.2041-210X.2010.00036.x) over standardized
  per-home-range environmental covariates, once the GEE covariate resampling step
  produces them. Distinct from the movement-parameter similarity metric above (this
  one is about environment/habitat, that one is about movement style) — likely want
  both as separate stratification axes for train/val splits.

## occurrence()/predict() mechanics — verified during Task 1 scoping

- `predict()`: point estimate + covariance at specific query times (one row per
  time). `occurrence()`: a full spatial `UD` raster (`$PDF`/`$CDF` over `$x`/`$y`),
  time marginalized away entirely — cannot ask it "where at time t" the way
  `predict()` answers; comparison has to happen at the gap-window level, not
  row-by-row.
- `cor.min`/`dt.max` govern whether `occurrence()` will even attempt to bridge a
  gap; `predict()` has **no equivalent safety valve at all** — it always returns a
  confident-looking answer regardless of gap size, reverting silently toward the
  stationary mean once correlation decays. `occurrence()` is the one ctmm gives you
  that's designed to admit "the data no longer constrains this."
- Closed form for the per-individual bridgeable-gap threshold (OUF velocity process
  is a simple OU process, single-exponential ACF): `Δt_bridgeable = −τ_velocity · ln(cor.min)`.
  Verified against individual 13's actual fit: predicted 54.5 min (cor.min=0.05,
  τ_velocity=18.2 min) vs. actual `dt.max` default fallback 60.0 min
  (`median(diff(t))`) — matches. **Every gap bin in the existing benchmark (2h–240h)
  already exceeds individual 13's default bridgeable threshold** — under default
  settings, `occurrence()` would likely refuse to smoothly bridge most of what's
  already being tested. This is a feature to design around, not a bug.
- `dt.max` default (`NULL` → `median(diff(data$t))`) and `cor.min` default (0.05,
  velocity correlation as of ctmm ≥0.5.6) should be set **per individual**, not as
  one global value — a fixed `dt.max=48h` is reasonable for individual 13
  (τ_position≈3.2d) but would make `occurrence()` refuse almost everything for
  individual 20 (τ_position≈53–73d), and vice versa.

## Silent-failure risk in small-sample individuals — verified, not just theoretical

Tested individuals 35 (17 pts) and 38 (18 pts) directly with only a `tryCatch`
wrapper, no explicit point-count floor:
- **ID 35**: `ctmm.fit()` issues a **warning**, not an error (`"MLE is near a
  boundary or optimizer failed."`). An `error=`-only `tryCatch` (what
  `home_ranges/home_range_analysis.R` actually uses) does **not** catch this —
  execution would silently continue to AKDE/occurrence on a degenerate fit.
- **ID 38**: **no error, no warning at all**, but the fitted parameters are
  physically absurd (τ[velocity] ≈ 1.18e-43 s, speed ≈ 8.5e69 km/day). `occurrence()`
  ran "successfully" on top of it, returning a technically-valid-shaped UD built on
  meaningless numbers.
- **Conclusion**: an explicit point-count floor is still doing real protective work,
  not redundant with `tryCatch`. For the batch `predict`/`occurrence` pipeline
  (Task 2), need: (a) `tryCatch(..., warning = function(w) stop(w))` or
  `options(warn=2)` to escalate boundary-fit warnings into caught errors, and (b) a
  post-fit plausibility check rejecting/flagging fits with physically-impossible
  speed/diffusion/τ values, since case 38 shows neither error nor warning will
  reliably surface a degenerate fit on its own.

## Co-occurring individuals: IRL pooling ≠ ctmm pooling (don't conflate these)

Pooling *raw telemetry* across individuals for one ctmm/OUF fit doesn't make sense
(one process, one `mu`) — that objection does **not** transfer to MaxEnt IRL, whose
entire mechanism is pooling many trajectories into one shared, feature-space reward
function; that's the intended fix for data-poor individuals, not a workaround. What
*does* carry over from co-occurrence specifically: (a) inflated effective sample
size / overstated confidence when co-occurring individuals share near-identical
environmental feature values along their paths (a precision problem); (b) genuine
point-estimate bias only when there's direct interaction (territorial
avoidance, mother–cub/mating pairs) or a shared unmodeled driver (fire, flood,
carcass) — an omitted-variable confound, not just pseudoreplication. Mitigations:
cluster-robust SEs on θ (cluster = same study + overlapping period), consider a
local-conspecific-density reward feature if metadata supports real interaction risk,
confirm the planned spatial-block CV doesn't leak by splitting co-occurring
individuals across train/test. The Alston et al. (2022) autocorrelation-weighting
paper above is the ctmm-ecosystem's own answer to the RSF version of this same
problem — read together with this section, not separately.

## Files referenced above

- `ctmm_interpolation_baseline.R` — the baseline script (committed).
- `ctmm_baseline_output/movement_parameter_summary.csv` — regenerate via the R
  snippet that loops `home_range_output/individual_rds/*.rds` and pulls
  `summary(FIT, units=FALSE)$CI` (rownames use "position"/"velocity", not literal
  "tau" — Greek τ character — grep accordingly if rewriting).
- `home_ranges/home_range_analysis.R` — moved from repo root into `home_ranges/`
  since this file was last written; update paths if referencing.
- `home_range_output/individual_rds/individual_*.rds` — **does not currently exist
  on disk** (gitignored output, cleaned between sessions) — rerun
  `home_ranges/home_range_analysis.R` to regenerate before relying on checkpoints
  again. All τ/speed/area numbers above came from either regenerating a fit on the
  fly (`ctmm.guess`/`ctmm.fit` directly from `jaguar_movement_data.csv`, fast) or
  were captured before the directory was cleaned.
