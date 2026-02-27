# -*- coding: utf-8 -*-
"""Sections 4-6: Variograms, Home Range (MCP), Spatial Overlap Network."""
from __future__ import annotations
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.spatial import ConvexHull
from shapely.geometry import MultiPoint
import networkx as nx

from .eda_config import (
    COL_ID, COL_TS, COL_LON, COL_LAT, COL_STUDY, COL_COUNTRY, COL_BIOME,
    BIOME_ORDER, BIOME_COLORS, m_per_deg_lon, M_PER_DEG_LAT,
)

logger = logging.getLogger(__name__)


# ================================================================== #
#  4. SPATIAL AUTOCORRELATION (VARIOGRAMS)
# ================================================================== #

def spatial_autocorrelation(df: pd.DataFrame, out_dir: Path, n_sample: int = 10) -> dict:
    """Empirical variograms with biome type in subplot titles."""
    logger.info("Computing spatial autocorrelation (variograms)...")
    figs = {}
    counts = df.groupby(COL_ID).size().nlargest(n_sample)
    sample_ids = counts.index.tolist()
    # Get biome for each
    id_biome = df.groupby(COL_ID)[COL_BIOME].first()

    fig, axes = plt.subplots(2, 5, figsize=(22, 8), sharey=False)
    axes_flat = axes.flatten()

    for i, ind_id in enumerate(sample_ids):
        grp = df[df[COL_ID] == ind_id].sort_values(COL_TS)
        lons, lats = grp[COL_LON].values, grp[COL_LAT].values
        times = grp[COL_TS].values
        biome = id_biome.get(ind_id, "Unknown")

        dx = (lons - lons[0]) * m_per_deg_lon(lats.mean())
        dy = (lats - lats[0]) * M_PER_DEG_LAT
        t0 = times[0].astype("datetime64[s]").astype(float)
        t_hours = (times.astype("datetime64[s]").astype(float) - t0) / 3600

        max_lag = min(t_hours[-1], 24 * 90)
        n_bins = 50
        bin_edges = np.linspace(0, max_lag, n_bins + 1)
        semivar = np.zeros(n_bins)
        counts_bin = np.zeros(n_bins, dtype=int)

        for j in range(len(t_hours)):
            for k in range(j + 1, min(j + 200, len(t_hours))):
                lag = t_hours[k] - t_hours[j]
                if lag > max_lag:
                    break
                b_idx = int(lag / max_lag * n_bins)
                if b_idx >= n_bins:
                    b_idx = n_bins - 1
                diff = (dx[k] - dx[j])**2 + (dy[k] - dy[j])**2
                semivar[b_idx] += diff
                counts_bin[b_idx] += 1

        valid = counts_bin > 0
        semivar[valid] /= (2 * counts_bin[valid])
        lag_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

        ax = axes_flat[i]
        ax.plot(lag_centers[valid] / 24, semivar[valid] / 1e6, "o-",
                markersize=3, color=BIOME_COLORS.get(biome, "#3F51B5"), alpha=0.8)
        ax.set_title(f"ID {ind_id}\n{biome}", fontsize=9)
        ax.set_xlabel("Lag (days)", fontsize=8)
        if i % 5 == 0:
            ax.set_ylabel("Semivariance (km²)", fontsize=8)

    fig.suptitle("Empirical Variograms (Top 10 by Fix Count)", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_dir / "4a_variograms.png", dpi=150)
    figs["variograms"] = fig
    plt.close("all")
    return figs


# ================================================================== #
#  5. HOME RANGE ESTIMATION (MCP) — PER-COUNTRY MAPS
# ================================================================== #

