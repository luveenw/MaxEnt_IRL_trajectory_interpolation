# -*- coding: utf-8 -*-
"""
Orchestrator for jaguar movement EDA.

Usage:
    python -m jaguar_irl.data.eda                           # run all sections
    python -m jaguar_irl.data.eda --sections quality movement  # run specific sections
    python -m jaguar_irl.data.eda --output post_filtering   # alternate output dir

Available section names:
    quality, movement, temporal, variogram, homerange, overlap, nsd, comparison
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

from .eda_config import load_data, COL_ID
from .eda_quality import data_quality_diagnostics
from .eda_movement import movement_metrics
from .eda_temporal import temporal_diel_patterns
from .eda_spatial import spatial_autocorrelation, home_range_estimation, spatial_overlap_network
from .eda_nsd import net_squared_displacement, NSD_DESCRIPTION
from .eda_comparison import cross_study_comparison

logger = logging.getLogger(__name__)

# Registry: maps section name → (function, HTML category prefix, HTML title)
EDA_SECTIONS = {
    "quality":    (data_quality_diagnostics,  "1", "Data Quality Diagnostics"),
    "movement":   (movement_metrics,          "2", "Movement Metrics"),
    "temporal":   (temporal_diel_patterns,    "3", "Temporal & Diel Patterns"),
    "variogram":  (spatial_autocorrelation,   "4", "Spatial Autocorrelation"),
    "homerange":  (home_range_estimation,     "5", "Home Range Estimation (MCP)"),
    "overlap":    (spatial_overlap_network,   "6", "Spatial Overlap Network"),
    "nsd":        (net_squared_displacement,  "7", "Net Squared Displacement"),
    "comparison": (cross_study_comparison,    "8", "Cross-Study & Cross-Biome Comparison"),
}

ALL_SECTION_NAMES = list(EDA_SECTIONS.keys())


def run_eda(csv_path: str,
            output_dir: str = "jaguar_irl/data/eda_report/pre_filtering",
            sections: Sequence[str] | None = None) -> Path:
    """Execute selected EDA sections (default: all) and generate HTML report.

    Parameters
    ----------
    csv_path : str
        Path to jaguar_movement_data.csv.
    output_dir : str
        Directory to write plots, CSVs, and index.html.
    sections : list of str or None
        Section names to run (see ``EDA_SECTIONS``).  None → run all.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if sections is None:
        sections = ALL_SECTION_NAMES
    else:
        unknown = set(sections) - set(ALL_SECTION_NAMES)
        if unknown:
            raise ValueError(
                f"Unknown section(s): {unknown}. "
                f"Available: {ALL_SECTION_NAMES}"
            )

    logger.info("=" * 60)
    logger.info("JAGUAR MOVEMENT DATA — EXPLORATORY DATA ANALYSIS")
    logger.info("Output: %s", out_dir)
    logger.info("Sections: %s", ", ".join(sections))
    logger.info("=" * 60)

    df = load_data(csv_path)
    logger.info("Loaded %d records for %d individuals", len(df), df[COL_ID].nunique())
    logger.info("Biome distribution:\n%s", df.groupby("biome")[COL_ID].nunique().to_string())

    all_figs = {}
    for name in sections:
        func, _prefix, _title = EDA_SECTIONS[name]
        all_figs.update(func(df, out_dir))

    _generate_html_report(out_dir)
    logger.info("=" * 60)
    logger.info("EDA COMPLETE — %d plots generated. Output: %s", len(all_figs), out_dir)
    logger.info("=" * 60)
    return out_dir


# Keep backward-compatible alias
run_full_eda = run_eda


def _generate_html_report(out_dir: Path) -> None:
    """Generate HTML page linking all plots and rendering CSV tables."""
    png_files = sorted(out_dir.glob("*.png"))

    html = [
        '<!DOCTYPE html><html><head><title>Jaguar EDA Report</title>',
        '<style>body{font-family:sans-serif;max-width:1200px;margin:auto;padding:20px;background:#fafafa}',
        'img{max-width:100%;border:1px solid #ddd;margin:10px 0;border-radius:4px}',
        'h1{color:#2E7D32}h2{color:#1565C0;border-bottom:2px solid #ddd;padding-bottom:5px}',
        'table{border-collapse:collapse;width:100%;margin:10px 0}',
        'th,td{border:1px solid #ddd;padding:6px 10px;text-align:left;font-size:13px}',
        'th{background:#e8e8e8}</style></head><body>',
        '<h1>Jaguar Movement Data — Exploratory Data Analysis</h1>',
    ]

    for _name, (_func, prefix, title) in EDA_SECTIONS.items():
        cat_files = [f for f in png_files if f.name.startswith(prefix)]
        if cat_files:
            html.append(f'<h2>{prefix}. {title}</h2>')
            if prefix == "7":
                html.append(NSD_DESCRIPTION)
            for f in cat_files:
                html.append(f'<img src="{f.name}" alt="{f.stem}"><br>')

    # Render CSV tables
    csv_files = sorted(out_dir.glob("*.csv"))
    if csv_files:
        html.append('<h2>Data Tables</h2>')
        for csv_f in csv_files:
            try:
                import pandas as pd
                tbl = pd.read_csv(csv_f)
                if len(tbl) > 50:
                    tbl = tbl.head(50)
                    html.append(f'<h3>{csv_f.name} (first 50 rows)</h3>')
                else:
                    html.append(f'<h3>{csv_f.name}</h3>')
                html.append(tbl.to_html(index=False, border=0, classes=""))
            except Exception:
                html.append(f'<p><a href="{csv_f.name}">{csv_f.name}</a></p>')

    html.append('</body></html>')
    with open(out_dir / "index.html", "w") as f:
        f.write("\n".join(html))


if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Run jaguar movement EDA (all sections or a subset).",
    )
    parser.add_argument("--csv", default="jaguar_movement_data.csv",
                        help="Path to movement CSV (default: jaguar_movement_data.csv)")
    parser.add_argument("--output", default="jaguar_irl/data/eda_report/pre_filtering",
                        help="Output directory (default: pre_filtering)")
    parser.add_argument("--sections", nargs="+", default=None,
                        choices=ALL_SECTION_NAMES, metavar="SECTION",
                        help=f"Sections to run (default: all). Choices: {', '.join(ALL_SECTION_NAMES)}")
    args = parser.parse_args()
    run_eda(args.csv, args.output, args.sections)
