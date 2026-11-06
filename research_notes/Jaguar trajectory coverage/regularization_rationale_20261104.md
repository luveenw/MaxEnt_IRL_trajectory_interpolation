# What L2 and scaling could address in this finite-horizon animal IRL

2026-11-04. Research and algebraic interpretation, not a selected modeling policy.
No bindings, defaults, split, or training run are changed. Read alongside the
[Hirakawa source audit](hirakawa_feature_scaling_regularization_review_20261104.md)
and the maintained [training manual](../../jaguar_irl/training/README_SHARED.md).

## The actual statistical problem

The present model has six shared linear landscape coefficients. For route q,
let F(q) be the sum of its departure-state feature vectors, and let C specify its
map, observed start, goal, and move count. Its probability is

`P_w(q | C) = exp(w·F(q)) / sum_(u feasible under C) exp(w·F(u))`.

The trainer averages route log-likelihoods within animals and then across animals.
It optionally subtracts `lambda * ||w||² / 2`; see
[shared.py](../../jaguar_irl/training/shared.py), objective, and
[shared_reward.py](../../jaguar_irl/core/shared_reward.py), finite-horizon solver.
The covariance of feasible **path feature totals**, rather than correlations
between individual raster pixels alone, determines likelihood curvature.
These identities follow by differentiating the finite log-partition function.
The feature-matching gradient is consistent with the foundational
[Ziebart et al. (2008) MaxEnt IRL paper, p.3](https://www.cs.cmu.edu/~bziebart/publications/maximum-entropy-inverse-reinforcement-learning.pdf).

## What is being limited, and why might that help?

L2 directly discourages large coefficients **in the coordinates supplied to the
trainer**. Its scientific purpose would be to reduce unwarrantedly strong inferred
preferences when demonstrations give weak or conflicting evidence, accepting
bias to improve transfer. It is not necessary merely because rewards are shared
across extents, and six coefficients with 34 training animals do not by themselves
establish a need for it. There has been no ecological fit establishing that it
improves this project.

The behavioral quantity is a path probability ratio:

`log[P_w(q|C) / P_w(u|C)] = w·[F(q) − F(u)]`.

For illustration, a total standardized grassland-feature contrast of 10 and
coefficient 2 contribute a log-odds contrast of 20, a probability ratio about
485 million, if other features cancel. That is a mathematical example, not an
observed project contrast. Long paths can accumulate large contrasts even when
per-cell differences look modest. Multiplying all weights by a positive constant
generally changes distribution sharpness; it does not preserve these probabilities.
L2 therefore affects inferred preferences, not just printed coefficient sizes.

Three concrete risk hypotheses merit checking:

1. **Nearly interchangeable explanations.** Feasible alternatives might trade
   forest against roughness so similarly that many opposing coefficient pairs
   explain demonstrations almost equally well. Coefficients can then change
   substantially with small sampling changes while fitted probabilities barely
   change. L2 favors smaller pairs; it does not demonstrate which ecological
   explanation is true. Pixel-level collinearity is a screening signal, not proof
   of this path-level condition.
2. **Likelihood maximized only at infinite coefficients.** If observed feature
   totals are extremal relative to feasible alternatives, increasing a coefficient
   direction can improve likelihood indefinitely while concentrating probability
   on a face of the feasible feature support. This is the exponential-family
   analogue of separation. [Geyer (2009), sections3.2–3.8](https://arxiv.org/pdf/0901.0455)
   establishes constancy/recession and MLE-existence theory. Our positive-weighted
   sum of conditional route log-partition functions has the analogous finite
   convex-support geometry; this application is a derivation, not a result tested
   on the jaguar routes. Positive L2 gives a finite unique optimum here, but does
   not correct ecological or observation-process misspecification.
3. **Sampling-specific certainty.** A small set of animals, seasonal classification
   errors, or inferred grid connectors could make one landscape preference look
   stronger than it generalizes to other animals. Shrinkage could help, or could
   suppress real specialization. Only validation on animals excluded from fitting
   can assess that tradeoff. Additional routes from one animal are not equivalent
   to independent additional animals.

These are plausible scenarios, not diagnoses already made. General IRL reward
ambiguity is documented by [Ng and Russell (2000)](https://wordpress.andrewng.org/index.php/publication/algorithms-for-inverse-reinforcement-learning/).
That paper does not establish that our selected six-feature model is unidentified,
nor prescribe this L2 penalty. General reward-shaping results must not be assumed
to apply inside our restricted feature span without checking their conditions.

## What scaling changes

For one feature, write `z=(x−mu)/s`. A coefficient b on z corresponds to coefficient
`a=b/s` on x. For each fixed-horizon route, centering subtracts a constant from
every feasible path score; the same constant cancels in normalization. Thus an
invertible shared affine feature transform preserves the unpenalized model family
through coefficient reparameterization. It can still change optimizer behavior,
finite-iteration fits, and stopping rules.

With L2, that equivalence no longer preserves the objective:

`lambda * sum(b_j²)/2 = lambda * sum(s_j² * a_j²)/2`.

Using raw units makes equal numerical penalties correspond to different
ecological contrasts. For example, changing canopy units from fraction to percent
divides its equivalent coefficient by100 and its squared penalty by10,000, with
the same reward. Scaling supplies a declared comparison scale for shrinkage.
One SD is reasonable for interpreting sampled variation, but it is not uniquely
correct. A scientifically meaningful fixed contrast or bounded-range transform
is also possible. Scaling does not remove skewness or supply missing movement
features.

[Schielzeth (2010)](https://www.sfu.ca/~lmgonigl/materials-qm/papers/schielzeth-2010-103.pdf)
supports SD standardization for comparable regression slopes; it does not validate
our proposed equal-animal route-departure reference population. That proposal
would weight an animal's repeated visits and inferred connectors, exclude terminal
states, and describe experienced training variation rather than all available
landscape variation. Rarely visited features can have very small SDs. Choosing
that population requires an explicit ecological rationale; it is not settled by
citing standardization generally. Shared transforms must be fitted without test
animals; inner validation must likewise avoid using its held-out animals to fit
data-derived transforms.

The Gaussian-prior reading follows directly from algebra:
`p(w) proportional to exp(−lambda||w||²/2)`. It is isotropic only in the chosen
coordinates. Because our objective averages log-likelihood rather than using an
ordinary summed independent-data likelihood, translating lambda into an absolute
prior variance also requires declaring likelihood weighting/normalization; calling
lambda0.01 a standard prior precision would obscure that choice.

## What these additions do not establish

The log-space solver already avoids naive exponential overflow. L2 is not a
necessary numerical-overflow remedy. Scaling can improve optimization conditioning
without being a scientific argument for shrinkage. Neither addition handles map
boundary assumptions, observation error, landscape mismatch, behavioral
heterogeneity, or absent kinematic features by itself.

Hirakawa's bounded feature scaling and absence of an explicit L2 term are recorded
in the source audit above. Regularization nevertheless has precedent in MaxEnt
IRL: Ziebart et al. (2008), p.3, connects uncertainty in empirical feature
expectations to an **L1** penalty and describes exponentiated-gradient's L1-type
effect. That is support for a possible finite-demonstration rationale, not for
our isotropic L2 form, our scaler, or a particular strength. No reviewed primary
source establishes `lambda=0.01` as suitable here.

## Defensible next comparison, subject to the user's modeling decision

A training-only screening calculation on the frozen Spring plan used 34 animals,
534 routes, and equal total animal weight over departure-state visits (including
connectors). All six features vary. The largest absolute exposure correlation is
0.4401 (tree cover versus flooded habitat); the correlation condition number is
4.9659. SDs are 2.8611 for roughness, 2.2644 for population density, and
0.2263–0.3405 for the four cover fractions. There is no obvious near-duplicate
feature in this screen. This does not measure feasible-path covariance and cannot
rule out weak identification. Reproducible script:
`analysis/pantanal_covariates/diagnose_training_features.py`; result with input
hashes: `analysis/pantanal_covariates/training_feature_diagnostics_20261104.json`.
No outer-test data or reward fit was used.

Use an explicitly unpenalized baseline (`--l2 0`) and inspect convergence,
coefficient growth, feasible-path feature contrasts, and stability across training
animal subsets. If comparing regularization strengths, predeclare candidates
including zero and evaluate them using whole-animal inner validation confined to
the34 training animals. Compare predictive likelihood/calibration and coefficient
stability; do not select lambda using the nine outer-test animals. Keep the
chosen feature scale explicit and fixed within each fit. This is a proposed
assessment strategy, not evidence that L2 or z-scoring is already warranted.
