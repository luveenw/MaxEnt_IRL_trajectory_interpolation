"""
Jaguar Movement Grid Analysis
==============================
Analyzes each individual jaguar's GPS telemetry data to:
  1. Characterise inter-fix distance and time-gap distributions (per individual)
  2. Determine an appropriate grid cell size for each individual
  3. Convert raw GPS trajectories into (x, y, time_step) grid sequences
     following Hirakawa et al. (2018) Ecosphere – "Can AI predict animal
     movements? Filling gaps in animal trajectories using inverse reinforcement
     learning" and its Appendix S1.

Grid-cell-size rationale (ecological / analytical):
  - The cell size must be ≥ the median step length so that a typical move
    advances at least one cell (i.e., the grid is fine enough to capture the
    dominant movement scale yet coarse enough to prevent excessive state-space
    size).
  - We use the 10th-percentile non-zero step length as the floor and the median
    non-zero step length as the primary estimate, rounded up to a "nice" value.
  - An additional check uses the typical GPS fix interval: cell size ≥ median
    inter-fix distance computed from typical jaguar travel speed (~3 km/h) times
    the median inter-fix time gap.
  - The chosen cell size is printed per individual in the summary report and
    stored in the output CSV.

Output:
  fig/grid_analysis/           – per-individual distance & time plots + summary plots
  data/grid_trajectories/      – one CSV per individual: (x, y, time_step)
  data/grid_analysis_report.csv – per-individual summary statistics
"""

import os
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")          # non-interactive backend (no display needed)
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import MaxNLocator
import scipy.stats as stats
from pyproj import Geod
from tqdm import tqdm

warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "jaguar_movement_data.csv")
FIG_DIR  = os.path.join(BASE_DIR, "fig", "grid_analysis")
TRAJ_DIR = os.path.join(BASE_DIR, "data", "grid_trajectories")
REPORT_PATH = os.path.join(BASE_DIR, "data", "grid_analysis_report.csv")

