# Exploratory Data Analysis Plan: Jaguar Movement Data

## Goal

Conduct comprehensive EDA on the full (unfiltered) Morato et al. (2018) dataset **before** applying quality filters, to understand data structure, identify patterns, and inform downstream modelling decisions.

> [!IMPORTANT]
> All analyses run on ALL 117 individuals before trimming. This ensures we understand what data we have and what we're discarding.

---

## Proposed Analyses (8 Categories)

### 1. Data Quality Diagnostics
**Purpose:** Understand completeness, temporal coverage, and potential biases before filtering.

| Plot / Output | Description |
|---|---|
| Fix count histogram | Distribution of GPS fixes per individual |
| Tracking duration histogram | Days of data per individual |
| Fix interval distribution | Per-individual median, IQR, and outlier intervals |
| Temporal coverage heatmap | Individuals × months, showing data presence/absence |
| Missing data pattern | Gap fraction per individual, flagging sparse trackers |

**Literature basis:** Standard telemetry data screening (Frair et al. 2010; Fleming et al. 2018 ctmm vignettes).

---

### 2. Movement Metrics
**Purpose:** Characterise movement behaviour via step lengths and turning angles.

| Plot / Output | Description |
|---|---|
| Step length distributions | Histogram + fitted distributions (Weibull, Gamma) per individual and pooled |
| Turning angle distributions | Rose diagram / circular histogram — pooled and per-study |
| Step length × turning angle scatter | Reveals correlated movement modes (directed vs. tortuous) |
| Speed distribution | Step length / time interval, distinguishing fix rates |

**Literature basis:** Morales et al. (2004) — mixture models for movement; Schoen et al. (2025) — jaguar-specific HMM with 3 states; Patterson et al. (2008) — state-space models.

---

### 3. Temporal & Diel Activity Patterns
**Purpose:** Detect circadian rhythms and seasonal patterns in movement.

| Plot / Output | Description |
|---|---|
| Diel activity plot | Step length by hour-of-day (polar or bar), pooled and per-study |
| Seasonal movement rates | Monthly mean step length / speed |
| Fix rate by hour | Reveals sampling bias (programmed fix schedules) |
| Activity overlap between studies | Diel activity curve comparisons across biomes |

**Literature basis:** Rowcliffe et al. (2014) — activity estimation from camera/GPS; Cozzi et al. (2012) — diel patterns of African carnivores.

---

### 4. Spatial Autocorrelation (Variograms)
**Purpose:** Quantify spatial and temporal autocorrelation to inform block CV size and model assumptions.

| Plot / Output | Description |
|---|---|
| Empirical variogram per individual | Semivariance vs. time lag — reveals home range behaviour (plateau = range residency) |
| Pooled variogram by study | Study-level autocorrelation structure |
| Autocorrelation range table | Numeric range estimates for each individual |

**Literature basis:** Fleming et al. (2014) ctmm framework; Roberts et al. (2017) — variogram for block CV sizing. **Implementation note:** Use the `SciKit-GStat` Python library or compute empirically from step displacements.

---

### 5. Home Range Estimation (MCP & KDE)
**Purpose:** Estimate space use per individual; provides tile-sizing context and overlap analysis input.

| Plot / Output | Description |
|---|---|
| 100% MCP per individual | Convex hull area (km²) per individual |
| 95% MCP per individual | Trimmed convex hull (excludes outlier fixes) |
| Home range size by study/biome | Boxplot or violin plot of areas grouped by study |
| Geographic map of all MCPs | All home ranges overlaid on a map (folium or matplotlib) |

**Literature basis:** Mohr (1947) — MCP original; Nilsen et al. (2008) — MCP sample size effects; Silveira (2004) — jaguar home range sizes.

> [!NOTE]
> Full KDE/AKDE are computationally expensive. Start with MCP for EDA, then use KDE for select individuals. AKDE reserved for post-filtering (Phase 2).

---

### 6. Spatial Overlap & Social Network
**Purpose:** Identify individuals sharing space — informs whether to pool or separate for IRL training.

| Plot / Output | Description |
|---|---|
| Pairwise MCP overlap matrix | Jaccard index of 95% MCP overlap between individuals in same study area |
| Overlap network graph | Nodes = individuals, edges = overlap intensity, coloured by study |
| Network metrics | Degree, clustering coefficient — reveals spatial groupings |

**Literature basis:** Fieberg & Kochanny (2005) — home range overlap indices; Spiegel et al. (2016) — spatial overlap networks for animal sociality; Craft et al. (2009) — disease / contact networks.

---

### 7. Net Squared Displacement (NSD)
**Purpose:** Classify gross movement patterns — resident, disperser, migrant, nomad.

| Plot / Output | Description |
|---|---|
| NSD time series per individual | NSD(t) curve — shape reveals movement type |
| NSD classification | Heuristic classification by curve shape (plateau=resident, monotonic=disperser) |
| Summary table | Individual × movement type |

