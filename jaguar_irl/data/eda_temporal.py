# -*- coding: utf-8 -*-
"""Section 3: Temporal & Diel Activity Patterns + biome breakdowns."""
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
    BIOME_ORDER, BIOME_COLORS, step_lengths_m,
)

logger = logging.getLogger(__name__)


def _build_step_df(df: pd.DataFrame) -> pd.DataFrame:
    """Build a per-step DataFrame with hour, month, study, biome."""
    records = []
    for ind_id, grp in df.groupby(COL_ID):
        grp = grp.sort_values(COL_TS)
        lons, lats = grp[COL_LON].values, grp[COL_LAT].values
        times = grp[COL_TS].values
        study = grp[COL_STUDY].iloc[0]
        biome = grp[COL_BIOME].iloc[0]
        if len(lons) < 2:
            continue
        sl = step_lengths_m(lons, lats)
        hours = pd.DatetimeIndex(times[:-1]).hour
        months = pd.DatetimeIndex(times[:-1]).month
        for i in range(len(sl)):
            records.append({
                "step_m": sl[i], "hour": hours[i], "month": months[i],
                "study": study, "biome": biome, "id": ind_id,
            })
    return pd.DataFrame(records)


def temporal_diel_patterns(df: pd.DataFrame, out_dir: Path) -> dict:
    """Diel activity, seasonal patterns, fix rate + biome breakdowns."""
    logger.info("Analyzing temporal patterns...")
    figs = {}
    step_df = _build_step_df(df)
    biomes_present = [b for b in BIOME_ORDER if b in step_df["biome"].values]

    # --- 3a. Diel activity: mean step by hour ---
    hourly = step_df.groupby("hour")["step_m"].agg(["mean", "std", "count"]).reset_index()
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(hourly["hour"], hourly["mean"],
           yerr=hourly["std"] / np.sqrt(hourly["count"]),
           color="#00BCD4", alpha=0.8, edgecolor="black", capsize=2)
    ax.set_xlabel("Hour of Day (UTC)")
    ax.set_ylabel("Mean Step Length (m)")
    ax.set_title("Diel Activity Pattern: Mean Step Length by Hour")
    ax.set_xticks(range(24))
    fig.tight_layout()
    fig.savefig(out_dir / "3a_diel_activity.png", dpi=150)
    figs["diel_activity"] = fig

    # --- 3b. Seasonal movement ---
    monthly = step_df.groupby("month")["step_m"].agg(["mean", "std", "count"]).reset_index()
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(monthly["month"], monthly["mean"],
           yerr=monthly["std"] / np.sqrt(monthly["count"]),
           color="#8BC34A", alpha=0.8, edgecolor="black", capsize=2)
    ax.set_xlabel("Month")
    ax.set_ylabel("Mean Step Length (m)")
    ax.set_title("Seasonal Movement Pattern")
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"])
    fig.tight_layout()
    fig.savefig(out_dir / "3b_seasonal_movement.png", dpi=150)
    figs["seasonal"] = fig

    # --- 3c. Fix rate by hour ---
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(df[COL_TS].dt.hour, bins=24, range=(0, 24), edgecolor="black",
            alpha=0.7, color="#607D8B")
    ax.set_xlabel("Hour of Day (UTC)")
    ax.set_ylabel("Number of Fixes")
    ax.set_title("Fix Frequency by Hour (sampling bias check)")
    ax.set_xticks(range(24))
    fig.tight_layout()
    fig.savefig(out_dir / "3c_fix_rate_by_hour.png", dpi=150)
    figs["fix_rate_hour"] = fig

    # --- 3d. Diel by study (top 5) ---
    top_studies = step_df.groupby("study")["step_m"].count().nlargest(5).index.tolist()
    fig, ax = plt.subplots(figsize=(12, 6))
    for study in top_studies:
        sub = step_df[step_df["study"] == study]
        hourly_sub = sub.groupby("hour")["step_m"].mean()
        ax.plot(hourly_sub.index, hourly_sub.values, marker="o", label=study[:25], alpha=0.8)
    ax.set_xlabel("Hour of Day (UTC)")
    ax.set_ylabel("Mean Step Length (m)")
    ax.set_title("Diel Activity by Study (Top 5)")
    ax.legend(fontsize=8)
    ax.set_xticks(range(24))
    fig.tight_layout()
    fig.savefig(out_dir / "3d_diel_by_study.png", dpi=150)
    figs["diel_by_study"] = fig

    # --- 3e. Diel activity by biome (overlaid) ---
    fig, ax = plt.subplots(figsize=(12, 6))
    for b in biomes_present:
        sub = step_df[step_df["biome"] == b]
        hourly_b = sub.groupby("hour")["step_m"].mean()
        ax.plot(hourly_b.index, hourly_b.values, marker="o",
                color=BIOME_COLORS.get(b, "gray"), label=b, alpha=0.8, lw=2)
    ax.set_xlabel("Hour of Day (UTC)")
    ax.set_ylabel("Mean Step Length (m)")
    ax.set_title("Diel Activity by Biome")
    ax.legend(fontsize=8)
    ax.set_xticks(range(24))
    fig.tight_layout()
    fig.savefig(out_dir / "3e_diel_by_biome.png", dpi=150)
    figs["diel_biome"] = fig

    # --- 3f. Seasonal movement by biome ---
    fig, ax = plt.subplots(figsize=(14, 5))
    width = 0.8 / max(len(biomes_present), 1)
    for i, b in enumerate(biomes_present):
        sub = step_df[step_df["biome"] == b]
        monthly_b = sub.groupby("month")["step_m"].mean()
        offset = (i - len(biomes_present) / 2) * width
        ax.bar(monthly_b.index + offset, monthly_b.values, width=width,
               color=BIOME_COLORS.get(b, "gray"), label=b, alpha=0.8)
    ax.set_xlabel("Month")
    ax.set_ylabel("Mean Step Length (m)")
    ax.set_title("Seasonal Movement by Biome")
    ax.legend(fontsize=7)
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"])
    fig.tight_layout()
    fig.savefig(out_dir / "3f_seasonal_by_biome.png", dpi=150)
    figs["seasonal_biome"] = fig

    # --- 3g. Fix rate by hour per biome ---
    fig, ax = plt.subplots(figsize=(12, 5))
    for b in biomes_present:
        sub = df[df[COL_BIOME] == b]
        hours = sub[COL_TS].dt.hour
        counts, _ = np.histogram(hours, bins=24, range=(0, 24))
        ax.plot(range(24), counts, marker=".", color=BIOME_COLORS.get(b, "gray"),
                label=b, alpha=0.8)
    ax.set_xlabel("Hour of Day (UTC)")
    ax.set_ylabel("Number of Fixes")
    ax.set_title("Fix Rate by Hour per Biome")
    ax.legend(fontsize=7)
    ax.set_xticks(range(24))
    fig.tight_layout()
    fig.savefig(out_dir / "3g_fix_rate_by_biome.png", dpi=150)
    figs["fix_rate_biome"] = fig

    # --- 3h. Diel per biome subplots (log option) ---
    n_biomes = len(biomes_present)
    ncols = min(3, n_biomes)
    nrows = (n_biomes + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 4 * nrows), squeeze=False)
    axes_flat = axes.flatten()
    for i, b in enumerate(biomes_present):
        ax = axes_flat[i]
        sub = step_df[step_df["biome"] == b]
        hourly_b = sub.groupby("hour")["step_m"].agg(["mean", "std", "count"]).reset_index()
        ax.bar(hourly_b["hour"], hourly_b["mean"],
               yerr=hourly_b["std"] / np.sqrt(hourly_b["count"]),
               color=BIOME_COLORS.get(b, "gray"), alpha=0.8, edgecolor="black", capsize=2)
        ax.set_title(f"{b} (n={int(hourly_b['count'].sum()):,} steps)", fontsize=10)
        ax.set_xlabel("Hour (UTC)", fontsize=8)
        ax.set_ylabel("Mean Step (m)", fontsize=8)
        ax.set_yscale("log")
        ax.set_xticks(range(0, 24, 3))
    for j in range(i + 1, len(axes_flat)):
        axes_flat[j].set_visible(False)
    fig.suptitle("Diel Activity per Biome (log-scale)", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_dir / "3h_diel_per_biome_log.png", dpi=150)
    figs["diel_per_biome_log"] = fig

    plt.close("all")
    return figs
