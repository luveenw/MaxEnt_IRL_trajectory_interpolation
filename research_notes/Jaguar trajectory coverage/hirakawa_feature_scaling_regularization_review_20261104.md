# Hirakawa (2018): map association, feature scaling and regularization

2026-11-04. Primary-source review requested before selecting a scaling policy.
No scaling policy, production binding profile, optimizer configuration or
training run is selected or activated by this note. Raw-unit and z-score
profiles prepared elsewhere are candidates, not scientific decisions.

## Findings that change how the proposal should be described

1. The versioned **binding** layer is this repository's engineering/provenance
   machinery, not a statistical method named in Hirakawa. Its role is to tell a
   run which feature array belongs to which map, in which feature order, with
   what units, definition and affine transform. Associating aligned environmental
   features with model states is necessary in both implementations; the particular
   manifests, cache indexes, hashes and profiles are our additions.
2. Hirakawa did **not** simply use original physical units. Appendix S2, p.1,
   explicitly says feature maps were scaled into the interval **−1 to0**. The
   reasons given are the original negative-cost formulation and undesirable
   behavior when feature magnitudes differ substantially.
3. Hirakawa did **not** describe z-scoring. No training-only equal-animal
   departure-state standardization appears in the paper, supplements or checked
   author code. It is a proposed adaptation, not replication of their recipe.
4. The main paper's displayed likelihood objective and gradient contain **no L2
   penalty**, and no L1/L2 term was found in the checked author trainer. Our
   optional `--l2`, default0.01, is an additional project modeling choice. The
   author code's `lam=0.01` is a **learning rate**, not a regularization coefficient.

