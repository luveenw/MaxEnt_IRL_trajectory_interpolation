"""Full-study MCPs and spatially bounded Pantanal candidate groups.

All input/output coordinates are WGS84 longitude/latitude (EPSG:4326).
Distances, radial trimming, hulls, buffers and areas are calculated in
WGS84 / UTM zone 21S (EPSG:32721), in metres. The 56 Pantanal animals in
this study fall wholly within that zone.

Change ``SpatialConfig.growth_buffer_km`` to change how close a new MCP
must be to the current group's MCP union. Five kilometres means a gap of
at most 5 km, NOT two overlapping 5 km buffers (which would allow 10 km).
``export_padding_km`` independently pads the map rectangle. The final,
500 m grid-aligned rectangle must satisfy both ``max_extent_side_km``
and ``max_extent_area_km2``; these caps prevent long chains of neighbours.

The defaults (5 km growth, 5 km map padding, at most 40 x 40 km) are
operational choices, not estimates of a biological boundary. They are
consistent with this cohort's median full-study MCP95 area of about
61 km2 (equivalent circular radius 4.4 km), and bound a 500 m map to
80 x 80 = 6,400 spatial cells. Larger smoothing kernels may require more
map padding; change the padding and budget explicitly in that case.

MCP95 follows adehabitatHR's radial convention: remove fixes farther
than the 95th percentile distance from the mean location, then form the
convex hull. This is a spatial grouping proxy, not a claim that a range
is resident or that 95% utilization probability has been estimated.
See https://stat.ethz.ch/CRAN/web/packages/adehabitatHR/vignettes/adehabitatHR.pdf

Only numpy and pyproj are required. No trajectory-selection or model
module is imported; callers must pass the FULL cleaned study records
before applying week/month/cadence filters.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
from pyproj import CRS, Transformer


@dataclass(frozen=True)
class SpatialConfig:
    """Spatial controls; all user-facing distances are kilometres."""

    mcp_percent: float = 95.0
    growth_buffer_km: float = 5.0
    export_padding_km: float = 5.0
    max_extent_side_km: float = 40.0
    max_extent_area_km2: float = 1600.0
    cell_size_m: float = 500.0
    metric_crs: str = "EPSG:32721"

    def __post_init__(self):
        if not all(math.isfinite(value) for value in (
            self.mcp_percent, self.growth_buffer_km, self.export_padding_km,
            self.max_extent_side_km, self.max_extent_area_km2, self.cell_size_m,
        )):
            raise ValueError("spatial configuration values must be finite")
        if not 0 < self.mcp_percent <= 100:
            raise ValueError("mcp_percent must be in (0, 100]")
        if self.growth_buffer_km < 0 or self.export_padding_km < 0:
            raise ValueError("buffers must be nonnegative")
        if min(self.max_extent_side_km, self.max_extent_area_km2, self.cell_size_m) <= 0:
            raise ValueError("extent limits and cell_size_m must be positive")
        crs = CRS.from_user_input(self.metric_crs)
        if not crs.is_projected or any(
            not math.isclose(axis.unit_conversion_factor, 1.0)
            for axis in crs.axis_info[:2]
        ):
            raise ValueError("metric_crs must be a projected CRS with metre units")


@dataclass
class MCP:
    individual_id: int
    polygon_xy: np.ndarray
    polygon_lonlat: np.ndarray
    area_km2: float
    n_full_fixes: int
    n_hull_input_fixes: int
    radial_cutoff_m: float
    full_start: str
    full_end: str
    study: str
    percent: float
    metric_crs: str
    full_bounds_xy: tuple[float, float, float, float]
    center_xy: tuple[float, float]

    def properties(self) -> dict:
        """Serializable provenance; geometry is exported separately."""
        return {
            "individual_id": self.individual_id,
            "method": "MCP",
            "contour_level": self.percent,
            "area_km2": self.area_km2,
            "n_full_fixes": self.n_full_fixes,
            "n_hull_input_fixes": self.n_hull_input_fixes,
            "n_radially_excluded_fixes": self.n_full_fixes - self.n_hull_input_fixes,
            "radial_cutoff_m": self.radial_cutoff_m,
            "full_start": self.full_start,
            "full_end": self.full_end,
            "study": self.study,
            "metric_crs": self.metric_crs,
            "trimming_method": "distance_to_mean_location_quantile_type7",
            "scope": "full_study_before_temporal_filtering",
        }


def convex_hull(points: Sequence[Sequence[float]]) -> np.ndarray:
    """Counter-clockwise monotone-chain hull, without repeated closing vertex."""
    unique = sorted(set(map(tuple, np.asarray(points, dtype=float))))
    if len(unique) < 3:
        raise ValueError("a polygon requires at least three distinct locations")

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    result = np.asarray(lower[:-1] + upper[:-1], dtype=float)
    if len(result) < 3:
        raise ValueError("locations are collinear; cannot form an MCP polygon")
    return result


def polygon_area_m2(polygon: np.ndarray) -> float:
    # Translating near the origin avoids cancellation with UTM northings.
    p = np.asarray(polygon, dtype=float) - polygon[0]
    return float(abs(np.dot(p[:, 0], np.roll(p[:, 1], -1))
                     - np.dot(p[:, 1], np.roll(p[:, 0], -1))) / 2)


def _bounds(points: np.ndarray) -> tuple[float, float, float, float]:
    return (float(points[:, 0].min()), float(points[:, 1].min()),
            float(points[:, 0].max()), float(points[:, 1].max()))


def _iso(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


@lru_cache(maxsize=16)
def _transformers(metric_crs: str) -> tuple[Transformer, Transformer]:
    """Reuse projection pipelines during repeated temporal candidate searches."""
    return (Transformer.from_crs("EPSG:4326", metric_crs, always_xy=True),
            Transformer.from_crs(metric_crs, "EPSG:4326", always_xy=True))


def build_full_study_mcps(
    records: Iterable[Mapping], ids: Iterable[int] | None = None,
    config: SpatialConfig | None = None,
) -> dict[int, MCP]:
    """Build MCPs from normalized full-study records, without changing records.

    Required record keys: ``individual_id``, ``timestamp``, ``longitude``,
    ``latitude``. Optional ``study`` supplies the study name. Dates must be
    mutually comparable (normally datetime objects). Invalid coordinates
    raise instead of silently changing which fixes define a range.
    """
    cfg = config or SpatialConfig()
    wanted = None if ids is None else set(map(int, ids))
    groups = defaultdict(list)
    for row in records:
        ident = int(row["individual_id"])
        if wanted is None or ident in wanted:
            groups[ident].append(row)
    if wanted is not None and wanted - groups.keys():
        raise ValueError(f"missing full-study records for IDs {sorted(wanted - groups.keys())}")
    forward, inverse = _transformers(cfg.metric_crs)
    output = {}
    for ident, rows in sorted(groups.items()):
        lonlat = np.asarray([(r["longitude"], r["latitude"]) for r in rows], dtype=float)
        if (not np.isfinite(lonlat).all() or np.any(np.abs(lonlat[:, 0]) > 180)
                or np.any(np.abs(lonlat[:, 1]) > 90)):
            raise ValueError(f"invalid WGS84 coordinates for ID {ident}")
        x, y = forward.transform(lonlat[:, 0], lonlat[:, 1])
        points = np.column_stack((x, y))
        center = points.mean(axis=0)
        distances = np.linalg.norm(points - center, axis=1)
        threshold = float(np.quantile(distances, cfg.mcp_percent / 100, method="linear"))
        keep = distances <= threshold  # Keep all tied boundary observations.
        hull = convex_hull(points[keep])
        hull_lon, hull_lat = inverse.transform(hull[:, 0], hull[:, 1])
        output[ident] = MCP(
            individual_id=ident, polygon_xy=hull,
            polygon_lonlat=np.column_stack((hull_lon, hull_lat)),
            area_km2=polygon_area_m2(hull) / 1e6,
            n_full_fixes=len(rows), n_hull_input_fixes=int(keep.sum()),
            radial_cutoff_m=threshold,
            full_start=_iso(min(r["timestamp"] for r in rows)),
            full_end=_iso(max(r["timestamp"] for r in rows)),
            study=str(rows[0].get("study", "")), percent=cfg.mcp_percent,
            metric_crs=cfg.metric_crs, full_bounds_xy=_bounds(points),
            center_xy=tuple(map(float, center)),
        )
    return output


def polygon_distance_m(a: np.ndarray, b: np.ndarray) -> float:
    """Exact Euclidean minimum distance for two convex MCP polygons."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    # Separating axes detect edge intersections and containment alike.
    separated = False
    for polygon in (a, b):
        edges = np.roll(polygon, -1, axis=0) - polygon
        for edge in edges:
            axis = np.asarray((-edge[1], edge[0]))
            norm = np.linalg.norm(axis)
            if norm == 0:
                continue
            axis /= norm
            pa, pb = a @ axis, b @ axis
            if pa.max() < pb.min() - 1e-7 or pb.max() < pa.min() - 1e-7:
                separated = True
                break
        if separated:
            break
    if not separated:
        return 0.0

    def point_to_edges(points, polygon):
        ends = np.roll(polygon, -1, axis=0)
        vectors = ends - polygon
        differences = points[:, None, :] - polygon[None, :, :]
        denom = np.sum(vectors * vectors, axis=1)
        t = np.sum(differences * vectors[None, :, :], axis=2) / denom
        t = np.clip(t, 0, 1)
        residual = differences - t[:, :, None] * vectors[None, :, :]
        return float(np.sqrt(np.min(np.sum(residual * residual, axis=2))))
    return min(point_to_edges(a, b), point_to_edges(b, a))


