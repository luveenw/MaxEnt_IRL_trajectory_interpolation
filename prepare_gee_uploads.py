#!/usr/bin/env python3
"""
Prepare Google Earth Engine ingestion artifacts for the biome review pipeline.

Earth Engine's table ingestion accepts Shapefile and CSV only -- raw GeoJSON is
not a documented upload format -- so this script converts the Step 1 outputs
into two CSVs that GEE can ingest directly:

  gee_upload/home_ranges_wkt.csv    one row per contour polygon, geometry as WKT
  gee_upload/jaguar_gps_points.csv  one row per GPS fix, geometry as lon/lat

The GPS fixes for all 117 individuals go into a *single* table rather than 115
per-individual assets. Earth Engine filters a 134k-row FeatureCollection on an
indexed property far faster than it resolves 115 separate asset reads, and it
turns a tedious batch upload into one command. Individuals 35 and 38 -- skipped
in Step 1 for having fewer than 20 fixes, and therefore absent from the home
range table -- are included here so the review app can fall back to assigning
their biome by point-in-polygon.

Usage:
    python3 prepare_gee_uploads.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import shape

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "home_range_output"
UPLOAD_DIR = BASE_DIR / "gee_upload"

HOME_RANGES_GEOJSON = OUTPUT_DIR / "home_ranges_raw.geojson"
MOVEMENT_CSV = BASE_DIR / "jaguar_movement_data.csv"
ADDITIONAL_INFO_CSV = BASE_DIR / "Jaguar_additional_information_fixed.csv"

ID_COL = "individual.local.identifier (ID)"

# jaguar_movement_data.csv uses classic-Mac CR-only line terminators; pandas
# needs to be told, or it reads the whole file as a single row.
MOVEMENT_LINETERMINATOR = "\r"

# Earth Engine CSV ingestion wants each column to hold one consistent type.
# Segment-level rows have no meaningful value for a few individual-level
# columns, so they carry this sentinel rather than an empty cell.
NA_SENTINEL = -1

HOME_RANGE_COLUMNS = [
    "individual_id",
    "study_name",
    "sex",
    "segment_id",
    "contour_level",
    "area_km2",
    "method",
    "is_range_shift",
    "n_core_areas",
    "ctmm_model",
    "n_gps_points",
    "trajectory_days",
    # Tracking years drive the Tier 2 covariate reconstruction: Hansen forest
    # cover, gHM and GHSL are all time series, and the whole point of using them
    # is to describe the landscape as it was while the animal was collared --
    # not as it is now. Carried here so Earth Engine needs no aggregation pass.
    "year_start",
    "year_end",
    "year_mid",
    "wkt",
]


def _num(value, sentinel=NA_SENTINEL):
    """Coerce a GeoJSON property to a number, mapping null to the sentinel."""
    if value is None:
        return sentinel
    return value


def load_tracking_years() -> pd.DataFrame:
    """First, last and midpoint tracking year for every individual.

    Returned as a frame indexed by individual_id so both upload CSVs can carry
    the same values; the Earth Engine scripts then select raster years without
    a server-side aggregation over 134k points.
    """
    movement = pd.read_csv(
        MOVEMENT_CSV, lineterminator=MOVEMENT_LINETERMINATOR, low_memory=False
    )
    movement.columns = [c.strip() for c in movement.columns]

    timestamps = _parse_timestamps(movement["timestamp"])
    years = pd.DataFrame(
        {"individual_id": movement[ID_COL].astype(int), "year": timestamps.dt.year}
    ).dropna()

    table = years.groupby("individual_id")["year"].agg(["min", "max"]).astype(int)
    table.columns = ["year_start", "year_end"]
    # Floor rather than round: the midpoint only ever indexes an annual layer,
    # and flooring keeps it inside the observed window.
    table["year_mid"] = ((table["year_start"] + table["year_end"]) // 2).astype(int)
    return table


def _parse_timestamps(raw: pd.Series) -> pd.Series:
    """Parse the dataset's two-digit-year timestamps, falling back to 4-digit."""
    parsed = pd.to_datetime(raw, format="%m/%d/%y %H:%M", errors="coerce")
    fallback = parsed.isna()
    if fallback.any():
        parsed.loc[fallback] = pd.to_datetime(
            raw[fallback], format="%m/%d/%Y %H:%M", errors="coerce"
        )
    return parsed


