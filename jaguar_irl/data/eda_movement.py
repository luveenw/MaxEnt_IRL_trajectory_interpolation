# -*- coding: utf-8 -*-
"""Section 2: Movement Metrics + biome-grouped plots."""
from __future__ import annotations
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .eda_config import (
    COL_ID, COL_TS, COL_LON, COL_LAT, COL_STUDY, COL_BIOME,
    BIOME_ORDER, BIOME_COLORS, step_lengths_m, turning_angles,
)

logger = logging.getLogger(__name__)


def movement_metrics(df: pd.DataFrame, out_dir: Path) -> dict:
    """Step length, turning angle, speed distributions + biome breakdowns."""
    logger.info("Computing movement metrics...")
    figs = {}

    all_steps, all_angles, all_speeds = [], [], []
    biome_steps: dict[str, list] = {}
    biome_angles: dict[str, list] = {}
    biome_speeds: dict[str, list] = {}

    for ind_id, grp in df.groupby(COL_ID):
        grp = grp.sort_values(COL_TS)
        lons, lats = grp[COL_LON].values, grp[COL_LAT].values
        times = grp[COL_TS].values
        biome = grp[COL_BIOME].iloc[0]
        if len(lons) < 3:
            continue
        sl = step_lengths_m(lons, lats)
        ta = turning_angles(lons, lats)
        dt_h = np.diff(times.astype("datetime64[s]").astype(float)) / 3600
        dt_h[dt_h <= 0] = np.nan
        speed = sl / dt_h

        all_steps.extend(sl)
        all_angles.extend(ta)
        valid_speed = speed[~np.isnan(speed)]
        all_speeds.extend(valid_speed)

        biome_steps.setdefault(biome, []).extend(sl)
        biome_angles.setdefault(biome, []).extend(ta)
        biome_speeds.setdefault(biome, []).extend(valid_speed)

    all_steps = np.array(all_steps)
    all_angles = np.array(all_angles)
    all_speeds = np.array(all_speeds)

    # --- 2a. Step length distribution ---
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].hist(all_steps[all_steps < 10000], bins=100, edgecolor="black",
                 alpha=0.7, color="#9C27B0", density=True)
    axes[0].set_xlabel("Step Length (m)")
    axes[0].set_ylabel("Density")
    axes[0].set_title("Step Length Distribution (< 10 km)")
    axes[1].hist(np.log10(all_steps[all_steps > 0] + 1), bins=80,
                 edgecolor="black", alpha=0.7, color="#673AB7", density=True)
    axes[1].set_xlabel("log10(Step Length + 1) [m]")
    axes[1].set_ylabel("Density")
    axes[1].set_title("Log-Scale Step Length Distribution")
    fig.suptitle(f"Pooled Step Lengths (n={len(all_steps):,} steps)", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_dir / "2a_step_length_distribution.png", dpi=150)
    figs["step_length"] = fig

    # --- 2b. Turning angle rose diagram ---
    fig, ax = plt.subplots(subplot_kw={"projection": "polar"}, figsize=(7, 7))
    angles_wrapped = all_angles % (2 * np.pi)
    ax.hist(angles_wrapped, bins=36, density=True, alpha=0.7, color="#E91E63")
    ax.set_title("Turning Angle Distribution", pad=20)
    fig.tight_layout()
    fig.savefig(out_dir / "2b_turning_angle_rose.png", dpi=150)
    figs["turning_angle"] = fig

    # --- 2c. Step length vs turning angle ---
    sample_n = min(50000, len(all_angles))
    rng = np.random.default_rng(42)
    idx = rng.choice(len(all_angles), sample_n, replace=False) if len(all_angles) > sample_n else np.arange(len(all_angles))
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(np.abs(all_angles[idx]), all_steps[idx], alpha=0.05, s=2, color="#795548")
    ax.set_xlabel("|Turning Angle| (radians)")
    ax.set_ylabel("Step Length (m)")
    ax.set_title("Step Length vs. Absolute Turning Angle")
    ax.set_ylim(0, np.percentile(all_steps, 99))
    fig.tight_layout()
    fig.savefig(out_dir / "2c_step_vs_angle.png", dpi=150)
    figs["step_vs_angle"] = fig

    # --- 2d. Speed distribution ---
    fig, ax = plt.subplots(figsize=(10, 5))
    speeds_capped = all_speeds[all_speeds < 5000]
    ax.hist(speeds_capped, bins=80, edgecolor="black", alpha=0.7, color="#FF5722", density=True)
    ax.set_xlabel("Speed (m/h)")
    ax.set_ylabel("Density")
    ax.set_title(f"Speed Distribution (< 5 km/h, n={len(speeds_capped):,})")
    fig.tight_layout()
    fig.savefig(out_dir / "2d_speed_distribution.png", dpi=150)
    figs["speed"] = fig

    # --- 2e. Step length per biome (individual subplots) ---
    biomes_present = [b for b in BIOME_ORDER if b in biome_steps]
    n_b = len(biomes_present)
    ncols = min(3, n_b)
    nrows = (n_b + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 4 * nrows), squeeze=False)
    axes_flat = axes.flatten()
    for i, b in enumerate(biomes_present):
        ax = axes_flat[i]
        vals = np.array(biome_steps[b])
        vals_log = np.log10(vals[vals > 0] + 1)
        ax.hist(vals_log, bins=50, alpha=0.8, density=True,
                color=BIOME_COLORS.get(b, "gray"), edgecolor="black", linewidth=0.3)
        ax.axvline(np.median(vals_log), color="red", ls="--", lw=1,
                   label=f"Median={np.median(vals_log):.2f}")
        ax.set_xlabel("log10(Step Length + 1) [m]")
        ax.set_ylabel("Density")
        ax.set_title(f"{b} (n={len(vals):,})", fontsize=10)
        ax.legend(fontsize=7)
    for j in range(i + 1, len(axes_flat)):
        axes_flat[j].set_visible(False)
    fig.suptitle("Step Length Distribution per Biome", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_dir / "2e_step_length_per_biome.png", dpi=150)
    figs["step_per_biome"] = fig

    # --- 2f. Turning angle rose per biome ---
    n_biomes = len(biomes_present)
    ncols = min(3, n_biomes)
    nrows = (n_biomes + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, subplot_kw={"projection": "polar"},
                             figsize=(5 * ncols, 5 * nrows))
    axes_flat = np.atleast_1d(axes).flatten()
    for i, b in enumerate(biomes_present):
        ax = axes_flat[i]
        vals = np.array(biome_angles[b]) % (2 * np.pi)
        ax.hist(vals, bins=36, density=True, alpha=0.7, color=BIOME_COLORS.get(b, "gray"))
        ax.set_title(b, fontsize=10, pad=10)
    for j in range(i + 1, len(axes_flat)):
        axes_flat[j].set_visible(False)
    fig.suptitle("Turning Angle Distribution by Biome", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_dir / "2f_turning_angle_by_biome.png", dpi=150)
    figs["angle_by_biome"] = fig

    # --- 2g. Step vs angle per biome (individual subplots) ---
    step99 = np.percentile(all_steps, 99)
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 5 * nrows), squeeze=False)
    axes_flat = axes.flatten()
    for i, b in enumerate(biomes_present):
        ax = axes_flat[i]
        b_steps = np.array(biome_steps[b])
        b_angles = np.array(biome_angles[b])
        n_samp = min(8000, len(b_angles))
        if n_samp == 0:
            continue
        idx_b = rng.choice(len(b_angles), n_samp, replace=False)
        ax.scatter(np.abs(b_angles[idx_b]), b_steps[idx_b], alpha=0.08, s=3,
                   color=BIOME_COLORS.get(b, "gray"))
        ax.set_xlabel("|Turning Angle| (rad)")
        ax.set_ylabel("Step Length (m)")
        ax.set_ylim(0, step99)
        ax.set_title(f"{b} (n={n_samp:,})", fontsize=10)
    for j in range(i + 1, len(axes_flat)):
        axes_flat[j].set_visible(False)
    fig.suptitle("Step Length vs. Turning Angle per Biome", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_dir / "2g_step_vs_angle_per_biome.png", dpi=150)
    figs["step_angle_per_biome"] = fig

    # --- 2h. Speed by biome (boxplot) ---
    fig, ax = plt.subplots(figsize=(12, 5))
    data_spd = [np.clip(biome_speeds.get(b, [0]), 0, 5000) for b in biomes_present]
    bp = ax.boxplot(data_spd, tick_labels=biomes_present,
                    patch_artist=True, showmeans=True, showfliers=False,
                    meanprops=dict(marker="D", markerfacecolor="white", markersize=6))
    for patch, b in zip(bp["boxes"], biomes_present):
        patch.set_facecolor(BIOME_COLORS.get(b, "gray"))
        patch.set_alpha(0.7)
    ax.set_ylabel("Speed (m/h)")
    ax.set_title("Speed by Biome (Boxplot)")
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(out_dir / "2h_speed_by_biome_box.png", dpi=150)
    figs["speed_box_biome"] = fig

    # --- 2h2. Speed histogram per biome (individual subplots) ---
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 4 * nrows), squeeze=False)
    axes_flat = axes.flatten()
    for i, b in enumerate(biomes_present):
        ax = axes_flat[i]
        vals = np.array(biome_speeds.get(b, []))
        vals = vals[(vals > 0) & (vals < 3000)]
        ax.hist(vals, bins=40, alpha=0.8, density=True,
                color=BIOME_COLORS.get(b, "gray"), edgecolor="black", linewidth=0.3)
        ax.axvline(np.median(vals) if len(vals) > 0 else 0, color="red", ls="--", lw=1,
                   label=f"Median={np.median(vals):.0f} m/h" if len(vals) > 0 else "")
        ax.set_xlabel("Speed (m/h)")
        ax.set_ylabel("Density")
        ax.set_title(f"{b} (n={len(vals):,})", fontsize=10)
        ax.legend(fontsize=7)
    for j in range(i + 1, len(axes_flat)):
        axes_flat[j].set_visible(False)
    fig.suptitle("Speed Distribution per Biome", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_dir / "2h2_speed_hist_per_biome.png", dpi=150)
    figs["speed_hist_biome"] = fig

    plt.close("all")
    return figs
