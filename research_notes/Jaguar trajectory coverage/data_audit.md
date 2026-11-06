# Jaguar telemetry and existing range analyses

## What does the raw telemetry contain?

### Takeaway
The CSV has 134,690 fixes assigned to 117 individual IDs, with strikingly heterogeneous record lengths and fix schedules. The identifier to retain through any trajectory split is `individual.local.identifier (ID)`; tag numbers are not a reliable substitute.

### Cited Findings
- Direct CSV audit (Python `csv`/`datetime`, sorted within individual): 117 IDs, 134,690 fixes, 20 study names; 17–10,988 fixes per ID (median 560) and 6.3–1,465.8 days from first to last timestamp (median 215.8 days). All timestamps parsed as `%m/%d/%y %H:%M`; coordinates were nonempty and within global latitude/longitude bounds. — [raw telemetry](/home/luveen/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/OneDrive%20Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/data/jaguar_movement_data.csv)
- The CSV columns include `Event_ID`, timestamp, longitude, latitude, species, `tag.local.identifier`, `individual.local.identifier (ID)`, study and country. They contain no home-range crossing labels, behavioral states, residence periods, or explicitly defined trajectory IDs. — [raw telemetry](/home/luveen/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/OneDrive%20Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/data/jaguar_movement_data.csv)
- Five individual IDs have two distinct tag identifiers (25, 27, 53, 59, 89), while eight tag identifiers occur under multiple individual IDs (including tag `1` under IDs 42, 58 and 93). Thus tag and individual are not one-to-one in this file. — [raw telemetry](/home/luveen/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/OneDrive%20Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/data/jaguar_movement_data.csv)
- Across the 134,573 within-individual consecutive intervals, 2,901 exceed 24 hours and 246 exceed seven days; 51 of 117 individuals have at least one gap over seven days. Median fix intervals vary substantially by individual (examples: ID 12, 1 hour; ID 1, 8 hours; ID 35, about 360 hours). — [raw telemetry](/home/luveen/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/OneDrive%20Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/data/jaguar_movement_data.csv)

### Inferences
- Neither fix count nor elapsed calendar duration proves that a resident jaguar traversed its range enough times. Individual 35, for example, spans 477 days with only 17 fixes and very large intervals; elapsed span alone would be misleading.
- Long gaps should terminate continuous observed paths for movement modeling, even if pre- and post-gap locations belong to the same biological individual and can eventually contribute to the same validated stationary-range analysis.

### Gaps
- The CSV has no direct measure of range crossing or range-residence timescale; these require trajectory-dependent estimation from the coordinates and timestamps.
- The correspondence between `individual.local.identifier (ID)` and biological animal must ultimately be checked against the source data dictionary, particularly where a tag was reused.

## What range analysis already exists, and does it diagnose coverage?

### Takeaway
The repository already has per-individual ctmm model fits and AKDE polygons, but its current AKDE script fits each entire individual record, with no temporal segmentation or range-crossing sufficiency gate. The polygons therefore cannot be treated as proof that each record captures a stable home range.

### Cited Findings
- The current analysis builds one telemetry object per individual, computes a variogram, calls `ctmm.select`, and then calls `akde` on the entire record. It skips only records with fewer than 20 valid points. — [current AKDE script](/home/luveen/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/OneDrive%20Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/home_ranges/home_range_analysis_akde_parallel.R)
- The script explicitly states that the former `segclust2d` temporal segmentation was removed because its configured `ncluster = c(2, 3)` excluded one cluster and could not genuinely return “no shift.” Its retained `n_core_areas` counts disconnected 50% AKDE polygon components, a geometric signal rather than a temporal range-shift test. — [current AKDE script](/home/luveen/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/OneDrive%20Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/home_ranges/home_range_analysis_akde_parallel.R)
- Existing `home_ranges_raw.geojson` has features for 115 of the 117 IDs (missing IDs 35 and 38); its fields include contour level, area, `ctmm_model`, number of GPS points, and trajectory duration, but no crossing count or position-autocorrelation timescale diagnostic. There are also 115 per-individual RDS outputs. — [range output](/home/luveen/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/OneDrive%20Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/home_ranges/home_range_output/home_ranges_raw.geojson); [RDS directory](/home/luveen/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/OneDrive%20Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/home_ranges/home_range_output/individual_rds)
- The current Python movement processor filters IDs using at least 100 fixes, 60 days, and at most 50% of days without fixes, then projects each individual and emits **one** full-length `(row, col, sequential index)` trajectory per ID. It defines a `resample_interval_hours = 4.0` setting, but the shown processing steps do not use that setting; time indices simply enumerate raw fixes. — [movement processor](/home/luveen/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/OneDrive%20Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/jaguar_irl/data/movement_processor.py)