Primary paper: [Hirakawa et al., *Can AI predict animal movements?*](https://doi.org/10.1002/ecs2.2447).
Local primary copies:
[main paper](../../Hirakawa%20et%20al.%20-%202018.pdf),
[Appendix S1](../../Hirakawa%20et%20al.%20-%202018%20-%20Supplement%201.pdf),
[Appendix S2](../../Hirakawa%20et%20al.%20-%202018%20-%20Supplement%202.pdf).

## Paper and author-code evidence

Main article pp.9–10 defines a reward linear in12 feature maps and maximizes
mean trajectory log-likelihood; the displayed equations are unnumbered. It
updates positive weights by exponentiated gradient. Main p.11 reports an initial
weight1.0 and learning rate0.01. Appendix S2 p.1 defines sea/land indicators,
exponentiated-distance features and a constant map, then gives the bounded
negative feature scaling. The supplement does not specify a sample-mean/SD
calculation or establish the exact data population used to choose scaling bounds.
Do not invent a training-only z-score or precise min–max formula from its range
statement alone.

The paper explicitly links
[the author's repository](https://github.com/thirakawa/MaxEnt_IRL_trajectory_interpolation)
and [Zenodo code DOI](https://doi.org/10.5281/zenodo.1402941). The inspected current
source files were downloaded read-only on2026-11-04:

- [`train.py`](https://github.com/thirakawa/MaxEnt_IRL_trajectory_interpolation/blob/master/train.py),
  lines19–21: one configured feature-map stack file; lines56–64 and103–116:
  each trajectory loads that same stack. Lines91–92 average likelihood and
  expected counts across trajectories. Lines126–157 update weights using
  empirical minus expected counts and a multiplicative exponential update.
  `lam` is halved/doubled on poorer/better likelihood and multiplies the gradient
  in the exponent. No squared-weight penalty or shrinkage gradient appears.
- [`MaxEntIRL.py`](https://github.com/thirakawa/MaxEnt_IRL_trajectory_interpolation/blob/master/MaxEntIRL.py),
  lines54–67: `load_features` loads the NPY array, checks feature count against
  weights and obtains state dimensions. Lines78–84 compute the linear reward.
  There is no versioned binding registry or runtime feature standardizer here.
- [`make_3d_feature_map.py`](https://github.com/thirakawa/MaxEnt_IRL_trajectory_interpolation/blob/master/data/feature_map/make_3d_feature_map.py)
  loads a prepared2D stack and replicates it through610 time planes; it does not
  compute a z-score or reconstruct original GIS units.

The local `MaxEnt IRL - clean v1.0 github code.zip` has byte-identical copies
of those three code files to the checked author repository. Their SHA256 values
are respectively `affe07bf1c5314581670228fb550f4d31dc56c6a266a24d0459d7f1350162935`,
`5c4a306d4c59c490a6c05940d0c433c477412a8737d97a78c72c75f67e9636e5`, and
`adfdf0c8948222b6a05507b3f7e4554cc1c856517e6b3ec458d5403441fbdc42`.
The zip SHA256 is `e038d1b6c08d3af81a971dd34302a876cf213fe3aafabc118b1dce49d208f771`.
Thus the code comparison is not based merely on assuming our fork is original.

The bundled `feature_map_2d.npy` has shape[12,200,300], all values within[−1,0],
and nonzero feature means/nonunit SDs. It is demonstrably not z-scored. Some
example details differ from the paper/supplement (e.g. code initial weight0.5,
constant plane−1, binary-like planes−0.8/−0.2); therefore the public example is
not evidence that every reported paper setting was reproduced literally. The
pre-scaling GIS generation code is not included in the checked entry points.

## Our L2 term and why scaling matters

In [shared.py](../../jaguar_irl/training/shared.py), `objective` first combines
animal-weighted route log-likelihoods and gradients, then returns

`mean_log_likelihood − (lambda/2) * sum_j(weight_j²)`

and gradient `likelihood_gradient − lambda*weights`. The current CLI default is
`--l2 0.01`; `--l2 0` disables this penalty. L2 discourages large coefficient
magnitudes, pulling preferences toward weaker coefficients when evidence does
not justify extremes. It is not MaxEnt's trajectory-entropy constraint, nor the
paper's learning rate. Changing the penalty or selecting its strength requires
scientific/numerical justification and, when tuning, validation confined to
training animals. Setting it to0 would remove this one adaptation; it would not
make the whole current implementation identical to Hirakawa, because objective
weighting, signed coefficients, finite-horizon solver and other contracts differ.

Changing predictor units changes the compensating coefficient needed to express
the same reward. Without a coefficient penalty, linear rescaling can often be
absorbed by coefficient rescaling. An isotropic L2 penalty is not invariant to
that operation: it penalizes numerical coefficient size. Scaling therefore
changes the effective relative shrinkage across features, not merely runtime.
For our fixed-horizon conditional likelihood, subtracting a shared feature mean
adds a path-constant shift that cancels in normalization; changing feature scale
still changes the L2 penalty's interpretation. Our signed-weight, finite-horizon
core does not require all feature values to be negative to remain finite, so
Hirakawa's negative-feature requirement must not be imposed without its original
formulation context.

## Is the proposed z-score defensible?

**Generic centering/SD scaling has peer-reviewed support; this exact choice of
reference observations does not come from Hirakawa.**

[Schielzeth (2010), *Methods in Ecology and Evolution*1:103–113](https://doi.org/10.1111/j.2041-210X.2010.00012.x)
defines scaling by the predictor SD and explains standardized coefficient
interpretation; see pp.104–105 and the
[author paper copy](https://www.sfu.ca/~lmgonigl/materials-qm/papers/schielzeth-2010-103.pdf).
Its motivation and examples concern regression interpretation, not an empirical
validation of animal-weighted MaxEnt preprocessing. It also notes dependence
on the reference population and cautions about categorical indicators. Our500m
area fractions are continuous proportions rather than strictly binary
indicators, but standardizing them is still a choice, not an obligation.

[Gelman (2008), *Statistics in Medicine*27:2865–2873](https://doi.org/10.1002/sim.3107)
explains bringing numeric inputs onto a common scale and specifically proposes
**two** SDs to facilitate certain comparisons with binary variables; see the
[author manuscript](https://sites.stat.columbia.edu/gelman/research/published/standardizing7.pdf).
It should not be cited as proof that our one-SD formula or animal weights are
uniquely correct.

For the proposed current candidate, each training animal contributes equal total
mass, and each departure-state visit within an animal contributes equally across
its routes. Repeated visits and inferred connecting grid cells are included;
terminal states are excluded. The mean/SD come from those features on the chosen
training-context maps, and the identical transforms are applied to test-context
maps. That choice protects the fitting boundary and prevents long-record animals
from defining the scale by observation count alone. It is **our prespecified
reference-distribution choice**, and could instead use a reviewed set of available
landscape cells, fixed physically meaningful scales, or a bounded-range transform.
Those alternatives imply different coefficient/penalty interpretations. None is
auto-proven optimal by a generic standardization citation.

The proposed state-based scale does not change the existing equal-animal
mean-whole-route likelihood into a per-step objective. It is also not new movement
observations: grid connectors remain deterministic geometry inferred between GPS
anchors. Any influence from those connectors on preprocessing should be disclosed
and can motivate a comparison against observed-anchor-only scaling before the
scientific policy is selected.

**Recommended communication:** explain binding as file/grid/meaning association;
explain optional scaling separately; acknowledge Hirakawa's bounded[−1,0]
features and unpenalized published objective; present z-score/reference-distribution
and L2 choices as reviewable project adaptations, with no selected policy inferred
from the availability of candidate binding files.
