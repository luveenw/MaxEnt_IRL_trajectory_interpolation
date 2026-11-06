"""Regression checks for spatial selection risks, with synthetic telemetry only."""

from datetime import datetime, timedelta

import numpy as np
import pytest
from pyproj import Transformer

from .pantanal_spatial import (
    MCP,
    SpatialConfig,
    build_full_study_mcps,
    extent_for_members,
    grow_cluster_candidates,
    polygon_area_m2,
    polygon_distance_m,
)


ORIGIN = np.array([500_000.0, 7_800_000.0])
TO_WGS84 = Transformer.from_crs(32721, 4326, always_xy=True)
TO_METRIC = Transformer.from_crs(4326, 32721, always_xy=True)


def records_for_xy(points, individual_id=12):
    """Daily observations preserve an independently known full study duration."""
    lon, lat = TO_WGS84.transform(points[:, 0], points[:, 1])
    return [
        {"individual_id": individual_id,
         "timestamp": datetime(2010, 1, 1) + timedelta(days=i),
         "longitude": float(x), "latitude": float(y), "study": "synthetic"}
        for i, (x, y) in enumerate(zip(lon, lat))
    ]


def square_mcp(ident, easting_offset=0):
    """One-square-kilometre hulls isolate clustering from radial trimming."""
    points = ORIGIN + [easting_offset, 0] + np.array(
        [[0, 0], [1_000, 0], [1_000, 1_000], [0, 1_000]], dtype=float
    )
    lon, lat = TO_WGS84.transform(points[:, 0], points[:, 1])
    return MCP(
        individual_id=ident, polygon_xy=points,
        polygon_lonlat=np.column_stack([lon, lat]), area_km2=1,
        n_full_fixes=4, n_hull_input_fixes=4, radial_cutoff_m=1_000,
        full_start="2010-01-01T00:00:00", full_end="2010-01-04T00:00:00",
        study="synthetic", percent=95, metric_crs="EPSG:32721",
        full_bounds_xy=(points[0, 0], points[0, 1], points[2, 0], points[2, 1]),
        center_xy=tuple(points.mean(axis=0)),
    )


def test_mcp95_trims_extremes_only_for_hull_and_preserves_full_duration():
    theta = np.linspace(0, 2 * np.pi, 95, endpoint=False)
    core = ORIGIN + np.column_stack([500 * np.cos(theta), 500 * np.sin(theta)])
    excursions = ORIGIN + np.array([[10_000 + i * 100, i * 100] for i in range(5)])
    records = records_for_xy(np.concatenate([core, excursions]))
    original = [dict(record) for record in records]

    mcp95 = build_full_study_mcps(records)[12]
    mcp100 = build_full_study_mcps(records, config=SpatialConfig(mcp_percent=100))[12]

    assert mcp95.n_full_fixes == mcp100.n_full_fixes == 100
    assert mcp95.n_hull_input_fixes == 95
    assert mcp100.n_hull_input_fixes == 100
    assert mcp100.area_km2 > 5 * mcp95.area_km2
    assert mcp95.full_start == records[0]["timestamp"].isoformat()
    assert mcp95.full_end == records[-1]["timestamp"].isoformat()
    assert mcp95.full_bounds_xy[2] > mcp95.polygon_xy[:, 0].max() + 9_000
    assert mcp95.properties()["scope"] == "full_study_before_temporal_filtering"
    assert records == original  # Excursion telemetry is available for training.


def test_polygon_distance_handles_gap_containment_and_touching():
    first = square_mcp(1).polygon_xy
    assert polygon_area_m2(first) == pytest.approx(1_000_000)
    assert polygon_distance_m(first, first + [3_000, 0]) == pytest.approx(2_000)
    assert polygon_distance_m(first, first + [4_000, 5_000]) == pytest.approx(5_000)
    assert polygon_distance_m(first, first + [1_000, 1_000]) == 0
    inner = ORIGIN + (first - ORIGIN) * 0.5 + [100, 100]
    assert polygon_distance_m(first, inner) == 0


def test_growth_buffer_means_polygon_gap_not_two_overlapping_buffers():
    # Hull edges are 8 km apart: two 5 km buffers would overlap, but a 5 km
    # growth threshold must reject this pair. At 8 km it becomes admissible.
    mcps = {1: square_mcp(1), 2: square_mcp(2, 9_000)}
    assert polygon_distance_m(mcps[1].polygon_xy, mcps[2].polygon_xy) == 8_000
    assert grow_cluster_candidates(mcps, SpatialConfig(growth_buffer_km=5)) == []
    accepted = grow_cluster_candidates(mcps, SpatialConfig(growth_buffer_km=8))
    assert [group["members"] for group in accepted] == [(1, 2)]


def test_neighbour_chain_is_bounded_by_final_map_extent():
    # Every adjacent pair is within 4 km, but the whole 96 km chain cannot
    # become a group. Three members span 11 km; four would span 16 km.
    mcps = {i: square_mcp(i, i * 5_000) for i in range(20)}
    config = SpatialConfig(growth_buffer_km=4, export_padding_km=0,
                           max_extent_side_km=12, max_extent_area_km2=144)
    groups = grow_cluster_candidates(mcps, config)
    assert max(len(group["members"]) for group in groups) == 3
    assert all(group["extent"]["width_km"] <= 12 for group in groups)
    assert all(group["extent"]["within_budget"] for group in groups)
    assert len(groups) == len({group["members"] for group in groups})


def test_selected_excursion_expands_map_and_can_fail_budget():
    mcps = {1: square_mcp(1)}
    baseline = extent_for_members(mcps, [1])
    excursion_xy = ORIGIN + [45_000, 500]
    excursion = TO_WGS84.transform(*excursion_xy)
    expanded = extent_for_members(mcps, [1], extra_lonlat=[excursion])

    assert baseline["within_budget"]
    assert not expanded["within_budget"]
    assert expanded["area_km2"] > baseline["area_km2"]
    xmin, ymin, xmax, ymax = expanded["bounds_m"]
    assert xmin <= excursion_xy[0] <= xmax and ymin <= excursion_xy[1] <= ymax
    assert xmax - excursion_xy[0] >= 5_000 - 1e-6
    assert expanded["width_km"] * expanded["height_km"] == expanded["area_km2"]


def test_metric_calculation_wgs84_roundtrip_and_grid_dimensions():
    points = square_mcp(1).polygon_xy
    mcp = build_full_study_mcps(records_for_xy(points),
                                config=SpatialConfig(mcp_percent=100))[12]
    assert mcp.area_km2 == pytest.approx(1, abs=1e-8)
    x, y = TO_METRIC.transform(mcp.polygon_lonlat[:, 0], mcp.polygon_lonlat[:, 1])
    np.testing.assert_allclose(np.column_stack([x, y]), mcp.polygon_xy, atol=1e-6, rtol=0)
    # Exact metric input avoids a floating roundtrip placing a hull vertex just
    # outside a global grid line and legitimately adding an edge grid cell.
    extent = extent_for_members({1: square_mcp(1)}, [1])
    assert extent["width_km"] == extent["height_km"] == 11
    assert extent["grid_columns"] == extent["grid_rows"] == 22
    assert extent["grid_cells"] == 484
    assert extent["area_km2"] == 121
    assert extent["metric_crs"] == "EPSG:32721"
    with pytest.raises(ValueError, match="projected CRS with metre units"):
        SpatialConfig(metric_crs="EPSG:4326")
    with pytest.raises(ValueError, match="projected CRS with metre units"):
        SpatialConfig(metric_crs="EPSG:2277")  # US survey feet.
