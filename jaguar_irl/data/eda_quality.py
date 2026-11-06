# -*- coding: utf-8 -*-
"""Section 1: Data Quality Diagnostics + biome-grouped plots."""
from __future__ import annotations
import logging
from pathlib import Path

import matplotlib.colors as mcolors
from matplotlib.colors import ListedColormap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Unified binary colormap for all temporal-coverage heatmaps:
# cream (#FFF8E1) = no data, dark teal (#1B5E20) = has data
_COVERAGE_CMAP = ListedColormap(["#FFF8E1", "#1B5E20"])
_COVERAGE_NORM = mcolors.BoundaryNorm([0, 0.5, 1], _COVERAGE_CMAP.N)

from .eda_config import (
    COL_ID, COL_TS, COL_STUDY, COL_COUNTRY, COL_BIOME,
    BIOME_ORDER, BIOME_COLORS,
)

logger = logging.getLogger(__name__)

# Study -> ecoregion mapping (path resolved relative to this file, not the CWD)
STUDY_ECOREGION_CSV = (
    Path(__file__).resolve().parent / "../../data/study_area_biome_mapping.csv"
).resolve()
COL_ECOREGION = "biome_ecoregion"


def _load_study_ecoregion_map(csv_path: Path = STUDY_ECOREGION_CSV) -> dict:
    """Return {study_name: biome_ecoregion} from the study-area mapping CSV."""
    mapping = pd.read_csv(csv_path, encoding="utf-8")
    mapping["study_name"] = mapping["study_name"].astype(str).str.strip()
    mapping[COL_ECOREGION] = mapping[COL_ECOREGION].astype(str).str.strip()
    return dict(zip(mapping["study_name"], mapping[COL_ECOREGION]))


