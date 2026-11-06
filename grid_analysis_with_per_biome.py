"""
Jaguar Movement Grid Analysis (with Per-Biome Output)
======================================================
Analyzes each individual jaguar's GPS telemetry data to:
  1. Characterise inter-fix distance and time-gap distributions (per individual)
  2. Determine an appropriate grid cell size for each individual
  3. Convert raw GPS trajectories into (x, y, time_step) grid sequences.
  4. Generate population-level AND biome-level summary statistics.
"""

import os
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import scipy.stats as stats
from pyproj import Geod
from tqdm import tqdm

warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "data", "jaguar_movement_data.csv")
INFO_PATH = os.path.join(BASE_DIR, "data", "Jaguar_additional_information_fixed.csv")
BIOME_PATH = os.path.join(BASE_DIR, "data", "study_area_biome_mapping.csv")

FIG_DIR  = os.path.join(BASE_DIR, "fig", "grid_analysis")
TRAJ_DIR = os.path.join(BASE_DIR, "data", "grid_trajectories")
REPORT_PATH = os.path.join(BASE_DIR, "data", "grid_analysis_report.csv")
BIOME_FIG_DIR = os.path.join(FIG_DIR, "per_biome")

os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(TRAJ_DIR, exist_ok=True)
os.makedirs(BIOME_FIG_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────
GEOD = Geod(ellps="WGS84")
CANDIDATE_CELL_SIZES_KM = [0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0,
                            7.5, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0]
MAX_GAP_HOURS = 24.0

# ──────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────
def geodesic_km(lon1, lat1, lon2, lat2):
    _, _, dist_m = GEOD.inv(lon1, lat1, lon2, lat2)
    return np.abs(dist_m) / 1000.0

def choose_cell_size(median_step_km: float, p10_step_km: float) -> float:
    reference = max(median_step_km, p10_step_km, 0.1)
    for cs in CANDIDATE_CELL_SIZES_KM:
        if cs >= reference: return cs
    return CANDIDATE_CELL_SIZES_KM[-1]

def latlon_to_grid(lon_arr, lat_arr, lon_min, lat_min, cell_size_km):
    mean_lat_rad = np.radians(np.mean(lat_arr))
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * np.cos(mean_lat_rad)
    dx_km = (lon_arr - lon_min) * km_per_deg_lon
    dy_km = (lat_arr - lat_min) * km_per_deg_lat
    return np.floor(dx_km / cell_size_km).astype(int), np.floor(dy_km / cell_size_km).astype(int)

def build_grid_trajectory(sub_df, cell_size_km):
    lons, lats = sub_df["location.long"].values, sub_df["location.lat"].values
    x_arr, y_arr = latlon_to_grid(lons, lats, lons.min(), lats.min(), cell_size_km)
    
    result = sub_df[["timestamp", "location.long", "location.lat"]].copy()
    result["x"], result["y"] = x_arr, y_arr
    result["elapsed_min"] = ((sub_df["timestamp_dt"] - sub_df["timestamp_dt"].iloc[0]).dt.total_seconds() / 60.0).values

    xy_shifted = result[["x", "y"]].shift(1)
    same_as_prev = (result["x"] == xy_shifted["x"]) & (result["y"] == xy_shifted["y"])
    result = result[~same_as_prev].reset_index(drop=True)
    result["time_step"] = result.index
    return result

# ──────────────────────────────────────────────────────────────────────────────
# LOAD DATA
# ──────────────────────────────────────────────────────────────────────────────
print("Loading jaguar GPS data …")
df = pd.read_csv(CSV_PATH, low_memory=False)
df.rename(columns={"individual.local.identifier (ID)": "ID"}, inplace=True)
df["timestamp_dt"] = pd.to_datetime(df["timestamp"], format="%m/%d/%y %H:%M", errors="coerce")
df.dropna(subset=["timestamp_dt", "location.long", "location.lat"], inplace=True)
df.sort_values(["ID", "timestamp_dt"], inplace=True)
df.reset_index(drop=True, inplace=True)
individuals = sorted(df["ID"].unique())

# ──────────────────────────────────────────────────────────────────────────────
# PER-INDIVIDUAL ANALYSIS
# ──────────────────────────────────────────────────────────────────────────────
report_rows = []
all_step_km = {}
all_gap_hr  = {}

for ind_id in tqdm(individuals, desc="Individuals"):
    sub = df[df["ID"] == ind_id].copy().reset_index(drop=True)
    n_fixes = len(sub)
    
    lons, lats, times = sub["location.long"].values, sub["location.lat"].values, sub["timestamp_dt"].values
    step_km, gap_hr = np.full(n_fixes, np.nan), np.full(n_fixes, np.nan)

    if n_fixes > 1:
        step_km[1:] = geodesic_km(lons[:-1], lats[:-1], lons[1:], lats[1:])
        gap_hr[1:]  = (pd.to_datetime(times[1:]) - pd.to_datetime(times[:-1])).total_seconds() / 3600.0

    gap_ok = gap_hr[1:] <= MAX_GAP_HOURS
    valid_steps = step_km[1:][gap_ok]
    valid_gaps  = gap_hr[1:][gap_ok]
    nonzero_steps = valid_steps[valid_steps > 0]

    def safe_stat(arr, fn): return float(fn(arr)) if len(arr) > 0 and np.isfinite(fn(arr)) else np.nan

    p10_step = safe_stat(nonzero_steps, lambda a: np.percentile(a, 10))
    med_step = safe_stat(nonzero_steps, np.median)
    med_gap  = safe_stat(valid_gaps, np.median)
    mode_gap = float(stats.mode(np.round(valid_gaps * 2) / 2, keepdims=True).mode[0]) if len(valid_gaps) > 0 else np.nan

    cell_size_km = choose_cell_size(med_step if not np.isnan(med_step) else 0.0, p10_step if not np.isnan(p10_step) else 0.0)
    grid_traj = build_grid_trajectory(sub, cell_size_km)
    
    all_step_km[ind_id] = nonzero_steps
    all_gap_hr[ind_id]  = valid_gaps

    report_rows.append({
        "ID": ind_id, "n_fixes": n_fixes, 
        "step_median_km": med_step, "gap_median_hr": med_gap, "gap_mode_hr": mode_gap,
        "cell_size_km": cell_size_km
    })

report_df = pd.DataFrame(report_rows)

# ──────────────────────────────────────────────────────────────────────────────
# POPULATION-LEVEL SUMMARY FIGURES
# ──────────────────────────────────────────────────────────────────────────────
print("Generating population-level summary figures …")
pool_steps = np.concatenate([v for v in all_step_km.values() if len(v) > 0])
pool_gaps  = np.concatenate([v for v in all_gap_hr.values()  if len(v) > 0])

def generate_summary_plot(steps, gaps, subset_df, title, filename):
    """Helper to plot the 6-panel summary figure for any subset"""
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle(title, fontsize=15, fontweight="bold")

    # (a) Step-length histogram
    ax = axes[0, 0]
    clip_s = np.percentile(steps, 98) if len(steps) else 1
    ax.hist(steps[steps <= clip_s], bins=80, color="#2e86de", edgecolor="white", alpha=0.85)
    ax.axvline(np.median(steps), color="#ffa502", lw=2, ls="--", label=f"Median={np.median(steps):.2f} km")
    ax.set_xlabel("Step length (km) [clipped P98]"); ax.set_ylabel("Count"); ax.set_title("(a) Step-Length Distribution"); ax.legend()

    # (b) Step-length ECDF
    ax = axes[0, 1]
    sorted_s = np.sort(steps)
    ecdf_s = np.arange(1, len(sorted_s)+1) / len(sorted_s)
    clip_s99 = np.percentile(sorted_s, 99) if len(sorted_s) else 1
    ax.plot(sorted_s[sorted_s <= clip_s99], ecdf_s[sorted_s <= clip_s99], color="#2e86de", lw=1.5)
    ax.axvline(np.median(steps), color="#ffa502", lw=1.8, ls="--", label=f"Median={np.median(steps):.2f} km")
    ax.set_xlabel("Step length (km) [clipped P99]"); ax.set_ylabel("Cumulative probability"); ax.set_title("(b) Step-Length ECDF"); ax.set_ylim(0, 1); ax.legend()

    # (c) Per-individual median step length (ranked)
    medians = subset_df.set_index("ID")["step_median_km"].sort_values()
    ax = axes[0, 2]
    ax.barh(range(len(medians)), medians.values, color="#2e86de", alpha=0.75, height=0.8)
    ax.set_xlabel("Median step length (km)"); ax.set_ylabel("Individual (ranked)"); ax.set_title("(c) Median Step Length per ID");
    ax.set_yticks(range(len(medians))); ax.set_yticklabels(medians.index.astype(str), fontsize=7)

    # (d) Time-gap histogram
    ax = axes[1, 0]
    clip_g = np.percentile(gaps, 98) if len(gaps) else 1
    ax.hist(gaps[gaps <= clip_g], bins=80, color="#8e44ad", edgecolor="white", alpha=0.85)
    ax.axvline(np.median(gaps), color="#ffa502", lw=2, ls="--", label=f"Median={np.median(gaps):.2f} hr")
    ax.set_xlabel("Inter-fix time gap (hours) [clipped P98]"); ax.set_ylabel("Count"); ax.set_title("(d) Time-Gap Distribution"); ax.legend()

    # (e) Time-gap ECDF
    ax = axes[1, 1]
    sorted_g = np.sort(gaps)
    ecdf_g = np.arange(1, len(sorted_g)+1) / len(sorted_g)
    clip_g99 = np.percentile(sorted_g, 99) if len(sorted_g) else 1
    ax.plot(sorted_g[sorted_g <= clip_g99], ecdf_g[sorted_g <= clip_g99], color="#8e44ad", lw=1.5)
    ax.axvline(np.median(gaps), color="#ffa502", lw=1.8, ls="--", label=f"Median={np.median(gaps):.2f} hr")
    ax.set_xlabel("Inter-fix time gap (hours) [clipped P99]"); ax.set_ylabel("Cumulative probability"); ax.set_title("(e) Time-Gap ECDF"); ax.set_ylim(0, 1); ax.legend()

    # (f) Distribution of chosen cell sizes
    ax = axes[1, 2]
    cell_counts = subset_df["cell_size_km"].value_counts().sort_index()
    ax.bar(cell_counts.index.astype(str), cell_counts.values, color="#44bd32", alpha=0.85)
    ax.set_xlabel("Grid cell size (km)"); ax.set_ylabel("Number of individuals"); ax.set_title("(f) Chosen Cell Sizes")
    for i, (cs, cnt) in enumerate(zip(cell_counts.index, cell_counts.values)):
        ax.text(i, cnt + (cell_counts.max()*0.02), str(cnt), ha="center", va="bottom", fontsize=9)
    ax.tick_params(axis="x", rotation=45)

    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches="tight")
    plt.close(fig)