def home_range_estimation(df: pd.DataFrame, out_dir: Path) -> dict:
    """MCP home ranges + per-country maps."""
    logger.info("Estimating home ranges (MCP)...")
    figs = {}

    hr_data = []
    all_hulls = []  # (id, study, biome, country, hull_lons, hull_lats)

    for ind_id, grp in df.groupby(COL_ID):
        lons, lats = grp[COL_LON].values, grp[COL_LAT].values
        study = grp[COL_STUDY].iloc[0]
        biome = grp[COL_BIOME].iloc[0]
        country = grp[COL_COUNTRY].iloc[0]
        if len(lons) < 5:
            continue
        lat_mean = lats.mean()
        x_m = lons * m_per_deg_lon(lat_mean)
        y_m = lats * M_PER_DEG_LAT
        points = np.column_stack([x_m, y_m])
        try:
            hull_100 = ConvexHull(points)
            area_100_km2 = hull_100.volume / 1e6
            centroid = points.mean(axis=0)
            dists = np.linalg.norm(points - centroid, axis=1)
            threshold = np.percentile(dists, 95)
            core = points[dists <= threshold]
            area_95_km2 = ConvexHull(core).volume / 1e6 if len(core) >= 3 else np.nan
            hr_data.append({
                "id": ind_id, "study": study, "biome": biome, "country": country,
                "n_fixes": len(lons), "mcp100_km2": area_100_km2,
                "mcp95_km2": area_95_km2, "lon_centroid": lons.mean(),
                "lat_centroid": lat_mean,
            })
            all_hulls.append((ind_id, study, biome, country,
                              lons[hull_100.vertices], lats[hull_100.vertices]))
        except Exception as e:
            logger.warning("MCP failed for ID %s: %s", ind_id, e)

    hr_df = pd.DataFrame(hr_data)
    hr_df.to_csv(out_dir / "home_range_mcp.csv", index=False)

    # --- 5a. Home range by study (boxplot) ---
    fig, ax = plt.subplots(figsize=(14, 6))
    studies_sorted = hr_df.groupby("study")["mcp95_km2"].median().sort_values().index
    data_by_study = [hr_df[hr_df["study"] == s]["mcp95_km2"].dropna().values for s in studies_sorted]
    bp = ax.boxplot(data_by_study, tick_labels=[s[:20] for s in studies_sorted],
                    vert=True, patch_artist=True, showfliers=True)
    colors = plt.cm.Set3(np.linspace(0, 1, len(studies_sorted)))
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.8)
    ax.set_ylabel("95% MCP Area (km²)")
    ax.set_title("Home Range Size by Study")
    ax.tick_params(axis="x", rotation=45)
    ax.set_yscale("log")
    fig.tight_layout()
    fig.savefig(out_dir / "5a_home_range_by_study.png", dpi=150)
    figs["hr_by_study"] = fig

    # --- 5b. Per-country MCP maps ---
    countries = sorted(set(c for _, _, _, c, _, _ in all_hulls))
    for country in countries:
        country_hulls = [(i, s, b, lo, la) for i, s, b, c, lo, la in all_hulls if c == country]
        if not country_hulls:
            continue
        fig, ax = plt.subplots(figsize=(12, 10))
        biomes_in_country = set()
        for ind_id, study, biome, hull_lons, hull_lats in country_hulls:
            biomes_in_country.add(biome)
            closed_lons = np.append(hull_lons, hull_lons[0])
            closed_lats = np.append(hull_lats, hull_lats[0])
            color = BIOME_COLORS.get(biome, "gray")
            ax.fill(closed_lons, closed_lats, alpha=0.2, color=color)
            ax.plot(closed_lons, closed_lats, alpha=0.6, lw=0.8, color=color)
            # label centroid
            ax.text(hull_lons.mean(), hull_lats.mean(), str(ind_id),
                    fontsize=5, ha="center", va="center", alpha=0.7)
        # Legend
        from matplotlib.patches import Patch
        patches = [Patch(facecolor=BIOME_COLORS.get(b, "gray"), alpha=0.5, label=b)
                   for b in sorted(biomes_in_country)]
        ax.legend(handles=patches, fontsize=8, loc="lower left")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.set_title(f"Jaguar Home Ranges — {country} (100% MCP, n={len(country_hulls)})")
        ax.set_aspect("equal")
        fig.tight_layout()
        safe_name = country.replace(" ", "_")
        fig.savefig(out_dir / f"5b_mcp_map_{safe_name}.png", dpi=150)
        figs[f"mcp_map_{safe_name}"] = fig

    plt.close("all")
    return figs


# ================================================================== #
#  6. SPATIAL OVERLAP NETWORK — PER-COUNTRY
# ================================================================== #