### Inferences
- Current AKDE polygons and ctmm fits are useful **starting points** for estimating stationary-range area and movement timescales, but for range-shifting animals or records with very long gaps they can conflate distinct residence periods. Inspect the fitted models/variograms and source fixes before using a polygon as a valid stationary range.
- The Python export currently treats a one-hour interval and a multi-day interval as identical one-step transitions, and can implicitly link points across outages. It needs explicit time handling and segmentation before use as IRL expert paths.

### Gaps
- The exported GeoJSON does not report `tau_p`, `T/tau_p`, effective sample size, crossing count, or range-area stabilization. The RDS objects may retain fitted model parameters, but I did not extract and validate those in this audit.
- The current output does not supply a validated catalog of stationary-range episodes for each individual.

## How should the raw data be split into learning trajectories?

### Takeaway
First decide which *individual residence periods* have adequate repeated coverage of a stable range; then split those periods into shorter, gap-safe IRL paths while retaining individual and residence IDs. Do not require every short learning path to contain 30–50 range crossings: that diagnostic concerns the coverage of the aggregate residence-period data used to infer a home range.

### Cited Findings
- The input has per-fix timestamps and stable individual IDs, but no pre-existing crossing labels, while 51 individuals have gaps longer than a week. — [raw telemetry](/home/luveen/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/OneDrive%20Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/data/jaguar_movement_data.csv)
- The current Python processor already supplies per-individual projection and grid discretization, but it assigns sequential time indices to raw fixes and exports a single path per ID. — [movement processor](/home/luveen/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/OneDrive%20Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/jaguar_irl/data/movement_processor.py)
- The existing R pipeline produces whole-individual ctmm fits and AKDEs and expressly has no valid temporal range-shift segmentation. — [current AKDE script](/home/luveen/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/OneDrive%20Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/home_ranges/home_range_analysis_akde_parallel.R)

### Inferences
- Proposed sequence: (1) group by biological individual, sort and quality-check fixes, collar changes and timestamps; (2) find major outages and candidate seasonal/range shifts, inspect variograms and fitted ctmm residence timescale for each candidate range episode; (3) establish adequate repeated coverage and approximate area stabilization *within each episode*, explicitly recording failures/uncertainty; (4) divide accepted episodes at gaps, range shifts and, if useful, fixed windows or natural excursions into many IRL paths; (5) preserve individual ID, episode ID, source timestamps, elapsed durations, sampling regime and train/test grouping in path metadata.
- A 30–50 crossing criterion, if applicable to the desired home-range estimator and habitat, should operate on each candidate resident-range episode, not as an arbitrary cutoff on a short path or as a fixed number of GPS fixes. Estimate crossing time/coverage from the fitted movement process and check observed range-area convergence rather than assuming the count from elapsed days alone.
- Use common temporal sampling or a transition model that honors actual elapsed time; avoid interpolating across long missing intervals, and do not force variable-duration individual tracks into an equal step count. Prevent validation leakage by holding out whole individuals (or at minimum whole residence episodes), not random windows from the same animal.

### Gaps
- A defensible exact gap threshold, temporal resolution, and crossing criterion have not been calibrated against these animals’ fitted movement timescales and measurement schedules.
- Whether one animal contributes multiple stationary-range episodes, and how many episodes qualify, cannot be determined from the existing outputs alone.