def extent_for_members(
    mcps: Mapping[int, MCP], members: Iterable[int],
    config: SpatialConfig | None = None,
    extra_lonlat: Iterable[Sequence[float]] = (),
) -> dict:
    """Map rectangle around full-study MCPs, plus optional selected raw fixes.

    A 95% hull is never used to delete trajectory fixes. Include those fixes
    in ``extra_lonlat`` before exporting the final map so that any selected
    excursion outside an MCP95 is covered. Recheck ``within_budget`` then.
    ``area_km2`` is the map's bounding rectangle, not a polygon union area.
    """
    cfg = config or SpatialConfig()
    members = tuple(sorted(set(map(int, members))))
    if not members:
        raise ValueError("extent requires at least one member")
    if any(mcps[i].metric_crs != cfg.metric_crs for i in members):
        raise ValueError("MCPs and spatial configuration must use the same metric CRS")
    points = np.concatenate([mcps[i].polygon_xy for i in members])
    extras = np.asarray(list(extra_lonlat), dtype=float)
    if extras.size:
        if extras.ndim != 2 or extras.shape[1] != 2 or not np.isfinite(extras).all():
            raise ValueError("extra_lonlat must contain finite longitude/latitude pairs")
        if np.any(np.abs(extras[:, 0]) > 180) or np.any(np.abs(extras[:, 1]) > 90):
            raise ValueError("extra_lonlat contains invalid WGS84 coordinates")
        trans, _ = _transformers(cfg.metric_crs)
        x, y = trans.transform(extras[:, 0], extras[:, 1])
        points = np.concatenate((points, np.column_stack((x, y))))
    xmin, ymin, xmax, ymax = _bounds(points)
    core = (xmin, ymin, xmax, ymax)
    pad = cfg.export_padding_km * 1000
    cell = cfg.cell_size_m
    # A globally anchored grid makes extents reproducible across selections.
    xmin, ymin = math.floor((xmin - pad) / cell) * cell, math.floor((ymin - pad) / cell) * cell
    xmax, ymax = math.ceil((xmax + pad) / cell) * cell, math.ceil((ymax + pad) / cell) * cell
    cols, rows = round((xmax - xmin) / cell), round((ymax - ymin) / cell)
    width, height = (xmax - xmin) / 1000, (ymax - ymin) / 1000
    rectangle = np.asarray(((xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax), (xmin, ymin)))
    _, inverse = _transformers(cfg.metric_crs)
    lon, lat = inverse.transform(rectangle[:, 0], rectangle[:, 1])
    # Densified transform_bounds encloses curved projected-rectangle edges.
    wgs84_bbox = inverse.transform_bounds(xmin, ymin, xmax, ymax, densify_pts=21)
    return {
        "members": list(members), "metric_crs": cfg.metric_crs,
        "core_bounds_m": list(core), "bounds_m": [xmin, ymin, xmax, ymax],
        "bounds_wgs84": list(map(float, wgs84_bbox)),
        "rectangle_wgs84": np.column_stack((lon, lat)).tolist(),
        "width_km": width, "height_km": height, "area_km2": width * height,
        "grid_columns": cols, "grid_rows": rows, "grid_cells": cols * rows,
        "cell_size_m": cell, "export_padding_km": cfg.export_padding_km,
        "within_budget": (max(width, height) <= cfg.max_extent_side_km + 1e-9
                          and width * height <= cfg.max_extent_area_km2 + 1e-9),
    }


