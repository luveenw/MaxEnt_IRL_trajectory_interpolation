# IRL Jaguar Movement Thesis — Task Checklist

## Phase 1: Data & Infrastructure (Mar–May 2026)
- [x] Create branching strategy (`feature/linear-irl`, `feature/deep-irl`)
- [x] Port [MaxEntIRL.py](file:///home/luveenw/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/MaxEntIRL.py), [train.py](file:///home/luveenw/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/train.py), [test.py](file:///home/luveenw/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/test.py) to Python 3.10+ / PyTorch
- [x] Replace `cv2` dependencies with `scipy`
- [x] Add type hints and replace print statements with logging
- [/] Pre-filtering EDA (Step 1b): biome assignment + full 8-category analysis
  - [/] Add biome type column via study-country lookup
  - [/] Biome-grouped visualizations (~20 new plots)
  - [/] Per-country MCP maps and overlap networks
  - [ ] Data coverage & covariate availability analysis
- [ ] Parse and clean [jaguar_movement_data.csv](file:///home/luveenw/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/jaguar_movement_data.csv) (fix CR line endings, validate coords)
- [ ] Per-individual trajectory extraction and quality filtering
- [ ] Temporal regularization (4-hr resampling via `crawl`/`ctmm`)
- [ ] Coordinate projection (WGS84 → UTM per study area)
- [ ] Grid discretization pipeline
- [ ] Post-filtering EDA (Step 2a): re-run all analyses on filtered individuals, output to `post_filtering/`
- [ ] AKDE home range estimation (per qualified individual via R `ctmm`)
- [ ] AKDE pairwise overlap indices (UDOI, BA)
- [ ] 99% AKDE isopleth tile bounding boxes
- [ ] Compare AKDE vs MCP home range estimates
- [ ] Implement configurable state/action spaces
- [ ] Set up GEE feature extraction pipeline
- [ ] Build feature maps for Morato study areas (13 features)
- [ ] Build feature maps for Madre de Dios

## Phase 2: Baseline Models (Apr–Jul 2026)
- [ ] Compute step lengths / turning angles
- [ ] Fit 3-state HMM for behavioral classification
- [ ] Fit RSF (logistic regression, mixed effects)
- [ ] Fit iSSF with behavioral state interactions
- [ ] Construct resistance surface from RSF + depredation model
- [ ] Compute least-cost corridors

## Phase 3: IRL Training (May–Sep 2026)
- [ ] Implement `DeepRewardNet` (neural network reward)
- [ ] Implement state-aware IRL (per-behavior reward functions)
- [ ] Train/validation/test split (stratified by biome)
- [ ] Hyperparameter search (grid resolution, LR, architecture)
- [ ] Train linear MaxEnt IRL (initial model)
- [ ] Train deep MaxEnt IRL (if time permits)
- [ ] Inspect learned reward maps for ecological interpretability

## Phase 4: Preliminary Results (**Oct 2026 Conference**)
- [ ] Prepare preliminary cross-validation results
- [ ] Compare IRL vs. baseline spatial predictions
- [ ] Conference presentation slides and poster

## Phase 5: Simulation & Transfer (Sep–Jan 2027)
- [ ] Implement `JaguarAgent` ABM framework
- [ ] Build Madre de Dios feature maps with human disturbance layer
- [ ] Run simulations (100+ agents, 1000+ realizations)
- [ ] Integrate human disturbance scenarios
- [ ] Aggregate into movement density maps

## Phase 6: Validation & Benchmarking (Dec 2026–Feb 2027)
- [ ] Spatial block cross-validation
- [ ] Individual-level cross-validation
- [ ] Compute all metrics (AUC, Boyce, MSD, KS tests, BA/UDOI, EMD)
- [ ] IRL vs. baselines paired Wilcoxon test
- [ ] Madre de Dios depredation point validation
- [ ] Sensitivity analyses (grid resolution, feature ablation, disturbance scenarios)
- [ ] Expert validation of corridor maps

## Phase 7: Thesis Writing (Jan–May 2027)
- [ ] Introduction & literature review
- [ ] Methods chapter
- [ ] Results chapter
- [ ] Discussion & conservation implications
- [ ] Revision cycles with advisor
- [ ] Defense preparation & submission
