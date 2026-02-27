# -*- coding: utf-8 -*-
"""Section 8: Cross-Study and Cross-Biome Comparison."""
from __future__ import annotations
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .eda_config import (
    COL_ID, COL_TS, COL_LON, COL_LAT, COL_STUDY, COL_COUNTRY, COL_BIOME,
    BIOME_ORDER, BIOME_COLORS, step_lengths_m,
)

logger = logging.getLogger(__name__)


def cross_study_comparison(df: pd.DataFrame, out_dir: Path) -> dict:
    """Summary statistics by study, country, and biome."""
    logger.info("Computing cross-study comparisons...")
    figs = {}

    # Per-individual stats
    records = []
    for ind_id, grp in df.groupby(COL_ID):
        grp = grp.sort_values(COL_TS)
        study = grp[COL_STUDY].iloc[0]
        country = grp[COL_COUNTRY].iloc[0]
        biome = grp[COL_BIOME].iloc[0]
        n_fixes = len(grp)
        duration = (grp[COL_TS].max() - grp[COL_TS].min()).total_seconds() / 86400
        lons, lats = grp[COL_LON].values, grp[COL_LAT].values
        median_sl = np.median(step_lengths_m(lons, lats)) if len(lons) >= 2 else np.nan
        records.append({
            "id": ind_id, "study": study, "country": country, "biome": biome,
            "n_fixes": n_fixes, "duration_days": duration, "median_step_m": median_sl,
        })
    comp_df = pd.DataFrame(records)

    # Study summary with biome
    study_summary = comp_df.groupby(["study", "biome"]).agg(
        n_individuals=("id", "count"),
        median_fixes=("n_fixes", "median"),
        median_duration=("duration_days", "median"),
        median_step=("median_step_m", "median"),
    ).round(1)
    study_summary.to_csv(out_dir / "study_summary.csv")

    # --- 8a. Country comparison boxplots ---
    countries = sorted(comp_df["country"].unique())
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    for ax, metric, label in zip(axes,
                                  ["n_fixes", "duration_days", "median_step_m"],
                                  ["GPS Fixes", "Duration (days)", "Median Step (m)"]):
        data = [comp_df[comp_df["country"] == c][metric].dropna().values for c in countries]
        bp = ax.boxplot(data, tick_labels=countries, patch_artist=True, showfliers=True)
        colors = plt.cm.Set2(np.linspace(0, 1, len(countries)))
        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
        ax.set_ylabel(label)
        ax.set_title(f"{label} by Country")
        ax.tick_params(axis="x", rotation=30)
    fig.suptitle("Cross-Country Comparison", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_dir / "8a_country_comparison.png", dpi=150)
    figs["country_comparison"] = fig

    # --- 8b. Biome comparison boxplots ---
    biomes_present = [b for b in BIOME_ORDER if b in comp_df["biome"].values]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    for ax, metric, label in zip(axes,
                                  ["n_fixes", "duration_days", "median_step_m"],
                                  ["GPS Fixes", "Duration (days)", "Median Step (m)"]):
        data = [comp_df[comp_df["biome"] == b][metric].dropna().values for b in biomes_present]
        bp = ax.boxplot(data, tick_labels=biomes_present, patch_artist=True,
                        showfliers=True, showmeans=True,
                        meanprops=dict(marker="D", markerfacecolor="white", markersize=5))
        for patch, b in zip(bp["boxes"], biomes_present):
            patch.set_facecolor(BIOME_COLORS.get(b, "gray"))
            patch.set_alpha(0.7)
        ax.set_ylabel(label)
        ax.set_title(f"{label} by Biome")
        ax.tick_params(axis="x", rotation=25)
    fig.suptitle("Cross-Biome Comparison", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_dir / "8b_biome_comparison.png", dpi=150)
    figs["biome_comparison"] = fig

    plt.close("all")
    return figs