def grow_cluster_candidates(
    mcps: Mapping[int, MCP], config: SpatialConfig | None = None,
    available_ids: Iterable[int] | None = None, min_members: int = 2,
    include_subgroups: bool = True,
) -> list[dict]:
    """Grow spatial candidates from each seed using fixed km and extent caps.

    A new polygon must touch the existing MCP UNION buffered by
    growth_buffer_km. The entire resulting map rectangle must stay within
    the fixed side/area budgets. A neighbour chain can therefore never
    expand the map indefinitely. At each iteration the feasible addition
    producing the smallest map area wins, then smallest gap, then ID.

    Prefixes from every seed supply multiple candidate member sets for the
    temporal ranking stage. This deterministic heuristic does not claim
    to enumerate every possible subset or find a global optimum.
    """
    cfg = config or SpatialConfig()
    if min_members < 1:
        raise ValueError("min_members must be positive")
    ids = sorted(mcps if available_ids is None else set(map(int, available_ids)))
    if set(ids) - mcps.keys():
        raise ValueError(f"MCPs missing for IDs {sorted(set(ids) - mcps.keys())}")
    distances = {}
    for n, a in enumerate(ids):
        for b in ids[n + 1:]:
            distances[a, b] = polygon_distance_m(mcps[a].polygon_xy, mcps[b].polygon_xy)
    def distance(a, b):
        return distances[min(a, b), max(a, b)]

    extent_cache = {}
    def group_extent(members):
        key = tuple(sorted(members))
        if key not in extent_cache:
            extent_cache[key] = extent_for_members(mcps, key, cfg)
        return extent_cache[key]

    candidates = {}
    for seed in ids:
        members = {seed}
        extent = group_extent(members)
        if not extent["within_budget"]:
            continue
        while True:
            key = tuple(sorted(members))
            if include_subgroups and len(members) >= min_members:
                candidates[key] = {"members": key, "extent": extent}
            additions = []
            for other in ids:
                if other in members:
                    continue
                gap = min(distance(other, member) for member in members)
                if gap > cfg.growth_buffer_km * 1000 + 1e-7:
                    continue
                proposed = group_extent(members | {other})
                if proposed["within_budget"]:
                    additions.append((proposed["area_km2"], gap, other, proposed))
            if not additions:
                if len(members) >= min_members:
                    candidates[key] = {"members": key, "extent": extent}
                break
            _, _, other, extent = min(additions, key=lambda item: item[:3])
            members.add(other)
    return sorted(candidates.values(), key=lambda c: (-len(c["members"]),
                                                      c["extent"]["area_km2"], c["members"]))


def export_geojson(mcps: Mapping[int, MCP], path: str | Path) -> Path:
    """Write full-study MCP polygons with provenance in WGS84 GeoJSON."""
    features = []
    for ident, mcp in sorted(mcps.items()):
        ring = np.concatenate((mcp.polygon_lonlat, mcp.polygon_lonlat[:1])).tolist()
        features.append({"type": "Feature", "id": ident,
                         "properties": mcp.properties(),
                         "geometry": {"type": "Polygon", "coordinates": [ring]}})
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2))
    return target


def configuration_dict(config: SpatialConfig) -> dict:
    return asdict(config)
