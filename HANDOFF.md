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

- **Donor-informed fitting test** (proposed, unverified): take a deliberately
  data-starved subset of individual 13's track, fit ctmm with and without using
  individual #117's τ/σ as an informative prior/starting value in `ctmm.fit()`, and
  see whether borrowing improves interpolation on the same held-out gaps. Needs
  verifying the correct way to fix/seed parameters in `ctmm.fit()` (didn't confirm
  the exact API before deciding not to guess under time pressure — check
  `?ctmm.fit`, `?ctmm.select`, and possibly `ctmm::meta()` properly first).
- **`ctmm::rsf.fit()`** (autocorrelation-corrected resource selection function) was
  identified as a better cross-individual-generalizing baseline than raw ctmm/OUF,
  since it's a linear-preference-over-features model like the eventual IRL reward,
  not an idiosyncratic per-individual space-use kernel. Not yet tried. Worth adding
  alongside linear + ctmm in the baseline lineup.
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

## Files referenced above

- `ctmm_interpolation_baseline.R` — the baseline script (committed).
- `ctmm_baseline_output/movement_parameter_summary.csv` — regenerate via the R
  snippet that loops `home_range_output/individual_rds/*.rds` and pulls
  `summary(FIT, units=FALSE)$CI` (rownames use "position"/"velocity", not literal
  "tau" — Greek τ character — grep accordingly if rewriting).
- `home_range_output/individual_rds/individual_*.rds` — per-individual ctmm fits
  and telemetry from the existing `home_range_analysis.R` pipeline (already run for
  115/117 individuals).