**Literature basis:** Bunnefeld et al. (2011) — NSD for migratory classification; Börger & Fryxell (2012) — NSD for movement mode identification.

---

### 8. Cross-Study Comparison
**Purpose:** Compare movement characteristics across the 20 studies / 5 countries / multiple biomes.

| Plot / Output | Description |
|---|---|
| Study summary table | n individuals, median fixes, median duration, median step length, median home range, per study |
| Country-level comparison | Boxplots of key metrics by country |
| Biome-level comparison | Metrics by ecological context (if biome labels can be inferred from study names) |

---

## Implementation Design

### File Structure

```
jaguar_irl/data/eda.py          ← All EDA functions + report generation
jaguar_irl/data/eda_report/     ← Generated output (plots + HTML summary)
```

### Architecture

```python
# Each analysis category is a function returning a dict of {name: figure}
def data_quality_diagnostics(df) -> dict[str, Figure]: ...
def movement_metrics(df) -> dict[str, Figure]: ...
def temporal_diel_patterns(df) -> dict[str, Figure]: ...
def spatial_autocorrelation(df) -> dict[str, Figure]: ...
def home_range_estimation(df) -> dict[str, Figure]: ...
def spatial_overlap_network(df) -> dict[str, Figure]: ...
def net_squared_displacement(df) -> dict[str, Figure]: ...
def cross_study_comparison(df) -> dict[str, Figure]: ...

def run_full_eda(csv_path) -> Path:
    """Run all analyses and save plots + HTML report."""
```

### Dependencies
- `matplotlib`, `numpy`, `scipy`, `pandas` (already available)
- `shapely` for MCP computation
- `networkx` for overlap network
- No R / rpy2 needed — variograms computed with `scipy` or `scikit-gstat`

---

## Verification

Run `python -m jaguar_irl.data.eda` and confirm:
- [ ] All 8 analysis functions execute without error
- [ ] Plots are saved to `jaguar_irl/data/eda_report/`
- [ ] A summary HTML file links all plots
- [ ] Key statistics are printed to console

---

## References

- Borger, L. & Fryxell, J.M. (2012). Quantifying individual differences in dispersal using net squared displacement. *Dispersal Ecology and Evolution*, 222-230.
- Bunnefeld, N. et al. (2011). A model-driven approach to quantify migration patterns. *Journal of Animal Ecology*, 80(2), 466-476.
- Cozzi, G. et al. (2012). Fear of the dark or dinner by moonlight? Reduced temporal partitioning among Africa's large carnivores. *Ecology*, 93(12), 2590-2599.
- Craft, M.E. et al. (2009). Distinguishing epidemic waves from disease spillover in a wildlife population. *Proceedings of the Royal Society B*, 276(1663), 1777-1785.
- Fieberg, J. & Kochanny, C.O. (2005). Quantifying home-range overlap: the importance of the utilization distribution. *Journal of Wildlife Management*, 69(4), 1346-1359.
- Fleming, C.H. et al. (2014). From fine-scale foraging to home ranges: a semivariance approach to identifying movement modes. *The American Naturalist*, 183(5), E154-E167.
- Frair, J.L. et al. (2010). Resolving issues of imprecise and habitat-biased locations in ecological analyses using GPS telemetry data. *Phil. Trans. R. Soc. B*, 365(1550), 2187-2200.
- Mohr, C.O. (1947). Table of equivalent populations of North American small mammals. *The American Midland Naturalist*, 37(1), 223-249.
- Morales, J.M. et al. (2004). Extracting more out of relocation data: building movement models as mixtures of random walks. *Ecology*, 85(9), 2436-2445.
- Nilsen, E.B. et al. (2008). Can minimum convex polygon home ranges be used to draw biologically meaningful conclusions? *Ecological Research*, 23(3), 635-639.
- Patterson, T.A. et al. (2008). State-space models of individual animal movement. *Trends in Ecology and Evolution*, 23(2), 87-94.
- Roberts, D.R. et al. (2017). Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. *Ecography*, 40(8), 913-929.
- Rowcliffe, J.M. et al. (2014). Quantifying levels of animal activity using camera trap data. *Methods in Ecology and Evolution*, 5(11), 1170-1179.
- Schoen, A.N. et al. (2025). Open-source, environmentally dynamic ML models demonstrate behavior-dependent utilization of space by a wide-ranging carnivore. *Movement Ecology*.
- Silveira, L. (2004). Ecology and conservation of the jaguar (Panthera onca) in the Cerrado. PhD Thesis.
- Spiegel, O. et al. (2016). Socially interacting or indifferent neighbours? Randomization of movement paths to tease apart social preference and spatial constraints. *Methods in Ecology and Evolution*, 7(8), 971-978.