def write_home_ranges_csv(years: pd.DataFrame) -> int:
    """Convert home_ranges_raw.geojson to a WKT CSV for GEE ingestion."""
    if not HOME_RANGES_GEOJSON.exists():
        sys.exit(
            f"ERROR: {HOME_RANGES_GEOJSON} not found.\n"
            "Run: Rscript home_range_analysis.R --consolidate-only"
        )

    with HOME_RANGES_GEOJSON.open(encoding="utf-8") as fh:
        collection = json.load(fh)

    features = collection["features"]
    out_path = UPLOAD_DIR / "home_ranges_wkt.csv"

    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=HOME_RANGE_COLUMNS)
        writer.writeheader()

        for feature in features:
            props = feature["properties"]
            geom = shape(feature["geometry"])

            # GEE rejects self-intersecting rings on ingestion; a zero-width
            # buffer repairs the handful ctmm's contouring can emit.
            if not geom.is_valid:
                geom = geom.buffer(0)

            ind_id = int(props["individual_id"])
            yr = years.loc[ind_id]

            writer.writerow(
                {
                    "individual_id": ind_id,
                    "study_name": props["study_name"],
                    "sex": props["sex"],
                    "segment_id": int(props["segment_id"]),
                    "contour_level": int(props["contour_level"]),
                    "area_km2": round(float(props["area_km2"]), 6),
                    "method": props["method"],
                    # Booleans survive the CSV round-trip more predictably as
                    # 0/1, and ee.Filter.eq() on an integer is unambiguous.
                    "is_range_shift": int(bool(props["is_range_shift"])),
                    "n_core_areas": int(_num(props["n_core_areas"])),
                    "ctmm_model": props["ctmm_model"],
                    "n_gps_points": int(_num(props["n_gps_points"])),
                    "trajectory_days": round(float(_num(props["trajectory_days"])), 4),
                    "year_start": int(yr["year_start"]),
                    "year_end": int(yr["year_end"]),
                    "year_mid": int(yr["year_mid"]),
                    "wkt": geom.wkt,
                }
            )

    size_mb = out_path.stat().st_size / 1e6
    individuals = {f["properties"]["individual_id"] for f in features}
    print(f"  {out_path.relative_to(BASE_DIR)}")
    print(f"    {len(features)} features, {len(individuals)} individuals, {size_mb:.1f} MB")
    return len(features)


# A fix's time weight is capped at this multiple of its own individual's
# median fix interval. Without a cap, a single fix either side of a two-month
# collar outage would carry two months of "use" and could by itself decide
# which ecoregion an animal is said to live in. Four intervals is long enough
# to absorb an ordinary missed schedule and short enough that a real outage
# cannot dominate.
GAP_CAP_INTERVALS = 4


def add_time_weights(points: pd.DataFrame) -> pd.DataFrame:
    """
    Give every fix the number of hours it stands for, as `hours_represented`.

    WHY. The review app measures how much an animal used an ecoregion, and the
    obvious estimator -- count the fixes inside it -- is only unbiased while
    the collar samples at a constant rate. It does not: 26 of 113 individuals
    change their median fix interval by more than 1.5x partway through the
    track, some by 4x. For 17 of those the schedule change coincides with a
    range shift, which is precisely the case where the bias has somewhere to
    go: the animal occupies different ground before and after, so a doubled
    interval halves the apparent use of whichever range came later.

    Weighting each fix by the time it represents -- half the gap behind it plus
    half the gap ahead, the trapezoidal rule -- turns "share of fixes" into
    "share of tracked time", which is what the weight was always meant to say.
    Where sampling is uniform the two agree exactly, so this costs nothing for
    the 87 individuals it does not apply to.

    The fix count is kept alongside it, unchanged, so the two can be compared.
    """
    points = points.sort_values(["individual_id", "millis"], kind="mergesort")

    # Sorting by individual first makes each animal's fixes one contiguous
    # block, so a running offset addresses them without an index lookup.
    weights = np.ones(len(points), dtype="float64")
    start = 0
    for _, group in points.groupby("individual_id", sort=False):
        stop = start + len(group)
        hours = group["millis"].to_numpy() / 3.6e6
        if len(hours) < 2:
            start = stop
            continue

        gaps = np.diff(hours)
        real = gaps[gaps > 0]
        if real.size == 0:
            # Every timestamp identical: nothing to weight by, so fall back to
            # counting, which is what unit weights already do.
            start = stop
            continue

        capped = np.clip(gaps, 0.0, np.median(real) * GAP_CAP_INTERVALS)
        w = np.zeros(len(hours))
        w[:-1] += capped / 2.0
        w[1:] += capped / 2.0
        weights[start:stop] = w
        start = stop

    points = points.copy()
    points["hours_represented"] = np.round(weights, 4)
    return points