os.makedirs(FIG_DIR, exist_ok=True)
os.makedirs(TRAJ_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────
GEOD = Geod(ellps="WGS84")   # geodesic distance calculator

# Candidate cell sizes in km (we will snap each individual to the smallest
# candidate that is ≥ its median step length).
CANDIDATE_CELL_SIZES_KM = [0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0,
                            7.5, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0]

# Maximum acceptable inter-fix gap (hours) before treating as a trajectory break
MAX_GAP_HOURS = 24.0

# ──────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def geodesic_km(lon1, lat1, lon2, lat2):
    """Vectorised geodesic distance in km using the WGS-84 ellipsoid (pyproj.Geod.inv)."""
    _, _, dist_m = GEOD.inv(lon1, lat1, lon2, lat2)
    return np.abs(dist_m) / 1000.0


def choose_cell_size(median_step_km: float, p10_step_km: float) -> float:
    """
    Select the smallest candidate cell size ≥ median_step_km.
    If median_step_km is 0 or very small we fall back to p10_step_km.
    """
    reference = max(median_step_km, p10_step_km, 0.1)
    for cs in CANDIDATE_CELL_SIZES_KM:
        if cs >= reference:
            return cs
    return CANDIDATE_CELL_SIZES_KM[-1]


def latlon_to_grid(lon_arr, lat_arr,
                   lon_min, lat_min,
                   cell_size_km):
    """
    Convert arrays of (lon, lat) to integer (x, y) grid coordinates.

    x increases eastward, y increases northward.
    Cell (0, 0) corresponds to (lon_min, lat_min).

    We approximate 1 degree latitude ≈ 111.32 km and use a locally-corrected
    longitude scale (varies with latitude).
    """
    mean_lat_rad = np.radians(np.mean(lat_arr))
    km_per_deg_lat = 111.32            # nearly constant
    km_per_deg_lon = 111.32 * np.cos(mean_lat_rad)

    dy_km = (lat_arr - lat_min) * km_per_deg_lat
    dx_km = (lon_arr - lon_min) * km_per_deg_lon

    x = np.floor(dx_km / cell_size_km).astype(int)
    y = np.floor(dy_km / cell_size_km).astype(int)
    return x, y


def build_grid_trajectory(sub_df, cell_size_km):
    """
    Convert a sorted, gap-filtered GPS trajectory into a sequence of
    (x, y, time_step) tuples following Hirakawa et al. (2018).

    Steps:
      1. Assign grid coordinates to every GPS fix.
      2. Remove duplicate consecutive grid cells (keep first, per paper).
      3. Replace the wall-clock elapsed time with a discrete time step equal
         to the ordinal position in the de-duplicated movement sequence.

    Returns a DataFrame with columns [x, y, time_step, timestamp,
                                       elapsed_min, lon, lat].
    """
    lons = sub_df["location.long"].values
    lats = sub_df["location.lat"].values

    lon_min, lat_min = lons.min(), lats.min()
    x_arr, y_arr = latlon_to_grid(lons, lats, lon_min, lat_min, cell_size_km)

    result = sub_df[["timestamp", "location.long", "location.lat"]].copy()
    result["x"] = x_arr
    result["y"] = y_arr

    # Elapsed time in minutes from the first fix
    result["elapsed_min"] = (
        (sub_df["timestamp_dt"] - sub_df["timestamp_dt"].iloc[0])
        .dt.total_seconds() / 60.0
    ).values

    # Remove consecutive duplicate grid cells (paper requirement)
    xy_shifted = result[["x", "y"]].shift(1)
    same_as_prev = (result["x"] == xy_shifted["x"]) & (result["y"] == xy_shifted["y"])
    result = result[~same_as_prev].reset_index(drop=True)

    # Discrete time step = movement count from first fix
    result["time_step"] = result.index  # 0-indexed movement number

    return result


def nice_int(x):
    return f"{int(x):,}" if not np.isnan(x) else "NaN"


# ──────────────────────────────────────────────────────────────────────────────
# LOAD DATA
# ──────────────────────────────────────────────────────────────────────────────
print("Loading jaguar GPS data …")
df = pd.read_csv(CSV_PATH, low_memory=False)
df.rename(columns={"individual.local.identifier (ID)": "ID"}, inplace=True)

# Parse timestamps
df["timestamp_dt"] = pd.to_datetime(df["timestamp"], format="%m/%d/%y %H:%M",
                                    errors="coerce")
df.dropna(subset=["timestamp_dt", "location.long", "location.lat"], inplace=True)
df.sort_values(["ID", "timestamp_dt"], inplace=True)
df.reset_index(drop=True, inplace=True)

individuals = sorted(df["ID"].unique())
print(f"  {len(df):,} fixes across {len(individuals)} individuals.")

# ──────────────────────────────────────────────────────────────────────────────
# PER-INDIVIDUAL ANALYSIS
# ──────────────────────────────────────────────────────────────────────────────
report_rows = []

print("\nAnalysing each individual …")
all_step_km   = {}   # pooled step lengths (for summary plot)
all_gap_hr    = {}   # pooled gap hours (for summary plot)

for ind_id in tqdm(individuals, desc="Individuals"):
    sub = df[df["ID"] == ind_id].copy().reset_index(drop=True)
    n_fixes = len(sub)

    # ── Inter-fix distances and time gaps ─────────────────────────────────────
    lons = sub["location.long"].values
    lats = sub["location.lat"].values
    times = sub["timestamp_dt"].values

    step_km = np.full(n_fixes, np.nan)
    gap_hr  = np.full(n_fixes, np.nan)

    if n_fixes > 1:
        step_km[1:] = geodesic_km(lons[:-1], lats[:-1], lons[1:], lats[1:])
        gap_hr[1:]  = (
            pd.to_datetime(times[1:]) - pd.to_datetime(times[:-1])
        ).total_seconds() / 3600.0

    # Remove rows that are gap-break transitions (> MAX_GAP_HOURS apart)
    gap_ok = gap_hr[1:] <= MAX_GAP_HOURS
    valid_steps = step_km[1:][gap_ok]
    valid_gaps  = gap_hr[1:][gap_ok]

    nonzero_steps = valid_steps[valid_steps > 0]

    # ── Statistical summary ───────────────────────────────────────────────────
    def safe_stat(arr, fn):
        try:
            v = fn(arr)
            return float(v) if np.isfinite(v) else np.nan
        except Exception:
            return np.nan

    p10_step   = safe_stat(nonzero_steps, lambda a: np.percentile(a, 10)) if len(nonzero_steps) > 0 else np.nan
    p25_step   = safe_stat(nonzero_steps, lambda a: np.percentile(a, 25)) if len(nonzero_steps) > 0 else np.nan
    med_step   = safe_stat(nonzero_steps, np.median) if len(nonzero_steps) > 0 else np.nan
    mean_step  = safe_stat(nonzero_steps, np.mean) if len(nonzero_steps) > 0 else np.nan
    p75_step   = safe_stat(nonzero_steps, lambda a: np.percentile(a, 75)) if len(nonzero_steps) > 0 else np.nan
    p90_step   = safe_stat(nonzero_steps, lambda a: np.percentile(a, 90)) if len(nonzero_steps) > 0 else np.nan
    p95_step   = safe_stat(nonzero_steps, lambda a: np.percentile(a, 95)) if len(nonzero_steps) > 0 else np.nan
    max_step   = safe_stat(nonzero_steps, np.max) if len(nonzero_steps) > 0 else np.nan
    std_step   = safe_stat(nonzero_steps, np.std) if len(nonzero_steps) > 0 else np.nan

    med_gap    = safe_stat(valid_gaps, np.median) if len(valid_gaps) > 0 else np.nan
    mean_gap   = safe_stat(valid_gaps, np.mean) if len(valid_gaps) > 0 else np.nan
    p90_gap    = safe_stat(valid_gaps, lambda a: np.percentile(a, 90)) if len(valid_gaps) > 0 else np.nan
    max_gap    = safe_stat(valid_gaps, np.max) if len(valid_gaps) > 0 else np.nan

    # Modal gap (dominant fix interval, rounded to nearest 0.5 hr)
    if len(valid_gaps) > 0:
        rounded_gaps = np.round(valid_gaps * 2) / 2  # 0.5-hr bins
        mode_gap = float(stats.mode(rounded_gaps, keepdims=True).mode[0])
    else:
        mode_gap = np.nan

    # Duration of monitoring
    duration_days = (
        (sub["timestamp_dt"].max() - sub["timestamp_dt"].min()).total_seconds() / 86400.0
    )

    # ── Grid cell size determination ──────────────────────────────────────────
    cell_size_km = choose_cell_size(
        med_step if not np.isnan(med_step) else 0.0,
        p10_step if not np.isnan(p10_step) else 0.0,
    )

    # ── Build grid trajectory ─────────────────────────────────────────────────
    grid_traj = build_grid_trajectory(sub, cell_size_km)
    grid_csv  = os.path.join(TRAJ_DIR, f"individual_{ind_id:03d}_grid_trajectory.csv")
    grid_traj[["x", "y", "time_step", "timestamp", "elapsed_min",
                "lon", "lat"] if "lon" in grid_traj.columns
               else ["x", "y", "time_step", "timestamp", "elapsed_min"]
               ].to_csv(grid_csv, index=False)

    # Bounding box of grid
    grid_width  = grid_traj["x"].max() - grid_traj["x"].min() + 1
    grid_height = grid_traj["y"].max() - grid_traj["y"].min() + 1
    n_unique_cells = grid_traj[["x","y"]].drop_duplicates().shape[0]

    # ── Store pooled data for summary plots ───────────────────────────────────
    all_step_km[ind_id]  = nonzero_steps
    all_gap_hr[ind_id]   = valid_gaps

    # ── Record in report ──────────────────────────────────────────────────────
    report_rows.append({
        "ID":                       ind_id,
        "n_fixes":                  n_fixes,
        "n_valid_steps":            len(valid_steps),
        "duration_days":            round(duration_days, 1),
        "monitoring_start":         sub["timestamp_dt"].min().strftime("%Y-%m-%d"),
        "monitoring_end":           sub["timestamp_dt"].max().strftime("%Y-%m-%d"),
        # Step lengths (km)
        "step_p10_km":              round(p10_step, 3) if not np.isnan(p10_step) else np.nan,
        "step_p25_km":              round(p25_step, 3) if not np.isnan(p25_step) else np.nan,
        "step_median_km":           round(med_step, 3) if not np.isnan(med_step) else np.nan,
        "step_mean_km":             round(mean_step, 3) if not np.isnan(mean_step) else np.nan,
        "step_std_km":              round(std_step, 3) if not np.isnan(std_step) else np.nan,
        "step_p75_km":              round(p75_step, 3) if not np.isnan(p75_step) else np.nan,
        "step_p90_km":              round(p90_step, 3) if not np.isnan(p90_step) else np.nan,
        "step_p95_km":              round(p95_step, 3) if not np.isnan(p95_step) else np.nan,
        "step_max_km":              round(max_step, 3) if not np.isnan(max_step) else np.nan,
        # Time gaps (hours)
        "gap_mode_hr":              round(mode_gap, 2) if not np.isnan(mode_gap) else np.nan,
        "gap_median_hr":            round(med_gap, 3) if not np.isnan(med_gap) else np.nan,
        "gap_mean_hr":              round(mean_gap, 3) if not np.isnan(mean_gap) else np.nan,
        "gap_p90_hr":               round(p90_gap, 3) if not np.isnan(p90_gap) else np.nan,
        "gap_max_hr":               round(max_gap, 3) if not np.isnan(max_gap) else np.nan,
        # Grid
        "cell_size_km":             cell_size_km,
        "grid_width_cells":         int(grid_width),
        "grid_height_cells":        int(grid_height),
        "n_unique_grid_cells":      int(n_unique_cells),
        "n_grid_steps":             len(grid_traj),
        "grid_trajectory_file":     os.path.basename(grid_csv),
    })

    # ── Per-individual figure ─────────────────────────────────────────────────
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle(
        f"Individual Jaguar ID {ind_id}  |  {n_fixes:,} fixes  |  "
        f"{duration_days:.0f} days  |  Chosen cell size = {cell_size_km} km",
        fontsize=13, fontweight="bold", y=1.01
    )

    # -- (a) Step-length histogram
    ax = axes[0, 0]
    if len(nonzero_steps) > 1:
        clip = np.percentile(nonzero_steps, 98)
        clipped = nonzero_steps[nonzero_steps <= clip]
        ax.hist(clipped, bins=60, color="#2e86de", edgecolor="white",
                linewidth=0.4, alpha=0.85)
        ax.axvline(p10_step,  color="#e84118", lw=1.5, ls=":",  label=f"P10={p10_step:.2f} km")
        ax.axvline(med_step,  color="#ffa502", lw=2,   ls="--", label=f"Median={med_step:.2f} km")
        ax.axvline(cell_size_km, color="#44bd32", lw=2, ls="-", label=f"Cell={cell_size_km} km")
    ax.set_xlabel("Step length (km) [clipped at P98]", fontsize=10)
    ax.set_ylabel("Count", fontsize=10)
    ax.set_title("(a) Inter-fix Step-Length Distribution", fontsize=11)
    ax.legend(fontsize=8)

    # -- (b) Step-length ECDF
    ax = axes[0, 1]
    if len(nonzero_steps) > 1:
        sorted_s = np.sort(nonzero_steps)
        ecdf_y   = np.arange(1, len(sorted_s)+1) / len(sorted_s)
        clip = np.percentile(sorted_s, 99)
        mask = sorted_s <= clip
        ax.plot(sorted_s[mask], ecdf_y[mask], color="#2e86de", lw=1.8)
        ax.axvline(med_step,  color="#ffa502", lw=1.8, ls="--", label=f"Median={med_step:.2f} km")
        ax.axvline(cell_size_km, color="#44bd32", lw=1.8, ls="-", label=f"Cell={cell_size_km} km")
        ax.axhline(0.50, color="grey", lw=0.8, ls=":")
    ax.set_xlabel("Step length (km) [clipped at P99]", fontsize=10)
    ax.set_ylabel("Cumulative probability", fontsize=10)
    ax.set_title("(b) Step-Length ECDF", fontsize=11)
    ax.set_ylim(0, 1)
    ax.legend(fontsize=8)

    # -- (c) Inter-fix time-gap histogram
    ax = axes[1, 0]
    if len(valid_gaps) > 1:
        clip_g = min(np.percentile(valid_gaps, 98), MAX_GAP_HOURS)
        clipped_g = valid_gaps[valid_gaps <= clip_g]
        ax.hist(clipped_g, bins=60, color="#8e44ad", edgecolor="white",
                linewidth=0.4, alpha=0.85)
        ax.axvline(mode_gap,  color="#e84118", lw=1.5, ls=":",  label=f"Mode={mode_gap:.2f} hr")
        ax.axvline(med_gap,   color="#ffa502", lw=2,   ls="--", label=f"Median={med_gap:.2f} hr")
    ax.set_xlabel("Inter-fix time gap (hours) [clipped at P98]", fontsize=10)
    ax.set_ylabel("Count", fontsize=10)
    ax.set_title("(c) Inter-fix Time-Gap Distribution", fontsize=11)
    ax.legend(fontsize=8)

    # -- (d) Time-gap ECDF
    ax = axes[1, 1]
    if len(valid_gaps) > 1:
        sorted_g = np.sort(valid_gaps)
        ecdf_g   = np.arange(1, len(sorted_g)+1) / len(sorted_g)
        clip_g = min(np.percentile(sorted_g, 99), MAX_GAP_HOURS)
        mask = sorted_g <= clip_g
        ax.plot(sorted_g[mask], ecdf_g[mask], color="#8e44ad", lw=1.8)
        ax.axvline(mode_gap, color="#e84118", lw=1.8, ls=":", label=f"Mode={mode_gap:.2f} hr")
        ax.axvline(med_gap,  color="#ffa502", lw=1.8, ls="--", label=f"Median={med_gap:.2f} hr")
        ax.axhline(0.50, color="grey", lw=0.8, ls=":")
    ax.set_xlabel("Inter-fix time gap (hours) [clipped at P99]", fontsize=10)
    ax.set_ylabel("Cumulative probability", fontsize=10)
    ax.set_title("(d) Inter-fix Time-Gap ECDF", fontsize=11)
    ax.set_ylim(0, 1)
    ax.legend(fontsize=8)

    plt.tight_layout()
    fig_path = os.path.join(FIG_DIR, f"individual_{ind_id:03d}_distributions.png")
    plt.savefig(fig_path, dpi=120, bbox_inches="tight")
    plt.close(fig)

# ──────────────────────────────────────────────────────────────────────────────
# WRITE REPORT CSV
# ──────────────────────────────────────────────────────────────────────────────
report_df = pd.DataFrame(report_rows)
report_df.to_csv(REPORT_PATH, index=False)
print(f"\nPer-individual report saved → {REPORT_PATH}")

# ──────────────────────────────────────────────────────────────────────────────
# POPULATION-LEVEL SUMMARY FIGURES
# ──────────────────────────────────────────────────────────────────────────────
print("Generating population-level summary figures …")

# --- (S1) Pool all step lengths across individuals
pool_steps = np.concatenate([v for v in all_step_km.values() if len(v) > 0])
pool_gaps  = np.concatenate([v for v in all_gap_hr.values()  if len(v) > 0])

fig, axes = plt.subplots(2, 3, figsize=(18, 10))
fig.suptitle("Population-Level Movement Statistics — All 117 Jaguars",
             fontsize=15, fontweight="bold")

# (S1-a) Pooled step-length histogram
ax = axes[0, 0]
clip_s = np.percentile(pool_steps, 98)
ax.hist(pool_steps[pool_steps <= clip_s], bins=80, color="#2e86de",
        edgecolor="white", linewidth=0.3, alpha=0.85)
ax.axvline(np.median(pool_steps), color="#ffa502", lw=2, ls="--",
           label=f"Median={np.median(pool_steps):.2f} km")
ax.set_xlabel("Step length (km) [clipped P98]")
ax.set_ylabel("Count")
ax.set_title("(S1a) Pooled Step-Length Distribution")
ax.legend()

# (S1-b) Pooled step-length ECDF
ax = axes[0, 1]
sorted_pool = np.sort(pool_steps)
ecdf_pool   = np.arange(1, len(sorted_pool)+1) / len(sorted_pool)
clip_s = np.percentile(sorted_pool, 99)
ax.plot(sorted_pool[sorted_pool <= clip_s],
        ecdf_pool[sorted_pool <= clip_s], color="#2e86de", lw=1.5)
ax.axvline(np.median(pool_steps), color="#ffa502", lw=1.8, ls="--",
           label=f"Median={np.median(pool_steps):.2f} km")
ax.set_xlabel("Step length (km) [clipped P99]")
ax.set_ylabel("Cumulative probability")
ax.set_title("(S1b) Pooled Step-Length ECDF")
ax.set_ylim(0, 1)
ax.legend()

# (S1-c) Per-individual median step length (ranked)
medians = report_df.set_index("ID")["step_median_km"].sort_values()
ax = axes[0, 2]
ax.barh(range(len(medians)), medians.values, color="#2e86de", alpha=0.75, height=0.8)
ax.set_xlabel("Median step length (km)")
ax.set_ylabel("Individual (ranked)")
ax.set_title("(S1c) Per-Individual Median Step Length")
ax.set_yticks([])

# (S1-d) Pooled time-gap histogram
ax = axes[1, 0]
clip_g = np.percentile(pool_gaps, 98)
ax.hist(pool_gaps[pool_gaps <= clip_g], bins=80, color="#8e44ad",
        edgecolor="white", linewidth=0.3, alpha=0.85)
ax.axvline(np.median(pool_gaps), color="#ffa502", lw=2, ls="--",
           label=f"Median={np.median(pool_gaps):.2f} hr")
ax.set_xlabel("Inter-fix time gap (hours) [clipped P98]")
ax.set_ylabel("Count")
ax.set_title("(S1d) Pooled Time-Gap Distribution")
ax.legend()

# (S1-e) Pooled time-gap ECDF
ax = axes[1, 1]
sorted_gaps = np.sort(pool_gaps)
ecdf_gaps   = np.arange(1, len(sorted_gaps)+1) / len(sorted_gaps)
clip_g = np.percentile(sorted_gaps, 99)
ax.plot(sorted_gaps[sorted_gaps <= clip_g],
        ecdf_gaps[sorted_gaps <= clip_g], color="#8e44ad", lw=1.5)
ax.axvline(np.median(pool_gaps), color="#ffa502", lw=1.8, ls="--",
           label=f"Median={np.median(pool_gaps):.2f} hr")
ax.set_xlabel("Inter-fix time gap (hours) [clipped P99]")
ax.set_ylabel("Cumulative probability")
ax.set_title("(S1e) Pooled Time-Gap ECDF")
ax.set_ylim(0, 1)
ax.legend()

# (S1-f) Distribution of chosen cell sizes
ax = axes[1, 2]
cell_counts = report_df["cell_size_km"].value_counts().sort_index()
ax.bar(cell_counts.index.astype(str), cell_counts.values,
       color="#44bd32", alpha=0.85, edgecolor="white")
ax.set_xlabel("Grid cell size (km)")
ax.set_ylabel("Number of individuals")
ax.set_title("(S1f) Distribution of Chosen Cell Sizes")
for i, (cs, cnt) in enumerate(zip(cell_counts.index, cell_counts.values)):
    ax.text(i, cnt + 0.3, str(cnt), ha="center", va="bottom", fontsize=9)
ax.tick_params(axis="x", rotation=45)

plt.tight_layout()
summary_fig = os.path.join(FIG_DIR, "population_summary.png")
plt.savefig(summary_fig, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"Population summary figure → {summary_fig}")

# --- (S2) Per-individual mode gap heatmap / bar chart -----------------------
fig, ax = plt.subplots(figsize=(16, 5))
mode_gaps_sorted = report_df.sort_values("gap_mode_hr").reset_index(drop=True)
colors = ["#e84118" if g <= 1 else "#2e86de" if g <= 4 else "#8e44ad"
          for g in mode_gaps_sorted["gap_mode_hr"]]
ax.bar(range(len(mode_gaps_sorted)), mode_gaps_sorted["gap_mode_hr"],
       color=colors, alpha=0.85, edgecolor="white")
ax.set_xlabel("Individual (ranked by modal gap)", fontsize=11)
ax.set_ylabel("Modal inter-fix interval (hours)", fontsize=11)
ax.set_title("Dominant (Modal) GPS Fix Interval per Jaguar\n"
             "Red ≤1 hr | Blue 1–4 hr | Purple >4 hr", fontsize=12)
ax.set_xticks(range(len(mode_gaps_sorted)))
ax.set_xticklabels(mode_gaps_sorted["ID"].astype(str), rotation=90, fontsize=7)
plt.tight_layout()
mode_fig = os.path.join(FIG_DIR, "modal_gap_per_individual.png")
plt.savefig(mode_fig, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"Modal gap figure → {mode_fig}")

# --- (S3) Step vs gap scatter ------------------------------------------------
fig, ax = plt.subplots(figsize=(8, 6))
ax.scatter(report_df["gap_median_hr"], report_df["step_median_km"],
           c=report_df["cell_size_km"], cmap="plasma",
           s=60, alpha=0.75, edgecolors="white", linewidths=0.5)
sc = ax.scatter(report_df["gap_median_hr"], report_df["step_median_km"],
                c=report_df["cell_size_km"], cmap="plasma",
                s=60, alpha=0.85, edgecolors="white", linewidths=0.5)
plt.colorbar(sc, ax=ax, label="Cell size (km)")
ax.set_xlabel("Median inter-fix gap (hours)", fontsize=11)
ax.set_ylabel("Median step length (km)", fontsize=11)
ax.set_title("Median Step Length vs. Median Time Gap\n(color = chosen cell size)", fontsize=12)
plt.tight_layout()
scatter_fig = os.path.join(FIG_DIR, "step_vs_gap_scatter.png")
plt.savefig(scatter_fig, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"Step vs gap scatter → {scatter_fig}")

# ──────────────────────────────────────────────────────────────────────────────
# PRINT CONSOLE SUMMARY TABLE
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "="*110)
print("PER-INDIVIDUAL SUMMARY  (sorted by cell size, then median step length)")
print("="*110)
hdr = (f"{'ID':>4}  {'N_fix':>6}  {'Days':>5}  "
       f"{'P10_step':>8}  {'Med_step':>8}  {'P90_step':>8}  "
       f"{'Mode_gap':>8}  {'Med_gap':>8}  "
       f"{'Cell_km':>7}  {'Grid_WxH':>10}  {'UniqueCell':>10}")
