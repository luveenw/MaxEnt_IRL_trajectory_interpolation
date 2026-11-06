# -*- coding: utf-8 -*-
"""
Movement data processor for jaguar GPS telemetry data.

Handles parsing, cleaning, quality filtering, coordinate projection,
and grid discretization of the Morato et al. (2018) jaguar movement
database for use with the MaxEnt IRL framework.

Processes full records with legacy individual eligibility, observed two-hour
sampling and per-bout short-fragment rejection. Pantanal week/month/cluster
selection lives separately in movement_processor_pantanal.py.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from pyproj import Transformer

from .movement_temporal import (
    SamplingConfig, interval_metrics, segment_points, thin_observed_records,
)

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


def _json_default(value):
    if isinstance(value,Path):
        return str(value)
    if isinstance(value,np.generic):
        return value.item()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


# ------------------------------------------------------------------ #
#  Configuration
# ------------------------------------------------------------------ #

@dataclass
class ProcessorConfig:
    """Configuration for movement data processing."""

    # Input
    csv_path: str = str(ROOT / "data" / "jaguar_movement_data.csv")

    # Quality filtering thresholds
    min_fixes: int = 100
    min_duration_days: int = 60
    max_gap_fraction: float = 0.50  # max fraction of days with no fix

    # Observed-fix sampling; no location interpolation.
    resample_interval_hours: float = 2.0
    regular_min_hours: float = 1.5
    regular_max_hours: float = 2.5
    max_interval_hours: float = 4.0
    max_affected_point_fraction: float = 0.20
    min_subtrajectory_points: int = 5
    max_short_fragment_loss: float = 0.05  # Per recording bout, before splitting.

    # Grid discretization
    cell_size_m: float = 500.0  # metres per grid cell

    # Tile buffer around home range
    tile_buffer_m: float = 20000.0  # 20 km buffer

    # Output
    output_dir: str = "./data/processed"

    def __post_init__(self) -> None:
        self.sampling_config()
        if not 0 <= self.max_short_fragment_loss <= 1 or not 0 <= self.max_gap_fraction <= 1:
            raise ValueError("Loss and missing-day fractions must be between 0 and 1")
        if self.min_fixes < 1 or self.min_duration_days < 0:
            raise ValueError("Require positive min_fixes and nonnegative duration")
        if not np.isfinite(self.cell_size_m) or self.cell_size_m <= 0:
            raise ValueError("cell_size_m must be finite and positive")
        if not np.isfinite(self.tile_buffer_m) or self.tile_buffer_m < 0:
            raise ValueError("tile_buffer_m must be finite and nonnegative")

    def sampling_config(self) -> SamplingConfig:
        return SamplingConfig(
            target_interval_hours=self.resample_interval_hours,
            regular_min_hours=self.regular_min_hours,
            regular_max_hours=self.regular_max_hours,
            max_gap_hours=self.max_interval_hours,
            max_affected_point_fraction=self.max_affected_point_fraction,
            min_subtrajectory_points=self.min_subtrajectory_points,
        )


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
        4. resample_and_segment() — Full records → accepted subtrajectories
        5. project_to_utm() — WGS84 → UTM projection (metres)
        6. discretize_to_grid() — Shared per-animal grid, separate segments
        7. export_trajectories() — Arrays, timestamps, IDs and quality audits
    """

    def __init__(self, config: Optional[ProcessorConfig] = None) -> None:
        self.config = config or ProcessorConfig()
        self.raw_df: Optional[pd.DataFrame] = None
        self.df: Optional[pd.DataFrame] = None
        self.individual_stats: Optional[pd.DataFrame] = None
        self.qualified_ids: list = []
        self.retained_ids: list = []
        self.bout_audit = pd.DataFrame()
        self.trajectory_stats = pd.DataFrame()

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
            df[COL_TIMESTAMP], format="mixed", dayfirst=False, errors="coerce"
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
        if df.duplicated([COL_ID, COL_TIMESTAMP]).any():
            raise ValueError("Resolve duplicate timestamps per individual before processing")

        self.raw_df = df.copy()
        self.df = df
        self.individual_stats = None
        self.qualified_ids = []
        self.retained_ids = []
        self.bout_audit = pd.DataFrame()
        self.trajectory_stats = pd.DataFrame()
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
        days_with_fix = grouped[COL_TIMESTAMP].agg(lambda s: s.dt.date.nunique())
        stats["days_with_fix"] = days_with_fix.values
        # The fraction of empty calendar dates needs both endpoint dates;
        # using fractional elapsed days could produce a negative gap fraction.
        stats["calendar_days"] = (
            stats["last_fix"].dt.normalize() - stats["first_fix"].dt.normalize()
        ).dt.days + 1
        stats["gap_fraction"] = 1.0 - stats["days_with_fix"] / stats["calendar_days"]

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

    def sample_individual(self, ind_df: pd.DataFrame) -> dict:
        """Sample one full record and split it at gaps and excess irregularity.

        This computes candidate segments and loss diagnostics before applying
        eligibility or short-fragment-loss rejection. A four-hour interval is
        retained as four hours, and cuts never duplicate an observation.
        """
        if ind_df[COL_ID].nunique() != 1:
            raise ValueError("sample_individual requires exactly one individual")
        if ind_df[COL_TIMESTAMP].duplicated().any():
            raise ValueError("Resolve duplicate individual timestamps before sampling")
        cfg = self.config.sampling_config()
        records = [dict(row, timestamp=row[COL_TIMESTAMP].to_pydatetime(),
                        event_id=row[COL_EVENT])
                   for row in ind_df.sort_values(COL_TIMESTAMP).to_dict("records")]
        selected = thin_observed_records(records, cfg)
        bouts = []
        for point in selected:
            if not bouts or (point["timestamp"]-bouts[-1][-1]["timestamp"]).total_seconds()/3600 > cfg.max_gap_hours:
                bouts.append([])
            bouts[-1].append(point)
        return {
            "selected_points": selected,
            "bouts": [dict(points=points, **segment_points(points, cfg)) for points in bouts],
            "raw_fixes": len(ind_df),
            "resampled_fixes": len(selected),
        }

    def resample_and_segment(self) -> pd.DataFrame:
        """Retain qualifying segments from each independently screened bout.

        A bout ends at a sampled interval over four hours. Its short-fragment
        loss uses all its sampled points before cuts; exceeding 5% rejects only
        that bout. Legacy eligibility is evaluated before this method.
        """
        if self.df is None:
            raise RuntimeError("Call parse() and filter_individuals() first")
        if "trajectory_id" in self.df.columns:
            raise RuntimeError("Already sampled; call parse() before processing again")
        cfg = self.config.sampling_config()
        retained, audit, summaries = [], [], []
        for individual, ind_df in self.df.groupby(COL_ID, sort=True):
            sampled = self.sample_individual(ind_df)
            selected = sampled["selected_points"]
            source_gaps = {p["timestamp"]: None if i == 0 else
                (p["timestamp"]-selected[i-1]["timestamp"]).total_seconds()/3600
                for i,p in enumerate(selected)}
            for bout in sampled["bouts"]:
                points = bout["points"]
                bout_id = f"jaguar_{individual}_b{points[0]['timestamp']:%Y%m%dT%H%M%S}"
                loss = bout["short_fragment_loss"]
                accepted = bool(bout["segments"]) and loss <= self.config.max_short_fragment_loss + 1e-12
                valid_count = sum(len(s) for s in bout["segments"])
                audit.append({"individual_id":individual,"bout_id":bout_id,
                    "start":points[0]["timestamp"],"end":points[-1]["timestamp"],
                    "n_sampled":len(points),"n_short_fixes":len(bout["dropped_points"]),
                    "short_fragment_loss":loss,"accepted":accepted,
                    "rejection_reason":"" if accepted else
                        ("excess_short_fragment_loss" if loss > self.config.max_short_fragment_loss + 1e-12
                         else "no_qualifying_segments"),
                    "candidate_segments":len(bout["segments"]),
                    "retained_segments":len(bout["segments"]) if accepted else 0,
                    "retained_fixes":valid_count if accepted else 0,
                    "rejected_good_fixes":0 if accepted else valid_count})
                if not accepted:
                    continue
                for part in bout["segments"]:
                    trajectory_id = f"jaguar_{individual}_{part[0]['timestamp']:%Y%m%dT%H%M%S}"
                    metrics = interval_metrics(part,cfg)
                    summaries.append({"trajectory_id":trajectory_id,"bout_id":bout_id,
                        "individual_id":individual,"split_group_id":individual,
                        "start":part[0]["timestamp"],"end":part[-1]["timestamp"],
                        "n_fixes":len(part),"duration_hours":
                            (part[-1]["timestamp"]-part[0]["timestamp"]).total_seconds()/3600,
                        "affected_point_fraction":metrics["affected_point_fraction"],
                        "max_gap_hours":metrics["max_gap_hours"],
                        "bout_short_fragment_loss":loss})
                    for step,point in enumerate(part):
                        item = {k:v for k,v in point.items() if k != "event_id"}
                        item.update(individual_id=individual,split_group_id=individual,
                            bout_id=bout_id,trajectory_id=trajectory_id,step_index=step,
                            dt_hours=None if step == 0 else metrics["gaps"][step-1],
                            source_dt_hours=source_gaps[point["timestamp"]],
                            elapsed_hours=(point["timestamp"]-part[0]["timestamp"]).total_seconds()/3600,
                            affected_by_gap=step in metrics["affected_indices"])
                        retained.append(item)
        extra = ["individual_id","split_group_id","bout_id","trajectory_id","step_index",
                 "dt_hours","source_dt_hours","elapsed_hours","affected_by_gap"]
        self.df = pd.DataFrame(retained,columns=list(dict.fromkeys([*self.df.columns,*extra])))
        self.bout_audit = pd.DataFrame(audit,columns=["individual_id","bout_id","start","end",
            "n_sampled","n_short_fixes","short_fragment_loss","accepted","rejection_reason",
            "candidate_segments","retained_segments","retained_fixes","rejected_good_fixes"])
        self.trajectory_stats = pd.DataFrame(summaries,columns=["trajectory_id","bout_id",
            "individual_id","split_group_id","start","end","n_fixes","duration_hours",
            "affected_point_fraction","max_gap_hours","bout_short_fragment_loss"])
        self.retained_ids = self.df[COL_ID].unique().tolist()
        logger.info("Retained %d points in %d segments for %d animals after bout screening",
                    len(self.df),len(self.trajectory_stats),len(self.retained_ids))
        return self.df

    # ------------------------------------------------------------------ #
    #  Step 4: UTM Projection
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_utm_epsg(lon: float, lat: float) -> int:
        """Determine the UTM EPSG code for a given WGS84 coordinate."""
        zone_number = min(60,max(1,int((lon + 180) / 6) + 1))
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
        """Export separate segments on one common grid per individual.

        Each dictionary key is a trajectory ID. Arrays contain row, column,
        and observation index; actual elapsed time is separate metadata.
        Bounds cover all retained points of an animal plus its configured
        buffer. Raster dimensions are rounded outwards to complete cells.
        """
        if self.df is None or "utm_x" not in self.df.columns or "trajectory_id" not in self.df.columns:
            raise RuntimeError("Call resample_and_segment() and project_to_utm() first.")

        logger.info("Discretizing to grid (cell size: %.0fm)...", self.config.cell_size_m)

        results: dict[str, dict] = {}
        cell = self.config.cell_size_m
        buf = self.config.tile_buffer_m

        self.df["grid_row"] = pd.Series(index=self.df.index,dtype="int64")
        self.df["grid_col"] = pd.Series(index=self.df.index,dtype="int64")
        quality = self.trajectory_stats.set_index("trajectory_id").to_dict("index")
        for ind_id, ind_df in self.df.groupby(COL_ID,sort=True):
            x_min = float(ind_df["utm_x"].min() - buf)
            y_min = float(ind_df["utm_y"].min() - buf)
            n_cols = max(1,int(np.ceil((ind_df["utm_x"].max()+buf-x_min)/cell)))
            n_rows = max(1,int(np.ceil((ind_df["utm_y"].max()+buf-y_min)/cell)))
            x_max,y_max = x_min+n_cols*cell,y_min+n_rows*cell
            for trajectory_id, part in ind_df.groupby("trajectory_id",sort=True):
                part = part.sort_values(COL_TIMESTAMP)
                x,y = part["utm_x"].to_numpy(),part["utm_y"].to_numpy()
                if not (np.isfinite(x).all() and np.isfinite(y).all() and
                        ((x>=x_min-1e-7)&(x<=x_max+1e-7)&(y>=y_min-1e-7)&(y<=y_max+1e-7)).all()):
                    raise ValueError(f"Selected fixes outside projected grid: {trajectory_id}")
                # North-up raster. An exact outer-edge coordinate belongs to
                # the adjacent edge cell; prior bounds validation is required.
                cols = np.clip(np.floor((x-x_min)/cell).astype(int),0,n_cols-1)
                rows = np.clip(np.floor((y_max-y)/cell).astype(int),0,n_rows-1)
                self.df.loc[part.index,"grid_row"] = rows
                self.df.loc[part.index,"grid_col"] = cols
                trajectory = np.stack([rows,cols,np.arange(len(part))],axis=1).astype(np.int32)
                results[trajectory_id] = {
                    "trajectory":trajectory,"trajectory_id":trajectory_id,
                    "individual_id":ind_id,"split_group_id":ind_id,"bout_id":part["bout_id"].iloc[0],
                    "trajectory_columns":["row","col","step_index"],
                    "time_axis":"observation_index_not_elapsed_time",
                    "grid_origin":(x_min,y_min),"grid_origin_top_left":(x_min,y_max),
                    "grid_bounds_m":(x_min,y_min,x_max,y_max),"cell_size_m":cell,
                    "grid_shape":(n_rows,n_cols,len(part)),
                    "utm_epsg":int(part["utm_epsg"].iloc[0]),"n_fixes":len(part),
                    "duration_days":quality[trajectory_id]["duration_hours"]/24,
                    "timestamps":[t.isoformat() for t in part[COL_TIMESTAMP]],
                    "dt_hours":[None if pd.isna(v) else float(v) for v in part["dt_hours"]],
                    "elapsed_hours":part["elapsed_hours"].tolist(),
                    "event_ids":part[COL_EVENT].tolist(),
                    "affected_point_fraction":quality[trajectory_id]["affected_point_fraction"],
                    "max_gap_hours":quality[trajectory_id]["max_gap_hours"],
                    "bout_short_fragment_loss":quality[trajectory_id]["bout_short_fragment_loss"],
                }
        self.df["grid_row"] = self.df["grid_row"].astype("int64")
        self.df["grid_col"] = self.df["grid_col"].astype("int64")
        logger.info("Discretized %d subtrajectories",len(results))
        return results

    # ------------------------------------------------------------------ #
    #  Step 6: Export trajectories
    # ------------------------------------------------------------------ #

    def export_trajectories(
        self,
        grid_data: dict[str, dict],
        output_dir: Optional[str] = None,
    ) -> Path:
        """Save segment arrays, matching timing metadata and selection audits.

        basename.txt is the authoritative index for this run. Unlisted files
        from an earlier run are left untouched; loaders must follow the index.
        """
        out_path = Path(output_dir or self.config.output_dir)
        tracking_dir = out_path / "tracking"
        tracking_dir.mkdir(parents=True, exist_ok=True)

        basenames: list[str] = []

        for trajectory_id, data in grid_data.items():
            basename = trajectory_id
            np.save(tracking_dir / f"{basename}.npy", data["trajectory"])
            basenames.append(basename)

            # Also save grid metadata
            meta = {k: v for k, v in data.items() if k != "trajectory"}
            np.save(tracking_dir / f"{basename}_meta.npy", meta)
            (tracking_dir/f"{basename}_meta.json").write_text(
                json.dumps(meta,default=_json_default,allow_nan=False,indent=2),encoding="utf-8")

        # Write basename index
        with open(out_path / "basename.txt", "w") as f:
            for bn in sorted(basenames):
                f.write(bn + "\n")

        # Keep animal-level summaries separate from segment-level manifests.
        manifest = self.trajectory_stats.copy()
        manifest["basename"] = manifest["trajectory_id"]
        for column,index in [("grid_rows",0),("grid_cols",1)]:
            manifest[column] = [grid_data[t]["grid_shape"][index] for t in manifest["trajectory_id"]]
        manifest["utm_epsg"] = [grid_data[t]["utm_epsg"] for t in manifest["trajectory_id"]]
        manifest["cell_size_m"] = self.config.cell_size_m
        manifest.to_csv(out_path/"trajectory_manifest.csv",index=False)
        self.df.to_csv(out_path/"selected_points.csv",index=False)
        self.bout_audit.to_csv(out_path/"bout_audit.csv",index=False)
        summary_df = self.individual_stats.rename(columns={COL_ID:"individual_id","n_fixes":"raw_fixes"}).copy()
        summary_df["eligible"] = summary_df["individual_id"].isin(self.qualified_ids)
        counts = self.df.groupby("individual_id").size()
        segment_counts = self.trajectory_stats.groupby("individual_id").size()
        summary_df["n_fixes"] = summary_df["individual_id"].map(counts).fillna(0).astype(int)
        summary_df["n_subtrajectories"] = summary_df["individual_id"].map(segment_counts).fillna(0).astype(int)
        for column,operation in [("retained_first_fix","min"),("retained_last_fix","max")]:
            dates = self.df.groupby("individual_id")[COL_TIMESTAMP].agg(operation)
            summary_df[column] = summary_df["individual_id"].map(dates)
        summary_df["retained"] = summary_df["n_fixes"] > 0
        summary_df.to_csv(out_path / "individual_summary.csv", index=False)
        (out_path/"processing_config.json").write_text(json.dumps({
            "config":asdict(self.config),"short_fragment_loss_scope":"recording_bout",
            "source_timezone":"unspecified; preserved without conversion",
            "trajectory_columns":["row","col","step_index"],
            "time_axis":"observation_index_not_elapsed_time",
        },default=_json_default,indent=2),encoding="utf-8")

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
        self.resample_and_segment()
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

    parser = argparse.ArgumentParser(description=__doc__)
    defaults = ProcessorConfig()
    parser.add_argument("--csv",default=defaults.csv_path)
    parser.add_argument("--output",default=defaults.output_dir)
    parser.add_argument("--cell-size-m",type=float,default=defaults.cell_size_m)
    parser.add_argument("--tile-buffer-m",type=float,default=defaults.tile_buffer_m)
    parser.add_argument("--max-short-fragment-loss",type=float,default=defaults.max_short_fragment_loss)
    args = parser.parse_args()
    processor = MovementProcessor(ProcessorConfig(csv_path=args.csv,output_dir=args.output,
        cell_size_m=args.cell_size_m,tile_buffer_m=args.tile_buffer_m,
        max_short_fragment_loss=args.max_short_fragment_loss))
    grid_data = processor.run_pipeline()

    # Print summary
    stats = processor.individual_stats
    print(f"\n{'='*60}")
    print(f"Processing complete!")
    print(f"  Total records parsed: {len(processor.raw_df)}")
    print(f"  Individuals qualified: {len(processor.qualified_ids)} / {stats[COL_ID].nunique()}")
    print(f"  Individuals with accepted segments: {len(processor.retained_ids)}")
    print(f"  Subtrajectories exported: {len(grid_data)}")
    print(f"  Fixes retained: {len(processor.df)}")
    print(f"  Output: {processor.config.output_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