def spatial_overlap_network(df: pd.DataFrame, out_dir: Path) -> dict:
    """Per-country overlap networks + cross-country callout."""
    logger.info("Computing spatial overlap network...")
    figs = {}

    # Build MCP polygons
    polygons, studies, biomes, countries_map = {}, {}, {}, {}
    for ind_id, grp in df.groupby(COL_ID):
        lons, lats = grp[COL_LON].values, grp[COL_LAT].values
        if len(lons) < 5:
            continue
        mp = MultiPoint(list(zip(lons, lats)))
        hull = mp.convex_hull
        if hull.geom_type == "Polygon" and hull.area > 0:
            polygons[ind_id] = hull
            studies[ind_id] = grp[COL_STUDY].iloc[0]
            biomes[ind_id] = grp[COL_BIOME].iloc[0]
            countries_map[ind_id] = grp[COL_COUNTRY].iloc[0]

    # Compute all pairwise overlaps
    ids_list = list(polygons.keys())
    all_edges = []
    for i in range(len(ids_list)):
        for j in range(i + 1, len(ids_list)):
            id_a, id_b = ids_list[i], ids_list[j]
            poly_a, poly_b = polygons[id_a], polygons[id_b]
            if not poly_a.intersects(poly_b):
                continue
            intersection = poly_a.intersection(poly_b).area
            union = poly_a.union(poly_b).area
            if union > 0:
                jaccard = intersection / union
                if jaccard > 0.01:
                    cross_country = countries_map[id_a] != countries_map[id_b]
                    all_edges.append((id_a, id_b, jaccard, cross_country))

    # Save overlap matrix
    if all_edges:
        ov_df = pd.DataFrame(all_edges, columns=["id_a", "id_b", "jaccard", "cross_country"])
        ov_df.to_csv(out_dir / "overlap_matrix.csv", index=False)

    # Per-country network plots
    all_countries = sorted(set(countries_map.values()))
    for country in all_countries:
        country_ids = {k for k, v in countries_map.items() if v == country}
        G = nx.Graph()
        for ind_id in country_ids:
            if ind_id in polygons:
                G.add_node(ind_id, biome=biomes[ind_id])
        for id_a, id_b, w, cross in all_edges:
            if id_a in country_ids and id_b in country_ids:
                G.add_edge(id_a, id_b, weight=w)
            elif id_a in country_ids or id_b in country_ids:
                # cross-country edge: add with flag
                G.add_node(id_a, biome=biomes.get(id_a, "?"))
                G.add_node(id_b, biome=biomes.get(id_b, "?"))
                G.add_edge(id_a, id_b, weight=w, cross_country=True)

        fig, ax = plt.subplots(figsize=(12, 10))
        if len(G.edges) > 0:
            pos = nx.spring_layout(G, k=2, seed=42, weight="weight")
            node_colors = [BIOME_COLORS.get(biomes.get(n, ""), "gray") for n in G.nodes()]
            # Separate within-country and cross-country edges
            within = [(u, v) for u, v, d in G.edges(data=True) if not d.get("cross_country")]
            cross = [(u, v) for u, v, d in G.edges(data=True) if d.get("cross_country")]
            w_within = [G[u][v]["weight"] * 5 for u, v in within]
            w_cross = [G[u][v]["weight"] * 5 for u, v in cross]

            nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors,
                                   node_size=120, alpha=0.8, edgecolors="black", linewidths=0.5)
            if within:
                nx.draw_networkx_edges(G, pos, edgelist=within, ax=ax,
                                       width=w_within, alpha=0.4, edge_color="gray")
            if cross:
                nx.draw_networkx_edges(G, pos, edgelist=cross, ax=ax,
                                       width=w_cross, alpha=0.8, edge_color="red",
                                       style="dashed")
            nx.draw_networkx_labels(G, pos, ax=ax, font_size=6)

            from matplotlib.patches import Patch
            from matplotlib.lines import Line2D
            biome_set = sorted(set(biomes.get(n, "") for n in G.nodes()))
            patches = [Patch(facecolor=BIOME_COLORS.get(b, "gray"), label=b) for b in biome_set if b]
            if cross:
                patches.append(Line2D([0], [0], color="red", ls="--", lw=2,
                                      label="Cross-country overlap"))
            # Edge-thickness reference lines (Jaccard × 5 = display width)
            for ref_j in (0.05, 0.25, 0.50):
                patches.append(Line2D([0], [0], color="gray", lw=ref_j * 5,
                                      label=f"Jaccard = {ref_j:.0%}"))
            ax.legend(handles=patches, fontsize=7, loc="upper left")
        else:
            ax.text(0.5, 0.5, "No spatial overlaps detected",
                    ha="center", va="center", fontsize=14, transform=ax.transAxes)
        ax.set_title(f"Spatial Overlap Network — {country}\n"
                     f"{len(G.nodes)} nodes, {len(G.edges)} edges\n"
                     f"Edge thickness ∝ Jaccard index (MCP intersection / union area)",
                     fontsize=11)
        ax.axis("off")
        fig.tight_layout()
        safe_name = country.replace(" ", "_")
        fig.savefig(out_dir / f"6a_overlap_network_{safe_name}.png", dpi=150)
        figs[f"overlap_{safe_name}"] = fig

    # ---- Network metrics (per-country, per-biome, global) ----

    def _graph_metrics(G_sub: nx.Graph, label: str, group_type: str) -> dict:
        """Compute standard network metrics for a graph."""
        n_nodes = len(G_sub.nodes)
        n_edges = len(G_sub.edges)
        if n_nodes == 0:
            return None
        weights = [d["weight"] for _, _, d in G_sub.edges(data=True)]
        m = {
            "group_type": group_type,
            "group": label,
            "n_nodes": n_nodes,
            "n_edges": n_edges,
            "density": nx.density(G_sub),
            "n_components": nx.number_connected_components(G_sub),
            "mean_degree": np.mean([d for _, d in G_sub.degree()]) if n_nodes else 0,
            "clustering_coeff": nx.average_clustering(G_sub, weight="weight") if n_edges else 0,
            "mean_jaccard": np.mean(weights) if weights else 0,
            "max_jaccard": np.max(weights) if weights else 0,
        }
        # Biome assortativity: requires ≥2 distinct biome values and ≥1 edge
        biome_vals = set(nx.get_node_attributes(G_sub, "biome").values())
        if len(biome_vals) >= 2 and n_edges > 0:
            try:
                m["biome_assortativity"] = nx.attribute_assortativity_coefficient(G_sub, "biome")
            except Exception:
                m["biome_assortativity"] = np.nan
        else:
            m["biome_assortativity"] = np.nan
        return m

    # Build the global graph
    G_all = nx.Graph()
    for ind_id in polygons:
        G_all.add_node(ind_id, biome=biomes.get(ind_id, ""),
                       country=countries_map.get(ind_id, ""))
    for id_a, id_b, w, _ in all_edges:
        G_all.add_edge(id_a, id_b, weight=w)

    rows = []

    # Per-country subgraphs
    for country in sorted(set(countries_map.values())):
        c_ids = [k for k, v in countries_map.items() if v == country and k in polygons]
        G_c = G_all.subgraph(c_ids).copy()
        m = _graph_metrics(G_c, country, "country")
        if m:
            rows.append(m)

    # Per-biome subgraphs
    for biome_name in BIOME_ORDER:
        b_ids = [k for k, v in biomes.items() if v == biome_name and k in polygons]
        if not b_ids:
            continue
        G_b = G_all.subgraph(b_ids).copy()
        m = _graph_metrics(G_b, biome_name, "biome")
        if m:
            rows.append(m)

    # Global
    m = _graph_metrics(G_all, "ALL", "global")
    if m:
        rows.append(m)

    if rows:
        metrics_df = pd.DataFrame(rows)
        metrics_df.to_csv(out_dir / "network_metrics.csv", index=False)

        # --- 6b. Comparative bar chart: key metrics by country & biome ---
        sub = metrics_df[metrics_df["group_type"] != "global"].copy()
        plot_metrics = ["density", "clustering_coeff", "mean_jaccard"]
        labels_nice = {"density": "Density", "clustering_coeff": "Clustering Coeff.",
                       "mean_jaccard": "Mean Jaccard"}
        fig, axes = plt.subplots(1, 3, figsize=(18, 5))
        for ax, metric in zip(axes, plot_metrics):
            # countries first, then biomes
            countries_df = sub[sub["group_type"] == "country"].sort_values("group")
            biomes_df = sub[sub["group_type"] == "biome"]
            # order biomes by BIOME_ORDER
            biome_order_present = [b for b in BIOME_ORDER if b in biomes_df["group"].values]
            biomes_df = biomes_df.set_index("group").loc[biome_order_present].reset_index()

            all_labels = list(countries_df["group"]) + [""] + list(biomes_df["group"])
            all_vals = list(countries_df[metric]) + [0] + list(biomes_df[metric])
            colors = (["#78909C"] * len(countries_df)) + ["white"] + \
                     [BIOME_COLORS.get(b, "gray") for b in biome_order_present]
            x = range(len(all_labels))
            bars = ax.bar(x, all_vals, color=colors, edgecolor="black", linewidth=0.5)
            # hide the separator bar
            sep_idx = len(countries_df)
            bars[sep_idx].set_visible(False)
            ax.set_xticks(list(x))
            ax.set_xticklabels(all_labels, rotation=40, ha="right", fontsize=7)
            ax.set_ylabel(labels_nice[metric])
            ax.set_title(labels_nice[metric], fontsize=10)
            # Add divider label
            ax.axvline(sep_idx, color="gray", ls=":", lw=0.8)
        fig.suptitle("Network Metrics by Country (left) & Biome (right)", fontsize=12)
        fig.tight_layout()
        fig.savefig(out_dir / "6b_network_metrics_comparison.png", dpi=150)
        figs["metrics_comparison"] = fig

    # --- 6c. Degree distribution by biome (individual subplots) ---
    if len(G_all.edges) > 0:
        biomes_with_nodes = [b for b in BIOME_ORDER
                             if any(biomes.get(n) == b for n in G_all.nodes)]
        n_b = len(biomes_with_nodes)
        ncols = min(3, n_b)
        nrows = (n_b + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 4 * nrows), squeeze=False)
        axes_flat = axes.flatten()
        max_degree = max(d for _, d in G_all.degree())
        for i, biome_name in enumerate(biomes_with_nodes):
            ax = axes_flat[i]
            b_nodes = [n for n in G_all.nodes if biomes.get(n) == biome_name]
            degrees = [G_all.degree(n) for n in b_nodes]
            ax.hist(degrees, bins=range(0, max_degree + 2), alpha=0.8,
                    color=BIOME_COLORS.get(biome_name, "gray"),
                    edgecolor="black", linewidth=0.3)
            med = np.median(degrees)
            ax.axvline(med, color="red", ls="--", lw=1,
                       label=f"Median={med:.0f}")
            ax.set_xlabel("Degree")
            ax.set_ylabel("Count")
            ax.set_title(f"{biome_name} (n={len(b_nodes)})", fontsize=10)
            ax.legend(fontsize=7)
        for j in range(i + 1, len(axes_flat)):
            axes_flat[j].set_visible(False)
        fig.suptitle("Degree Distribution by Biome", fontsize=13)
        fig.tight_layout()
        fig.savefig(out_dir / "6c_degree_distribution.png", dpi=150)
        figs["degree_dist"] = fig

    # --- 6d. Jaccard edge-weight distribution: within- vs cross-biome ---
    if all_edges:
        within_w = [w for a, b, w, _ in all_edges if biomes.get(a) == biomes.get(b)]
        cross_w = [w for a, b, w, _ in all_edges if biomes.get(a) != biomes.get(b)]
        fig, ax = plt.subplots(figsize=(10, 5))
        bins = np.linspace(0, 1, 30)
        if within_w:
            ax.hist(within_w, bins=bins, alpha=0.6, color="#2E7D32", edgecolor="black",
                    linewidth=0.3, label=f"Within-biome (n={len(within_w)})")
        if cross_w:
            ax.hist(cross_w, bins=bins, alpha=0.6, color="#E65100", edgecolor="black",
                    linewidth=0.3, label=f"Cross-biome (n={len(cross_w)})")
        ax.set_xlabel("Jaccard Index (MCP overlap)")
        ax.set_ylabel("Edge Count")
        ax.set_title("Edge Weight Distribution: Within- vs Cross-Biome Overlap")
        ax.legend(fontsize=9)
        fig.tight_layout()
        fig.savefig(out_dir / "6d_jaccard_distribution.png", dpi=150)
        figs["jaccard_dist"] = fig

    plt.close("all")
    return figs