print(hdr)
print("-"*110)
for _, row in report_df.sort_values(["cell_size_km","step_median_km"]).iterrows():
    print(
        f"{int(row['ID']):>4}  "
        f"{int(row['n_fixes']):>6}  "
        f"{row['duration_days']:>5.0f}  "
        f"{row['step_p10_km'] if not pd.isna(row['step_p10_km']) else 'NaN':>8}  "
        f"{row['step_median_km'] if not pd.isna(row['step_median_km']) else 'NaN':>8}  "
        f"{row['step_p90_km'] if not pd.isna(row['step_p90_km']) else 'NaN':>8}  "
        f"{row['gap_mode_hr'] if not pd.isna(row['gap_mode_hr']) else 'NaN':>8}  "
        f"{row['gap_median_hr'] if not pd.isna(row['gap_median_hr']) else 'NaN':>8}  "
        f"{row['cell_size_km']:>7}  "
        f"{str(row['grid_width_cells'])+'x'+str(row['grid_height_cells']):>10}  "
        f"{int(row['n_unique_grid_cells']):>10}"
    )
print("="*110)

print("\n── POPULATION SUMMARY ──────────────────────────────────────────────────")
print(f"  Total fixes:               {len(df):,}")
print(f"  Individuals:               {len(individuals)}")
print(f"  Median step length (all):  {np.median(pool_steps):.3f} km")
print(f"  Median time gap (all):     {np.median(pool_gaps):.3f} hr")
print(f"  Cell sizes used:           {sorted(report_df['cell_size_km'].unique())}")
print(f"\n  Output files:")
print(f"    Report CSV:              {REPORT_PATH}")
print(f"    Grid trajectories:       {TRAJ_DIR}/")
print(f"    Figures:                 {FIG_DIR}/")
print("\nDone ✓")
