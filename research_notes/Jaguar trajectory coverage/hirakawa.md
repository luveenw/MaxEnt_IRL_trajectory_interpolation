# Hirakawa et al. (2018): trajectory selection and home-range coverage

## Did trajectory selection seek to capture each shearwater's home range?

### Takeaway
No such objective is stated. The selected unit was the outward leg of a qualifying colony-based foraging round trip; the stated selection rationale was varied environmental exposure for IRL training and evaluable interpolation gaps, not saturation of an individual utilization distribution.

### Cited Findings
- Appendix S1, pp. 1–2: round-trip candidates were delimited by crossings of latitude/longitude thresholds around the breeding island; only trips longer than eight hours were accepted. The authors then required short missing portions (under about 50 km) for artificial-gap evaluation and trips whose farthest point was over approximately 300 km from the colony. They retained the outward journey from colony to farthest point, omitting the return journey, and analyzed 106 such trajectories (53 per sex). — [Appendix S1, pp. 1–2](</home/luveen/Dropbox/Documents/Luveen Wadhwani/OneDrive/OneDrive Documents/Luveen-Obsidian/03 - Projects/Columbia/00 - Thesis/MaxEnt_IRL_trajectory_interpolation/Hirakawa et al. - 2018 - Supplement 1.pdf>)
- The explicit reason given for the >300 km criterion is that training should be diverse in quantity and quality and that interpolation benefits from trajectories passing through varied environmental locations. — [Appendix S1, p. 1](</home/luveen/Dropbox/Documents/Luveen Wadhwani/OneDrive/OneDrive Documents/Luveen-Obsidian/03 - Projects/Columbia/00 - Thesis/MaxEnt_IRL_trajectory_interpolation/Hirakawa et al. - 2018 - Supplement 1.pdf>)
- The paper explains that chick-rearing shearwaters make colony-based round-trip foraging expeditions, but its 106 analyzed trajectories are the selected outward segments. — [Main paper, p. 5](https://doi.org/10.1002/ecs2.2447); [Appendix S1, pp. 1–2](</home/luveen/Dropbox/Documents/Luveen Wadhwani/OneDrive/OneDrive Documents/Luveen-Obsidian/03 - Projects/Columbia/00 - Thesis/MaxEnt_IRL_trajectory_interpolation/Hirakawa et al. - 2018 - Supplement 1.pdf>)
- The learned reward maps and train/test sets are stratified by sex: 43 trajectories of each sex train a map, while 10 of each sex are held out. The authors discuss possible future inclusion of individual attributes in movement prediction, but do not report individual-specific reward maps. — [Main paper, pp. 10–11 and 19](https://doi.org/10.1002/ecs2.2447)

### Inferences
- These choices support coverage of environmental conditions and route types for a **sex-level movement/interpolation model**. They do not ensure that any particular bird's full home range was sampled; exclusion of the return leg and the >300 km criterion would preclude treating the selected legs as a representative utilization distribution without further evidence.
- Repeated visits or crossings of a jaguar's range would serve a different purpose: establishing the spatial and temporal support of an individual home-range estimate. Appendix S1's distance threshold is not a substitute for that.

### Gaps
- The paper and appendices do not give a number of selected trajectories per distinct bird or an individual-to-trajectory mapping, so individual coverage cannot be assessed from the reported selection counts.
- No home-range stabilization, range-crossing threshold, or individual utilization-distribution completeness check is described for trajectory selection.

## What role does home-range estimation play in the paper?

### Takeaway
Home-range estimation is named as a **possible downstream use of more accurate gap filling**, not the target of the IRL fitting or a criterion for selecting the 106 journeys.

### Cited Findings
- The abstract describes the task as predicting likely routes through missing GPS segments, using trajectories to infer environmental preferences and reward maps. — [Main paper, p. 1](https://doi.org/10.1002/ecs2.2447)
- The introduction says missing or uneven GPS observations can bias behavioral analysis, including home-range determination, and that straight-line interpolation can underestimate track length and tortuosity. — [Main paper, p. 4](https://doi.org/10.1002/ecs2.2447)
- In the discussion the authors say their filled paths were adequate for most ecological purposes, giving home-range estimation as an example, while noting errors on convoluted foraging/search paths. — [Main paper, p. 17](https://doi.org/10.1002/ecs2.2447)
- They note that their grid-step state drops actual timing/dwell information, which matters; they defend location-only utility partly by observing that ecological studies sometimes estimate/analyze home ranges without exact timing. — [Main paper, pp. 19–20](https://doi.org/10.1002/ecs2.2447)
- Their evaluation instead holds out trajectories, removes at least 50% of each test trajectory artificially, and compares reconstructed and observed routes with a modified Hausdorff distance. — [Main paper, pp. 10–11](https://doi.org/10.1002/ecs2.2447)

### Inferences
- Applying this method before jaguar home-range estimation could improve placement of missing movement segments, but prediction accuracy does not establish that enough independent movement has been observed to estimate each jaguar's range robustly. These are separate validation questions.
- Grid-step representation is especially consequential if the eventual jaguar estimand is time-weighted utilization: the model collapses residence time in a cell. Retain timestamps and original telemetry for the range estimator even if grid-step trajectories are built for IRL.

### Gaps
- Hirakawa et al. do not calculate home-range areas, compare home-range estimates before/after interpolation, or test how many trips/crossings are needed for range stabilization.