def write_gps_points_csv(years: pd.DataFrame) -> int:
    """Merge every GPS fix into one lon/lat CSV for GEE ingestion."""
    movement = pd.read_csv(
        MOVEMENT_CSV, lineterminator=MOVEMENT_LINETERMINATOR, low_memory=False
    )
    movement.columns = [c.strip() for c in movement.columns]

    info = pd.read_csv(ADDITIONAL_INFO_CSV)
    info = info.dropna(subset=["Sex"])
    info["ID"] = info["ID"].astype(int)
    sex_by_id = dict(zip(info["ID"], info["Sex"]))

    timestamps = _parse_timestamps(movement["timestamp"])
    if timestamps.isna().any():
        print(f"    WARNING: {int(timestamps.isna().sum())} timestamps failed to parse")

    points = pd.DataFrame(
        {
            "individual_id": movement[ID_COL].astype(int),
            "study_name": movement["study.name"],
            "country": movement["country"],
            "sex": movement[ID_COL].astype(int).map(sex_by_id),
            "longitude": movement["location.long"],
            "latitude": movement["location.lat"],
            "timestamp": timestamps.dt.strftime("%Y-%m-%d %H:%M:%S"),
            # system:time_start equivalent, so the explorer can order or filter
            # a detail view chronologically without reparsing strings.
            # Cast to ms resolution explicitly: pandas 3 defaults datetime64 to
            # microseconds, so dividing raw int64 by 1e6 would yield seconds.
            "millis": timestamps.astype("datetime64[ms]").astype("int64"),
            # The fix's OWN calendar year, distinct from the individual-level
            # year_mid below. Nothing in the biome workflow needs it; it is
            # here for the per-fix covariate sampling described under
            # "Next steps for IRL training" in the v3 plan, which groups fixes
            # by year so each one meets the landscape of its own moment.
            "fix_year": timestamps.dt.year,
        }
    )

    # Individual-level tracking years repeated on every fix. Redundant on disk,
    # but it lets the review app read them off a single feature instead of
    # aggregating the whole collection -- and individuals 35 and 38 have no
    # home range row to carry them otherwise.
    ids = points["individual_id"]
    points["year_start"] = ids.map(years["year_start"])
    points["year_end"] = ids.map(years["year_end"])
    points["year_mid"] = ids.map(years["year_mid"])

    before = len(points)
    points = points.dropna(subset=["longitude", "latitude"])
    if len(points) != before:
        print(f"    Dropped {before - len(points)} fixes with missing coordinates")

    # After the coordinate drop, so a discarded fix does not leave its share of
    # time attached to the neighbours it no longer sits between.
    points = add_time_weights(points)

    out_path = UPLOAD_DIR / "jaguar_gps_points.csv"
    points.to_csv(out_path, index=False)

    size_mb = out_path.stat().st_size / 1e6
    print(f"  {out_path.relative_to(BASE_DIR)}")
    tracked_days = points["hours_represented"].sum() / 24.0
    print(
        f"    {len(points)} points, {points['individual_id'].nunique()} individuals, "
        f"{size_mb:.1f} MB"
    )
    print(f"    Time weights span {tracked_days:,.0f} tracked days "
          f"(median {points['hours_represented'].median():.2f} h per fix)")
    return len(points)


def main() -> None:
    UPLOAD_DIR.mkdir(exist_ok=True)
    print("--- Preparing Earth Engine ingestion artifacts ---")
    years = load_tracking_years()
    print(f"  Tracking years resolved for {len(years)} individuals "
          f"({years['year_start'].min()}-{years['year_end'].max()})")
    write_home_ranges_csv(years)
    write_gps_points_csv(years)
    print("\nNext: bash upload_gee_assets.sh   (or upload both CSVs via the")
    print("Code Editor Assets tab -> NEW -> CSV file)")


if __name__ == "__main__":
    main()
