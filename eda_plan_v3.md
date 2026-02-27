# Enhanced EDA Plan: Jaguar Movement Data (v2)

## Overview

Run comprehensive EDA **twice** — before and after Step 2 (data processing) — to understand raw data structure and measure the impact of quality filtering. Outputs saved to separate subdirectories for cross-comparison.

```
jaguar_irl/data/eda_report/pre_filtering/   ← Full unfiltered dataset (117 individuals)
jaguar_irl/data/eda_report/post_filtering/  ← After quality filtering (~90 individuals)
```

---

## Biome Type Assignment (New)

A `biome` column will be added to the DataFrame during initial loading, using study name as the key. All assignments are sourced from Morato et al. (2018), Morato et al. (2021), and corroborated by the Movebank study metadata.

| Study Name | Country | Biome |
|---|---|---|
| Panthera_Pantanal-Jaguar-Project | Brazil | Pantanal |
| Jaguar_Taiama | Brazil | Pantanal |
| jaguar_Oncafari Project | Brazil | Pantanal |
| Sao Bento | Brazil | Pantanal |
| Pantanal | Paraguay | Pantanal |
| Paraguayan Pantanal | Paraguay | Pantanal |
| Jaguar Conservation in the Atlantic Forest | Brazil | Atlantic Forest |
| Jaguars' Movement Pattern in a fragmente landscape | Brazil | Atlantic Forest |
| IOP | Brazil | Atlantic Forest |
| Atlantic forest | Paraguay | Atlantic Forest |
| Jaguar Conservation in the Caatinga Biome | Brazil | Caatinga |
| Humid Chaco | Paraguay | Humid Chaco |
| Dry Chaco | Paraguay | Dry Chaco |
| Jaguar Conservation in Argentina | Argentina | Humid Chaco |
| Jaguar Conservation in Argentina | Brazil | Atlantic Forest |
| Rio Negro | Brazil | Amazon/Pantanal transition |
| Jaguar_Mamiraua | Brazil | Amazon (Varzea) |
| Costa Rica | Costa Rica | Tropical moist forest |
| Greater Lacandona Ecosystem | Mexico | Tropical moist forest |
| Jaguar Mex | Mexico | Tropical dry forest |
| jaguar of sonora | Mexico | Sonoran Desert scrub |

> [!IMPORTANT]
> "Jaguar Conservation in Argentina" spans two countries. Argentina records → Humid Chaco; Brazil records → Atlantic Forest. This requires a compound key (study + country) for biome assignment.

**Collapsed biome categories** for statistical comparisons (some biomes have very few individuals):

| Biome Group | Component Biomes | n (approx) |
|---|---|---|
| Pantanal | Pantanal | ~41 |
| Atlantic Forest | Atlantic Forest | ~19 |
| Chaco | Humid Chaco, Dry Chaco | ~17 |
| Amazon/Transition | Amazon (Varzea), Amazon/Pantanal transition | ~12 |
| Mesoamerican Forest | Tropical moist forest, Tropical dry forest, Sonoran Desert scrub | ~9 |
| Caatinga | Caatinga | ~2 |

---

## Updated Analyses (8 Categories + Biome Overlays)

### 1. Data Quality Diagnostics

**Existing plots** (unchanged):
- 1a. Fix count histogram
- 1b. Tracking duration histogram
- 1c. Fix interval distribution by study
- 1d. Temporal coverage heatmap

**New biome-grouped plots:**
- 1e. Fix count by biome (boxplot with mean/median/CI markers)
- 1f. Tracking duration by biome (boxplot + histogram per biome)
- 1g. Fix interval distribution by biome (violin or boxplot)
- 1h. Temporal coverage by biome (separate heatmap per biome, or color-coded)
- 1i. Data density timeline: fixes per month per individual (line plot, faceted by biome)

### 2. Movement Metrics

**Existing plots** (unchanged):
- 2a. Step length distribution (linear + log)
- 2b. Turning angle rose diagram
- 2c. Step length vs. absolute turning angle
- 2d. Speed distribution