def data_quality_diagnostics(df: pd.DataFrame, out_dir: Path) -> dict:
    """Fix counts, durations, fix intervals, temporal coverage, + biome breakdowns."""
    logger.info("Running data quality diagnostics...")
    figs = {}
    grouped = df.groupby(COL_ID)

    # Per-individual stats
    stats = grouped.agg(
        n_fixes=(COL_TS, "count"),
        first_fix=(COL_TS, "min"),
        last_fix=(COL_TS, "max"),
        study=(COL_STUDY, "first"),
        biome=(COL_BIOME, "first"),
    ).reset_index()
    stats["duration_days"] = (stats["last_fix"] - stats["first_fix"]).dt.total_seconds() / 86400

    # --- 1a. Fix count histogram ---
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(stats["n_fixes"], bins=30, edgecolor="black", alpha=0.7, color="#2196F3")
    ax.axvline(stats["n_fixes"].median(), color="red", ls="--",
               label=f'Median={stats["n_fixes"].median():.0f}')
    ax.set_xlabel("Number of GPS Fixes")
    ax.set_ylabel("Number of Individuals")
    ax.set_title(f"Distribution of GPS Fixes per Individual (n={len(stats)})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "1a_fix_count_histogram.png", dpi=150)
    figs["fix_count_histogram"] = fig

    # --- 1b. Tracking duration histogram ---
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(stats["duration_days"], bins=30, edgecolor="black", alpha=0.7, color="#4CAF50")
    ax.axvline(stats["duration_days"].median(), color="red", ls="--",
               label=f'Median={stats["duration_days"].median():.0f} days')
    ax.set_xlabel("Tracking Duration (days)")
    ax.set_ylabel("Number of Individuals")
    ax.set_title("Distribution of Tracking Duration")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "1b_duration_histogram.png", dpi=150)
    figs["duration_histogram"] = fig

    # --- 1c. Fix interval distribution by study ---
    intervals_by_study = {}
    for ind_id, grp in grouped:
        grp_sorted = grp.sort_values(COL_TS)
        diffs_h = grp_sorted[COL_TS].diff().dt.total_seconds() / 3600
        study = grp[COL_STUDY].iloc[0]
        intervals_by_study.setdefault(study, []).extend(diffs_h.dropna().values.tolist())

    fig, ax = plt.subplots(figsize=(14, 6))
    study_names = sorted(intervals_by_study.keys())
    data_to_plot = [np.clip(intervals_by_study[s], 0, 48) for s in study_names]
    bp = ax.boxplot(data_to_plot, tick_labels=[s[:20] for s in study_names],
                    vert=True, patch_artist=True, showfliers=False)
    for patch in bp["boxes"]:
        patch.set_facecolor("#FF9800")
        patch.set_alpha(0.7)
    ax.set_ylabel("Fix Interval (hours, capped at 48h)")
    ax.set_title("Fix Interval Distribution by Study")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(out_dir / "1c_fix_interval_by_study.png", dpi=150)
    figs["fix_interval"] = fig

    # --- 1c2. Fix interval distribution by biome ecoregion (from study mapping CSV) ---
    study_to_eco = _load_study_ecoregion_map()
    unmapped = sorted(s for s in intervals_by_study if str(s).strip() not in study_to_eco)
    if unmapped:
        logger.warning("Studies missing from ecoregion mapping (excluded from 1c2): %s", unmapped)

    intervals_by_eco: dict[str, list] = {}
    for study, vals in intervals_by_study.items():
        eco = study_to_eco.get(str(study).strip())
        if eco is not None:
            intervals_by_eco.setdefault(eco, []).extend(vals)

    # Individuals per ecoregion (for axis labels)
    eco_per_ind = grouped[COL_STUDY].first().astype(str).str.strip().map(study_to_eco)
    n_ind_by_eco = eco_per_ind.value_counts().to_dict()

    # Order ecoregions by median interval so differences in sampling schedule are easy to read
    eco_names = sorted(intervals_by_eco, key=lambda e: np.median(intervals_by_eco[e]))
    data_eco = [np.clip(intervals_by_eco[e], 0, 48) for e in eco_names]
    eco_labels = [f"{e}\n(n={n_ind_by_eco.get(e, 0)})" for e in eco_names]

    fig, ax = plt.subplots(figsize=(max(12, 1.1 * len(eco_names)), 7))
    bp = ax.boxplot(data_eco, tick_labels=eco_labels, vert=True,
                    patch_artist=True, showfliers=False)
    cmap_eco = plt.get_cmap("tab20")
    for k, patch in enumerate(bp["boxes"]):
        patch.set_facecolor(cmap_eco(k % 20))
        patch.set_alpha(0.7)
    ax.set_ylabel("Fix Interval (hours, capped at 48h)")
    ax.set_title("Fix Interval Distribution by Biome Ecoregion (ordered by median)")
    ax.tick_params(axis="x", rotation=60, labelsize=8)
    for lbl in ax.get_xticklabels():
        lbl.set_ha("right")
    fig.tight_layout()
    fig.savefig(out_dir / "1c2_fix_interval_by_ecoregion.png", dpi=150)
    figs["fix_interval_by_ecoregion"] = fig

    # --- 1d. Temporal coverage heatmap ---
    df_copy = df.copy()
    df_copy["year_month"] = df_copy[COL_TS].dt.to_period("M")
    all_months = sorted(df_copy["year_month"].unique())
    all_ids = sorted(df_copy[COL_ID].unique())
    coverage = np.zeros((len(all_ids), len(all_months)))
    month_idx = {m: i for i, m in enumerate(all_months)}
    id_idx = {ind: i for i, ind in enumerate(all_ids)}
    for _, row in df_copy.iterrows():
        coverage[id_idx[row[COL_ID]], month_idx[row["year_month"]]] += 1
    coverage_binary = (coverage > 0).astype(float)

    cmap_cov = _COVERAGE_CMAP
    norm_cov = _COVERAGE_NORM
    fig, ax = plt.subplots(figsize=(18, 10))
    im = ax.imshow(coverage_binary, aspect="auto", cmap=cmap_cov, norm=norm_cov, interpolation="none")
    ax.set_xlabel("Month")
    ax.set_ylabel("Individual ID")
    ax.set_title("Temporal Coverage: Individuals x Months")
    tick_positions = list(range(0, len(all_months), 12))
    ax.set_xticks(tick_positions)
    ax.set_xticklabels([str(all_months[i]) for i in tick_positions], rotation=45)
    ax.set_yticks(range(0, len(all_ids), 5))
    ax.set_yticklabels([str(all_ids[i]) for i in range(0, len(all_ids), 5)])
    cbar = fig.colorbar(im, ax=ax, ticks=[0.25, 0.75], shrink=0.6, pad=0.02)
    cbar.ax.set_yticklabels(["No data", "Has data"])
    fig.tight_layout()
    fig.savefig(out_dir / "1d_temporal_coverage_heatmap.png", dpi=150)
    figs["temporal_coverage"] = fig

    # --- 1e. Fix count by biome ---
    biomes_present = [b for b in BIOME_ORDER if b in stats["biome"].values]
    fig, ax = plt.subplots(figsize=(12, 5))
    data_by_biome = [stats[stats["biome"] == b]["n_fixes"].values for b in biomes_present]
    bp = ax.boxplot(data_by_biome, tick_labels=biomes_present,
                    patch_artist=True, showmeans=True,
                    meanprops=dict(marker="D", markerfacecolor="white", markersize=6))
    for patch, b in zip(bp["boxes"], biomes_present):
        patch.set_facecolor(BIOME_COLORS.get(b, "gray"))
        patch.set_alpha(0.7)
    ax.set_ylabel("Number of GPS Fixes")
    ax.set_title("GPS Fixes per Individual by Biome")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(out_dir / "1e_fix_count_by_biome.png", dpi=150)
    figs["fix_by_biome"] = fig

    # --- 1f. Tracking duration by biome (boxplot) ---
    data_dur = [stats[stats["biome"] == b]["duration_days"].values for b in biomes_present]
    fig, ax = plt.subplots(figsize=(12, 5))
    bp = ax.boxplot(data_dur, tick_labels=biomes_present,
                    patch_artist=True, showmeans=True,
                    meanprops=dict(marker="D", markerfacecolor="white", markersize=6))
    for patch, b in zip(bp["boxes"], biomes_present):
        patch.set_facecolor(BIOME_COLORS.get(b, "gray"))
        patch.set_alpha(0.7)
    ax.set_ylabel("Duration (days)")
    ax.set_title("Tracking Duration by Biome (Boxplot)")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(out_dir / "1f_duration_by_biome_box.png", dpi=150)
    figs["duration_by_biome_box"] = fig

    # --- 1f2. Tracking duration histogram per biome (individual subplots) ---
    n_b = len(biomes_present)
    ncols = min(3, n_b)
    nrows = (n_b + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 4 * nrows), squeeze=False)
    axes_flat = axes.flatten()
    for i, b in enumerate(biomes_present):
        ax = axes_flat[i]
        vals = stats[stats["biome"] == b]["duration_days"].values
        ax.hist(vals, bins=15, alpha=0.8, color=BIOME_COLORS.get(b, "gray"), edgecolor="black")
        ax.axvline(np.median(vals), color="red", ls="--", lw=1, label=f"Median={np.median(vals):.0f}d")
        ax.set_xlabel("Duration (days)")
        ax.set_ylabel("Count")
        ax.set_title(f"{b} (n={len(vals)})", fontsize=10)
        ax.legend(fontsize=7)
    for j in range(i + 1, len(axes_flat)):
        axes_flat[j].set_visible(False)
    fig.suptitle("Tracking Duration Histogram per Biome", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_dir / "1f2_duration_hist_per_biome.png", dpi=150)
    figs["duration_hist_biome"] = fig

    # --- 1g. Fix interval by biome ---
    intervals_by_biome = {}
    for ind_id, grp in grouped:
        grp_sorted = grp.sort_values(COL_TS)
        diffs_h = grp_sorted[COL_TS].diff().dt.total_seconds() / 3600
        biome = grp[COL_BIOME].iloc[0]
        intervals_by_biome.setdefault(biome, []).extend(diffs_h.dropna().values.tolist())
    fig, ax = plt.subplots(figsize=(12, 5))
    data_int = [np.clip(intervals_by_biome.get(b, [0]), 0, 48) for b in biomes_present]
    bp = ax.boxplot(data_int, tick_labels=biomes_present,
                    patch_artist=True, showfliers=False)
    for patch, b in zip(bp["boxes"], biomes_present):
        patch.set_facecolor(BIOME_COLORS.get(b, "gray"))
        patch.set_alpha(0.7)
    ax.set_ylabel("Fix Interval (hours, capped at 48h)")
    ax.set_title("Fix Interval Distribution by Biome")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(out_dir / "1g_fix_interval_by_biome.png", dpi=150)
    figs["interval_by_biome"] = fig

    # --- 1h. Temporal coverage per biome ---
    id_biome = df.groupby(COL_ID)[COL_BIOME].first()
    for b in biomes_present:
        b_ids = sorted([i for i in all_ids if id_biome.get(i) == b])
        if not b_ids:
            continue
        b_cov = np.array([coverage[id_idx[i]] for i in b_ids])
        b_cov_bin = (b_cov > 0).astype(float)
        fig, ax = plt.subplots(figsize=(16, max(3, len(b_ids) * 0.25)))
        im = ax.imshow(b_cov_bin, aspect="auto", cmap=cmap_cov, norm=norm_cov, interpolation="none")
        ax.set_xlabel("Month")
        ax.set_ylabel("Individual ID")
        ax.set_title(f"Temporal Coverage: {b} (n={len(b_ids)})")
        ax.set_xticks(tick_positions)
        ax.set_xticklabels([str(all_months[i]) for i in tick_positions], rotation=45)
        step = max(1, len(b_ids) // 20)
        ax.set_yticks(range(0, len(b_ids), step))
        ax.set_yticklabels([str(b_ids[i]) for i in range(0, len(b_ids), step)])
        cbar = fig.colorbar(im, ax=ax, ticks=[0.25, 0.75], shrink=0.6, pad=0.02)
        cbar.ax.set_yticklabels(["No data", "Has data"])
        fig.tight_layout()
        safe = b.replace("/", "_")
        fig.savefig(out_dir / f"1h_temporal_coverage_{safe}.png", dpi=150)
        figs[f"coverage_{safe}"] = fig

    # --- 1h2. Temporal coverage per country ---
    id_country = df.groupby(COL_ID)[COL_COUNTRY].first()
    for country in sorted(id_country.unique()):
        c_ids = sorted([i for i in all_ids if id_country.get(i) == country])
        if not c_ids:
            continue
        c_cov = np.array([coverage[id_idx[i]] for i in c_ids])
        c_cov_bin = (c_cov > 0).astype(float)
        fig, ax = plt.subplots(figsize=(16, max(3, len(c_ids) * 0.25)))
        im = ax.imshow(c_cov_bin, aspect="auto", cmap=cmap_cov, norm=norm_cov, interpolation="none")
        ax.set_xlabel("Month")
        ax.set_ylabel("Individual ID")
        ax.set_title(f"Temporal Coverage: {country} (n={len(c_ids)})")
        ax.set_xticks(tick_positions)
        ax.set_xticklabels([str(all_months[i]) for i in tick_positions], rotation=45)
        step = max(1, len(c_ids) // 20)
        ax.set_yticks(range(0, len(c_ids), step))
        ax.set_yticklabels([str(c_ids[i]) for i in range(0, len(c_ids), step)])
        cbar = fig.colorbar(im, ax=ax, ticks=[0.25, 0.75], shrink=0.6, pad=0.02)
        cbar.ax.set_yticklabels(["No data", "Has data"])
        fig.tight_layout()
        safe = country.replace(" ", "_")
        fig.savefig(out_dir / f"1h_temporal_coverage_{safe}.png", dpi=150)
        figs[f"coverage_{safe}"] = fig

    # --- 1i. Data density per biome (individual subplots) ---
    monthly_counts = df_copy.groupby(["year_month", COL_BIOME]).size().reset_index(name="n_fixes")
    n_b = len(biomes_present)
    ncols = min(3, n_b)
    nrows = (n_b + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(7 * ncols, 4 * nrows), squeeze=False)
    axes_flat = axes.flatten()
    for i, b in enumerate(biomes_present):
        ax = axes_flat[i]
        sub = monthly_counts[monthly_counts[COL_BIOME] == b]
        periods = sub["year_month"].astype(str)
        ax.fill_between(range(len(periods)), sub["n_fixes"].values,
                        alpha=0.5, color=BIOME_COLORS.get(b, "gray"))
        ax.plot(range(len(periods)), sub["n_fixes"].values, marker=".",
                color=BIOME_COLORS.get(b, "gray"), markersize=3)
        ax.set_title(f"{b}", fontsize=10)
        ax.set_ylabel("Fixes")
        # thin x ticks
        tick_step = max(1, len(periods) // 8)
        ax.set_xticks(range(0, len(periods), tick_step))
        ax.set_xticklabels(periods.values[::tick_step], rotation=45, fontsize=7)
    for j in range(i + 1, len(axes_flat)):
        axes_flat[j].set_visible(False)
    fig.suptitle("Fix Count per Month by Biome (Data Density)", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_dir / "1i_data_density_per_biome.png", dpi=150)
    figs["density_per_biome"] = fig

    # Save stats
    stats.to_csv(out_dir / "individual_stats.csv", index=False)
    plt.close("all")
    return figs
