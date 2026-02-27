# -*- coding: utf-8 -*-
"""
Movement data processor for jaguar GPS telemetry data.

Handles parsing, cleaning, quality filtering, coordinate projection,
and grid discretization of the Morato et al. (2018) jaguar movement
database for use with the MaxEnt IRL framework.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from pyproj import Transformer

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
#  Configuration
# ------------------------------------------------------------------ #

@dataclass
class ProcessorConfig:
    """Configuration for movement data processing."""

    # Input
    csv_path: str = "jaguar_movement_data.csv"

    # Quality filtering thresholds
    min_fixes: int = 100
    min_duration_days: int = 60
    max_gap_fraction: float = 0.50  # max fraction of days with no fix

    # Temporal resampling
    resample_interval_hours: float = 4.0

    # Grid discretization
    cell_size_m: float = 1000.0  # metres per grid cell

    # Tile buffer around home range
    tile_buffer_m: float = 20000.0  # 20 km buffer

    # Output
    output_dir: str = "./data/processed"


# ------------------------------------------------------------------ #
#  Column name constants
# ------------------------------------------------------------------ #

COL_EVENT = "Event_ID"
COL_TIMESTAMP = "timestamp"
COL_LON = "location.long"
COL_LAT = "location.lat"
COL_SPECIES = "individual.taxon.canonical.name"
COL_TAG = "tag.local.identifier"
COL_ID = "individual.local.identifier (ID)"
COL_STUDY = "study.name"
COL_COUNTRY = "country"


# ------------------------------------------------------------------ #
#  Core processor
# ------------------------------------------------------------------ #

class MovementProcessor:
    """Process jaguar GPS telemetry data for IRL model input.

    Pipeline:
        1. parse() — Load CSV, parse timestamps, validate coordinates
        2. compute_individual_stats() — Per-individual summary statistics
        3. filter_individuals() — Quality filtering
        4. project_to_utm() — WGS84 → UTM projection (metres)
        5. discretize_to_grid() — Continuous coords → grid cell indices
        6. export_trajectories() — Save as .npy files for MaxEntIRL
    """

    def __init__(self, config: Optional[ProcessorConfig] = None) -> None:
        self.config = config or ProcessorConfig()
        self.raw_df: Optional[pd.DataFrame] = None
        self.df: Optional[pd.DataFrame] = None
        self.individual_stats: Optional[pd.DataFrame] = None
        self.qualified_ids: list = []

    # ------------------------------------------------------------------ #
    #  Step 1: Parse & Clean
    # ------------------------------------------------------------------ #

    def parse(self) -> pd.DataFrame:
        """Load and parse the jaguar movement CSV.

        Returns:
            Cleaned DataFrame with parsed timestamps and validated coords.
        """
        logger.info("Parsing %s...", self.config.csv_path)

        df = pd.read_csv(
            self.config.csv_path,
            low_memory=False,
            dtype={COL_TAG: str},
        )
        df.columns = df.columns.str.strip()

        # Parse timestamps (format: M/D/YY H:MM or similar)
        df[COL_TIMESTAMP] = pd.to_datetime(
            df[COL_TIMESTAMP], format="mixed", dayfirst=False
        )

        # Validate coordinates
        df[COL_LON] = pd.to_numeric(df[COL_LON], errors="coerce")
        df[COL_LAT] = pd.to_numeric(df[COL_LAT], errors="coerce")

        n_before = len(df)
        df = df.dropna(subset=[COL_LON, COL_LAT, COL_TIMESTAMP])
        n_dropped = n_before - len(df)
        if n_dropped > 0:
            logger.warning("Dropped %d rows with missing coords/timestamps", n_dropped)

        # Validate coordinate ranges
        valid_coords = (
            (df[COL_LON] >= -180) & (df[COL_LON] <= 180) &
            (df[COL_LAT] >= -90) & (df[COL_LAT] <= 90)
        )
        n_invalid = (~valid_coords).sum()
        if n_invalid > 0:
            logger.warning("Dropped %d rows with out-of-range coordinates", n_invalid)
            df = df[valid_coords]

        # Sort by individual and timestamp
        df = df.sort_values([COL_ID, COL_TIMESTAMP]).reset_index(drop=True)

        self.raw_df = df.copy()
        self.df = df
        logger.info(
            "Parsed %d records for %d individuals",
            len(df), df[COL_ID].nunique(),
        )
        return df

    # ------------------------------------------------------------------ #
    #  Step 2: Per-individual statistics
    # ------------------------------------------------------------------ #

    def compute_individual_stats(self) -> pd.DataFrame:
        """Compute summary statistics for each individual.

        Returns:
            DataFrame with columns: id, n_fixes, first_fix, last_fix,
            duration_days, median_interval_h, fixes_per_day, study,
            country, lon_mean, lat_mean.
        """
        if self.df is None:
            raise RuntimeError("Call parse() first.")

        logger.info("Computing per-individual statistics...")

        grouped = self.df.groupby(COL_ID)

        # Basic stats
        stats = grouped.agg(
            n_fixes=(COL_EVENT, "count"),
            first_fix=(COL_TIMESTAMP, "min"),
            last_fix=(COL_TIMESTAMP, "max"),
            study=(COL_STUDY, "first"),
            country=(COL_COUNTRY, "first"),
            lon_mean=(COL_LON, "mean"),
            lat_mean=(COL_LAT, "mean"),
        ).reset_index()

        stats["duration_days"] = (
            (stats["last_fix"] - stats["first_fix"]).dt.total_seconds() / 86400
        )
        stats["fixes_per_day"] = stats["n_fixes"] / np.maximum(
            stats["duration_days"], 1.0
        )

        # Median fix interval per individual
        median_intervals = []
        for ind_id in stats[COL_ID]:
            ind_df = self.df[self.df[COL_ID] == ind_id].sort_values(COL_TIMESTAMP)
            diffs_h = ind_df[COL_TIMESTAMP].diff().dt.total_seconds() / 3600
            median_intervals.append(diffs_h.median())
        stats["median_interval_h"] = median_intervals

        # Number of unique days with at least one fix
        days_with_fix = grouped.apply(
            lambda g: g[COL_TIMESTAMP].dt.date.nunique(),
            include_groups=False,
        )
        stats["days_with_fix"] = days_with_fix.values
        stats["gap_fraction"] = 1.0 - (
            stats["days_with_fix"] / np.maximum(stats["duration_days"], 1.0)
        )

        self.individual_stats = stats
        logger.info("Computed stats for %d individuals", len(stats))
        return stats

    # ------------------------------------------------------------------ #
    #  Step 3: Quality filtering
    # ------------------------------------------------------------------ #

    def filter_individuals(self) -> list:
        """Apply quality filters and return list of qualified individual IDs.

        Criteria:
            - >= min_fixes GPS fixes
            - >= min_duration_days tracking duration
            - gap_fraction <= max_gap_fraction
        """
        if self.individual_stats is None:
            raise RuntimeError("Call compute_individual_stats() first.")

        stats = self.individual_stats
        cfg = self.config

        passes = stats[
            (stats["n_fixes"] >= cfg.min_fixes) &
            (stats["duration_days"] >= cfg.min_duration_days) &
            (stats["gap_fraction"] <= cfg.max_gap_fraction)
        ]

        self.qualified_ids = passes[COL_ID].tolist()

        # Filter the main dataframe
        self.df = self.df[self.df[COL_ID].isin(self.qualified_ids)].copy()

        logger.info(
            "Quality filter: %d / %d individuals pass "
            "(>=%d fixes, >=%d days, <=%.0f%% gaps)",
            len(self.qualified_ids), len(stats),
            cfg.min_fixes, cfg.min_duration_days, cfg.max_gap_fraction * 100,
        )
        logger.info(
            "Retained %d / %d total fixes",
            len(self.df), len(self.raw_df),
        )

        return self.qualified_ids

    # ------------------------------------------------------------------ #
    #  Step 4: UTM Projection
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_utm_epsg(lon: float, lat: float) -> int:
        """Determine the UTM EPSG code for a given WGS84 coordinate."""
        zone_number = int((lon + 180) / 6) + 1
        if lat >= 0:
            return 32600 + zone_number  # Northern hemisphere
        else:
            return 32700 + zone_number  # Southern hemisphere

    def project_to_utm(self) -> pd.DataFrame:
        """Convert WGS84 (lon, lat) to UTM (easting, northing) per individual.

        Each individual gets projected into the UTM zone of their centroid
        to ensure consistent metric distances.

        Adds columns: utm_x, utm_y, utm_epsg.
        """
        if self.df is None:
            raise RuntimeError("Call parse() first.")

        logger.info("Projecting to UTM...")

        self.df["utm_x"] = np.nan
        self.df["utm_y"] = np.nan
        self.df["utm_epsg"] = 0

        for ind_id in self.df[COL_ID].unique():
            mask = self.df[COL_ID] == ind_id
            ind_df = self.df.loc[mask]

            # Determine UTM zone from centroid
            lon_mean = ind_df[COL_LON].mean()
            lat_mean = ind_df[COL_LAT].mean()
            epsg = self.get_utm_epsg(lon_mean, lat_mean)

            transformer = Transformer.from_crs(
                "EPSG:4326", f"EPSG:{epsg}", always_xy=True
            )
            x, y = transformer.transform(
                ind_df[COL_LON].values, ind_df[COL_LAT].values
            )

            self.df.loc[mask, "utm_x"] = x
            self.df.loc[mask, "utm_y"] = y
            self.df.loc[mask, "utm_epsg"] = epsg

        logger.info("UTM projection complete")
        return self.df

    # ------------------------------------------------------------------ #
    #  Step 5: Grid discretization
    # ------------------------------------------------------------------ #

    def discretize_to_grid(self) -> dict[str, dict]:
        """Convert UTM coordinates to grid cell indices per individual.

        For each individual:
            1. Compute bounding box of their trajectory + buffer
            2. Create grid with cell_size_m resolution
            3. Map each fix to (row, col, time_index)

        Returns:
            Dict mapping individual ID to:
                - 'trajectory': array of shape (n_fixes, 3) [row, col, time_idx]
                - 'grid_origin': (x_min, y_min) in UTM
                - 'grid_shape': (n_rows, n_cols, n_timesteps)
                - 'utm_epsg': int
        """
        if "utm_x" not in self.df.columns:
            raise RuntimeError("Call project_to_utm() first.")

        logger.info("Discretizing to grid (cell size: %.0fm)...", self.config.cell_size_m)

        results: dict[str, dict] = {}
        cell = self.config.cell_size_m
        buf = self.config.tile_buffer_m

        for ind_id in self.df[COL_ID].unique():
            ind_df = self.df[self.df[COL_ID] == ind_id].sort_values(COL_TIMESTAMP)

            # Bounding box + buffer
            x_min = ind_df["utm_x"].min() - buf
            x_max = ind_df["utm_x"].max() + buf
            y_min = ind_df["utm_y"].min() - buf
            y_max = ind_df["utm_y"].max() + buf

            n_cols = int(np.ceil((x_max - x_min) / cell))
            n_rows = int(np.ceil((y_max - y_min) / cell))

            # Map coordinates to grid cells
            col_idx = ((ind_df["utm_x"].values - x_min) / cell).astype(int)
            row_idx = ((ind_df["utm_y"].values - y_min) / cell).astype(int)

            # Clip to valid range
            col_idx = np.clip(col_idx, 0, n_cols - 1)
            row_idx = np.clip(row_idx, 0, n_rows - 1)

            # Invert row index (grid convention: row 0 = top = max y)
            row_idx = (n_rows - 1) - row_idx

            # Time indices: sequential from 0
            n_timesteps = len(ind_df)
            time_idx = np.arange(n_timesteps)

            trajectory = np.stack([row_idx, col_idx, time_idx], axis=1).astype(np.int32)

            results[str(ind_id)] = {
                "trajectory": trajectory,
                "grid_origin": (float(x_min), float(y_min)),
                "grid_shape": (n_rows, n_cols, n_timesteps),
                "utm_epsg": int(ind_df["utm_epsg"].iloc[0]),
                "n_fixes": len(ind_df),
                "duration_days": (
                    ind_df[COL_TIMESTAMP].iloc[-1] - ind_df[COL_TIMESTAMP].iloc[0]
                ).total_seconds() / 86400,
            }

        logger.info("Discretized %d individuals", len(results))
        return results

    # ------------------------------------------------------------------ #
    #  Step 6: Export trajectories
    # ------------------------------------------------------------------ #

    def export_trajectories(
        self,
        grid_data: dict[str, dict],
        output_dir: Optional[str] = None,
    ) -> Path:
        """Save discretized trajectories as .npy files.

        Also writes a basename.txt index file listing all individuals.

        Args:
            grid_data: Output of discretize_to_grid().
            output_dir: Override output directory.

        Returns:
            Path to the output directory.
        """
        out_path = Path(output_dir or self.config.output_dir)
        tracking_dir = out_path / "tracking"
        tracking_dir.mkdir(parents=True, exist_ok=True)

        basenames: list[str] = []

        for ind_id, data in grid_data.items():
            basename = f"jaguar_{ind_id}"
            np.save(tracking_dir / f"{basename}.npy", data["trajectory"])
            basenames.append(basename)

            # Also save grid metadata
            meta = {k: v for k, v in data.items() if k != "trajectory"}
            np.save(tracking_dir / f"{basename}_meta.npy", meta)

        # Write basename index
        with open(out_path / "basename.txt", "w") as f:
            for bn in sorted(basenames):
                f.write(bn + "\n")

        # Write summary CSV
        summary_rows = []
        for ind_id, data in grid_data.items():
            summary_rows.append({
                "individual_id": ind_id,
                "basename": f"jaguar_{ind_id}",
                "n_fixes": data["n_fixes"],
                "duration_days": data["duration_days"],
                "grid_rows": data["grid_shape"][0],
                "grid_cols": data["grid_shape"][1],
                "utm_epsg": data["utm_epsg"],
            })
        summary_df = pd.DataFrame(summary_rows)
        summary_df.to_csv(out_path / "individual_summary.csv", index=False)

        logger.info(
            "Exported %d trajectories to %s", len(basenames), tracking_dir,
        )
        return out_path

    # ------------------------------------------------------------------ #
    #  Convenience: run full pipeline
    # ------------------------------------------------------------------ #

    def run_pipeline(self) -> dict[str, dict]:
        """Execute the full data processing pipeline.

        Returns:
            Grid data dictionary from discretize_to_grid().
        """
        self.parse()
        self.compute_individual_stats()
        self.filter_individuals()
        self.project_to_utm()
        grid_data = self.discretize_to_grid()
        self.export_trajectories(grid_data)
        return grid_data


def main() -> None:
    """CLI entry point for data processing."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    processor = MovementProcessor()
    grid_data = processor.run_pipeline()

    # Print summary
    stats = processor.individual_stats
    qualified = stats[stats[COL_ID].isin(processor.qualified_ids)]
    print(f"\n{'='*60}")
    print(f"Processing complete!")
    print(f"  Total records parsed: {len(processor.raw_df)}")
    print(f"  Individuals qualified: {len(processor.qualified_ids)} / {stats[COL_ID].nunique()}")
    print(f"  Fixes retained: {len(processor.df)}")
    print(f"  Output: {processor.config.output_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