**New biome-grouped plots:**
- 2e. Pooled step lengths by biome (overlapping histograms or ridgeline plot)
- 2f. Turning angle distributions per biome (small-multiple rose diagrams)
- 2g. Step length vs. turning angle colored by biome
- 2h. Speed distribution by biome (boxplot with mean/SD/CI + optional histogram facets)

### 3. Temporal & Diel Patterns

**Existing plots** (unchanged):
- 3a. Diel activity (mean step length by hour)
- 3b. Seasonal movement (mean step length by month)
- 3c. Fix rate by hour
- 3d. Diel activity by study (top 5)

**New biome-grouped plots:**
- 3e. Diel activity by biome (one line per biome, overlaid on single plot)
- 3f. Seasonal movement by biome (faceted bar charts)
- 3g. Fix rate by hour per biome (to detect biome-specific sampling schedules)
- 3h. Diel activity per biome (one subplot per biome, with log-scale option for step length to reveal smaller-scale variation)

### 4. Spatial Autocorrelation (Variograms)

**Updated existing plot:**
- 4a. Variograms with biome type in subplot titles

### 5. Home Range Estimation (MCP)

**Existing plots** (redesigned):
- 5a. Home range by study (unchanged)
- 5b. **Per-country MCP maps** — one map per country, zoomed to fit all ranges, with study-based coloring and legend

### 6. Spatial Overlap Network

**Redesigned:**
- 6a. **Per-country network maps** — one network graph per country
- 6b. Cross-country overlap callout: if any individual has MCP overlap with an individual in a different country, highlight with a distinct edge style/color

### 7. Net Squared Displacement

**Updated:**
- 7a. NSD time series with biome type in subplot titles
- Add section description explaining NSD metric, classification logic (resident vs. disperser), and ecological interpretation

### 8. Cross-Study Comparison

**Existing plots** (unchanged):
- 8a. Country comparison boxplots

**New biome-grouped plots:**
- 8b. Biome comparison boxplots (fixes, duration, step length)
- 8c. Study summary table extended with biome column

---

## New Section 9: Data Coverage & Feature Availability

Address whether the data supports the planned IRL and baseline models.

| Question | How Addressed |
|---|---|
| Data points over time per individual | Plot 1i (data density timeline) |
| Seasonality in data | Plots 3b, 3f (monthly step length by biome) |
| Data availability per landscape type | Biome summary table + plot 1e (fixes by biome) |
| Feature candidates for IRL/baseline | New table: candidate covariates with availability per biome |
| Minimum covariate set across studies | New table: covariate × biome matrix showing coverage |

**New output: `covariate_availability.csv`**

| Covariate | Source | Pantanal | Atlantic Forest | Chaco | Amazon | Mesoamerican | Caatinga |
|---|---|---|---|---|---|---|---|
| Tree cover % | Hansen GFC | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Distance to water | HydroSHEDS | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Elevation | SRTM | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Slope / Ruggedness | SRTM-derived | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| NDVI (seasonal) | MODIS | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Land cover class | ESA WorldCover | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Human footprint | WCS HFP | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Distance to roads | OSM | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Distance to settlements | OSM/GHSL | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Precipitation | CHIRPS/ERA5 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Temperature | ERA5 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Prey density proxy | Camera trap / modelled | ? | ? | ? | ? | ? | ? |
| Humidity | ERA5 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

> [!NOTE]
> All satellite-based covariates (tree cover, NDVI, elevation, land cover, etc.) are available globally and thus across all biomes. Prey density is the most difficult — it requires either camera trap data or species distribution models, and availability is biome-specific.

---

## CSV Visualization Check