generate_summary_plot(pool_steps, pool_gaps, report_df, 
                      f"Population-Level Movement Statistics — All {len(individuals)} Jaguars",
                      os.path.join(FIG_DIR, "population_summary.png"))

# ──────────────────────────────────────────────────────────────────────────────
# BIOME-LEVEL SUMMARY FIGURES
# ──────────────────────────────────────────────────────────────────────────────
print("\nGenerating biome-level summary figures …")

try:
    # Read mapping info with defensive column resolution
    info_df = pd.read_csv(CSV_PATH)
    biome_map_df = pd.read_csv(BIOME_PATH)
    
    # Locate likely columns ignoring exact casing
    id_col = next((c for c in info_df.columns if "INDIVIDUAL.LOCAL.IDENTIFIER" in c.upper()), None)
    study_col_info = next((c for c in info_df.columns if "STUDY" in c.upper() or "AREA" in c.upper()), None)
    
    study_col_map = next((c for c in biome_map_df.columns if "STUDY" in c.upper() or "AREA" in c.upper()), None)
    biome_col = next((c for c in biome_map_df.columns if "BIOME" in c.upper()), None)
    
    print(f"ID column: {id_col} | study column: {study_col_info} | study mapping column: {study_col_map} | biome mapping column: {biome_col}")
    if all([id_col, study_col_info, study_col_map, biome_col]):
        # Map IDs to biomes
        sa_to_biome = dict(zip(biome_map_df[study_col_map], biome_map_df[biome_col]))
        info_df["Biome"] = info_df[study_col_info].map(sa_to_biome)
        id_to_biome = dict(zip(info_df[id_col], info_df["Biome"]))
        
        report_df["Biome"] = report_df["ID"].map(id_to_biome)
        
        for biome, group in report_df.groupby("Biome"):
            biome_ids = group["ID"].tolist()
            
            # Pool arrays specifically for this biome
            b_steps = np.concatenate([all_step_km[i] for i in biome_ids if i in all_step_km and len(all_step_km[i]) > 0])
            b_gaps = np.concatenate([all_gap_hr[i] for i in biome_ids if i in all_gap_hr and len(all_gap_hr[i]) > 0])
            
            if len(b_steps) == 0:
                continue
            
            title = f"Biome-Level Movement Statistics — {biome} ({len(biome_ids)} Jaguars)"
            # Replace spaces and both forward and backward slashes
            clean_biome = str(biome).replace(' ', '_').replace('/', '_').replace('\\', '_')
            filename = os.path.join(BIOME_FIG_DIR, f"{clean_biome}_summary.png")
            generate_summary_plot(b_steps, b_gaps, group, title, filename)
            print(f"  → Saved {biome} summary.")
            
    else:
        print("Warning: Could not resolve merge columns for biome datasets. Biome figures skipped.")
        
except FileNotFoundError:
    print("Warning: Extra CSV mapping files not found. Biome figures skipped.")

print("\nDone ✓")