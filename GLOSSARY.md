# Jaguar seasonal movement analysis

Terms for the observation, selection and modeling units in this project.
Operational formats and commands are defined in
[jaguar_irl/training/README_SHARED.md](jaguar_irl/training/README_SHARED.md).

## Language

**Individual**:
The original tracked jaguar, retaining one identity across its observations,
collars, bursts and map contexts.
_Avoid_: treating each fragment as a new individual

**Native fix**:
An actual recorded location before intentional sampling in this analysis.
_Avoid_: inferred connecting point

**Selected fix**:
A native fix retained by the observed-point sampling procedure.

**Burst**:
A technical sequence of telemetry observations delimited by acquisition or
researcher-defined processing rules. In this workflow, bursts are split at
individual, tag, season-occurrence and hard-gap boundaries, then sampled and
screened for minimum retained points. An individual can contribute many bursts;
a burst may contain several behaviors.
_Avoid_: bout when referring to these technical data segments

**Bout**:
A period of movement behavior, such as resting, foraging or exploring. The
current temporal selection procedure does not infer behavioral states or bouts.

**Legacy bout naming**:
Existing identifiers such as `BoutProcessor`, `source_bout_id`, `n_bouts`,
`export_pantanal_bouts_irl` and policy IDs containing `bouts` refer to technical
bursts in this implementation. These names and historical artifacts remain
compatible; their wording does not imply behavioral segmentation. Existing
report labels using “bout” should likewise be read as “burst” until updated.

**Exported route**:
A spatial representation of a selected fragment, with its own starting point,
ending point and sequence of movement states.
_Avoid_: animal, complete study track

**Season occurrence**:
One dated instance of a named season, distinguished from the recurring season
pooled across years.

**Representative season-year**:
The per-extent target year for querying covariate products, chosen from the
admitted trajectories' season-years. It does not filter trajectory years or
establish the actual observation epoch of a source product. Summer's year names
its November start.
_Avoid_: training-year restriction, automatically date-matched landscape

**Wooded-cover proxy**:
The fraction of a model cell assigned to selected wooded vegetation classes in
a categorical land-cover map. MapBiomas is the chosen source for the Pantanal;
the finalized Pantanal recipe selects classes 3 and 4 only, excluding separately
mapped flooded woody classes 6 and 7. This forest/savanna class-area proxy is not
an exhaustive measure of wooded habitat. A savanna
or mixed woody pixel contributes its classified area, not a measured tree-canopy
percentage. Review the source and crosswalk when transferring outside its coverage.
_Avoid_: canopy closure, percent tree canopy, unless actually measured by the source

**Canopy closure / tree-canopy cover**:
A continuous estimate of the share of an area covered by tree canopy under the
source product's definition. This differs from the area classified as forest or
savanna, and is not interchangeable with the wooded-cover proxy.

**Map group**:
A set of movement evidence assigned to a shared local spatial domain for
computation, based on proximity of animal MCP95 domains. Group membership does
not define a biological population or statistical split stratum. It must not
constrain animal train/test allocation or cross-validation folds.
_Avoid_: validation site, unless independently justified

**Seasonal collection**:
A chosen cover of a season's evidence by map groups, with canonical ownership
preventing repeated use of the same observations.

**Nominal schedule vacancy**:
The share of assumed scheduled observation slots without a recorded fix,
conditional on the stated schedule and exposure period.
_Avoid_: measured GPS acquisition failure rate

**Temporal eligibility**:
Satisfaction of the observation sampling, continuity and minimum-burst rules.
It does not establish suitability for the numerical model.

**Optimizer candidate**:
An exported route passing the implemented temporal, geometric, movement and map
budget screens. Further input preparation and scientific assessment are needed.
An explicitly recorded training-plan map-size exception can admit an otherwise
qualified route without changing this historical export flag.
_Avoid_: ecologically validated trajectory, ready fitted model

**Shared reward**:
One common set of feature coefficients applied across the local maps in an
experiment; local movement probabilities can still differ.

**Selection checkpoint**:
A preserved account of accepted source evidence, selection policy, ownership
and spatial context, used to construct model inputs.
_Avoid_: unqualified checkpoint when optimizer progress is also discussed

**Training checkpoint**:
A preserved parameter estimate and optimizer progress for a specified fit.
_Avoid_: selection checkpoint

**Burst**:
A retained temporally contiguous segment under the selected sampling/gap rules.
Use burst in scientific prose. Historical `bout`/`BoutProcessor` identifiers and
artifact paths remain unchanged for compatibility and provenance.

**Population-density covariate**:
For the current Spring recipe, an overlap-area-weighted mean of the published
annual GlobPOP density surface (people/km²), with same-year valid LandScan
count-derived density only at approved missing/nonfinite native pixels. All
approved replacements are source-estimated zeros corroborated by modern GHSL.
Fallback-area fractions retain provenance; the mixture is not an independently
validated census or a reconstruction of the missing GlobPOP estimates.