| CSV File | Already Visualized? | Action |
|---|---|---|
| [individual_stats.csv](file:///home/luveenw/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/jaguar_irl/data/eda_report/individual_stats.csv) | Partially (histograms) | Add biome column; visualize as biome-grouped summary |
| [home_range_mcp.csv](file:///home/luveenw/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/jaguar_irl/data/eda_report/home_range_mcp.csv) | Yes (boxplot + map) | Add biome column |
| [overlap_matrix.csv](file:///home/luveenw/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/jaguar_irl/data/eda_report/overlap_matrix.csv) | Yes (network) | No change needed |
| [network_metrics.csv](file:///home/luveenw/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/jaguar_irl/data/eda_report/network_metrics.csv) | Not visualized | Add to HTML report as summary table |
| [study_summary.csv](file:///home/luveenw/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/jaguar_irl/data/eda_report/study_summary.csv) | Not visualized | Add to HTML report + extend with biome column |
| `covariate_availability.csv` | New | Render as table in HTML report |

---

## Implementation Changes

### Files to modify

#### [MODIFY] [jaguar_irl/data/eda.py](file:///home/luveenw/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/jaguar_irl/data/eda.py)
- Add `STUDY_BIOME_MAP` dictionary and `assign_biome()` function
- Add `output_subdir` parameter to [run_full_eda()](file:///home/luveenw/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/jaguar_irl/data/eda.py#809-848) for pre/post comparison
- Add ~20 new biome-grouped plot functions
- Redesign 5b (per-country maps) and 6a (per-country networks)
- Add Section 9 data coverage analysis and covariate table
- Add NSD section description

#### [MODIFY] [jaguar_irl/data/movement_processor.py](file:///home/luveenw/Dropbox/Documents/Luveen%20Wadhwani/OneDrive/Documents/Luveen-Obsidian/03%20-%20Projects/Columbia/00%20-%20Thesis/MaxEnt_IRL_trajectory_interpolation/jaguar_irl/data/movement_processor.py)
- Add biome column during data loading (so it persists through filtering)

### Pre/post comparison workflow

```python
# Before filtering
run_full_eda("jaguar_movement_data.csv", output_dir="jaguar_irl/data/eda_report/pre_filtering")

# After filtering (Step 2)
run_full_eda("jaguar_irl/data/processed/filtered.csv", output_dir="jaguar_irl/data/eda_report/post_filtering")
```

---

## References

- Borger, L. & Fryxell, J.M. (2012). Quantifying individual differences in dispersal using net squared displacement. *Dispersal Ecology and Evolution*, 222-230.
- Bunnefeld, N. et al. (2011). A model-driven approach to quantify migration patterns. *J. Animal Ecology*, 80(2), 466-476.
- Cozzi, G. et al. (2012). Fear of the dark or dinner by moonlight? *Ecology*, 93(12), 2590-2599.
- Craft, M.E. et al. (2009). Distinguishing epidemic waves from disease spillover. *Proc. R. Soc. B*, 276(1663), 1777-1785.
- Fieberg, J. & Kochanny, C.O. (2005). Quantifying home-range overlap. *J. Wildlife Management*, 69(4), 1346-1359.
- Fleming, C.H. et al. (2014). From fine-scale foraging to home ranges. *Am. Nat.*, 183(5), E154-E167.
- Frair, J.L. et al. (2010). Resolving issues of imprecise and habitat-biased locations. *Phil. Trans. R. Soc. B*, 365(1550), 2187-2200.
- Mohr, C.O. (1947). Table of equivalent populations of North American small mammals. *Am. Midland Nat.*, 37(1), 223-249.
- Morales, J.M. et al. (2004). Extracting more out of relocation data. *Ecology*, 85(9), 2436-2445.
- Morato, R.G. et al. (2018). Space use and movement of jaguars. *PLoS ONE*, 13(4), e0195946.
- Morato, R.G. et al. (2021). Jaguar movement database v2. *Movebank Data Repository*.
- Nilsen, E.B. et al. (2008). Can MCP home ranges be used to draw biologically meaningful conclusions? *Ecol. Res.*, 23(3), 635-639.
- Patterson, T.A. et al. (2008). State-space models of individual animal movement. *TREE*, 23(2), 87-94.
- Roberts, D.R. et al. (2017). Cross-validation strategies for structured data. *Ecography*, 40(8), 913-929.
- Rowcliffe, J.M. et al. (2014). Quantifying levels of animal activity. *MEE*, 5(11), 1170-1179.
- Schoen, A.N. et al. (2025). Behavior-dependent utilization of space by a wide-ranging carnivore. *Movement Ecology*.
- Silveira, L. (2004). Ecology and conservation of the jaguar in the Cerrado. PhD Thesis.
- Spiegel, O. et al. (2016). Socially interacting or indifferent neighbours? *MEE*, 7(8), 971-978.
