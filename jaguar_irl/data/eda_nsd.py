# -*- coding: utf-8 -*-
"""Section 7: Net Squared Displacement with biome labels and explanation."""
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
    BIOME_COLORS, m_per_deg_lon, M_PER_DEG_LAT,
)

logger = logging.getLogger(__name__)

# Section description for the HTML report
NSD_DESCRIPTION = """
<div style="background:#f5f5f5;padding:15px;border-radius:8px;margin:10px 0">
<h3>What is Net Squared Displacement (NSD)?</h3>
<p><b>Net Squared Displacement</b> measures the straight-line distance squared from
an animal's starting location to each subsequent location over time. The shape of the
NSD(t) curve reveals the animal's gross movement pattern:</p>
<ul>
<li><b style="color:#4CAF50">Sedentary</b>: NSD stays near zero throughout — the
animal barely moves from its origin.</li>
<li><b style="color:#2196F3">Resident</b>: NSD fluctuates but returns to low values
repeatedly — the animal has a stable home range and revisits areas near its start.</li>
<li><b style="color:#F44336">Disperser</b>: NSD increases monotonically or reaches
a high plateau and stays there — the animal has permanently moved away from its origin.</li>
</ul>
<p><b>Classification logic used here (heuristic)</b>: For each individual, we compare
the median NSD over the last 10 fixes to the maximum NSD observed. If the maximum NSD
is very small (< 1 km²), the animal is <em>Sedentary</em>. If the final NSD is
> 50% of the maximum, the animal is a <em>Disperser</em> (it ended far from its start).
Otherwise, it is a <em>Resident</em> (it returned toward its origin).</p>
<p><em>Reference: Bunnefeld et al. (2011); Börger & Fryxell (2012)</em></p>
</div>
"""


def net_squared_displacement(df: pd.DataFrame, out_dir: Path, n_sample: int = 12) -> dict:
    """NSD time series with biome labels in subplot titles."""
    logger.info("Computing net squared displacement...")
    figs = {}

    counts = df.groupby(COL_ID).size().nlargest(n_sample)
    sample_ids = counts.index.tolist()
    id_biome = df.groupby(COL_ID)[COL_BIOME].first()
    id_study = df.groupby(COL_ID)[COL_STUDY].first()

    fig, axes = plt.subplots(3, 4, figsize=(20, 12))
    axes_flat = axes.flatten()

    for i, ind_id in enumerate(sample_ids):
        grp = df[df[COL_ID] == ind_id].sort_values(COL_TS)
        lons, lats = grp[COL_LON].values, grp[COL_LAT].values
        times = grp[COL_TS].values
        biome = id_biome.get(ind_id, "Unknown")
        study = id_study.get(ind_id, "Unknown")

        lat_mean = lats.mean()
        dx = (lons - lons[0]) * m_per_deg_lon(lat_mean)
        dy = (lats - lats[0]) * M_PER_DEG_LAT
        nsd = (dx**2 + dy**2) / 1e6  # km²

        t0 = times[0].astype("datetime64[s]").astype(float)
        days = (times.astype("datetime64[s]").astype(float) - t0) / 86400

        # Heuristic classification
        if len(nsd) > 10:
            final_nsd = np.median(nsd[-10:])
            max_nsd = np.max(nsd)
            if max_nsd < 1:
                mode, color = "Sedentary", "#4CAF50"
            elif final_nsd > 0.5 * max_nsd:
                mode, color = "Disperser", "#F44336"
            else:
                mode, color = "Resident", "#2196F3"
        else:
            mode, color = "Unknown", "gray"

        ax = axes_flat[i]
        ax.plot(days, nsd, color=color, alpha=0.7, lw=1)
        ax.set_title(f"ID {ind_id} ({mode})\n{biome} — {study[:20]}", fontsize=8)
        ax.set_xlabel("Days", fontsize=7)
        if i % 4 == 0:
            ax.set_ylabel("NSD (km²)", fontsize=8)

    for j in range(i + 1, len(axes_flat)):
        axes_flat[j].set_visible(False)

    fig.suptitle("Net Squared Displacement Time Series", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_dir / "7a_nsd_time_series.png", dpi=150)
    figs["nsd"] = fig

    plt.close("all")
    return figs
