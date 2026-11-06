"""Export route-only MaxEnt demonstrations from a frozen selection checkpoint.

Explicit --groups or --all is required. No training, new selection, report edits,
temporal interpolation, cell-run export, or automatic animal split is performed.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np
from pyproj import Transformer

from .pantanal_checkpoint import (digest, file_hash, file_inventory, json_text,
    load_selection_checkpoint, publish_directory, read_table, verify_inventory, write_table)
from .pantanal_irl_temporal import ExportConfig, build_tracks, hours

EXPORT_SCHEMA = "pantanal_plain_maxent_export/1"
ROOT = Path(__file__).resolve().parents[2]


def cell_for_point(point, grid, transformer):
    x, y = transformer.transform(point["longitude"], point["latitude"])
    xmin, ymin, xmax, ymax = grid["bounds"]
    if not (xmin <= x <= xmax and ymin <= y <= ymax):
        raise ValueError("outside_checkpoint_grid")
    col = math.floor((x-xmin)/grid["cell_size_m"])
    row = math.floor((ymax-y)/grid["cell_size_m"])
    # Exact exterior boundaries only. Genuine outliers are never clipped.
    if x == xmax:
        col = grid["cols"]-1
    if y == ymin:
        row = grid["rows"]-1
    if not (0 <= row < grid["rows"] and 0 <= col < grid["cols"]):
        raise ValueError("inconsistent_grid_transform")
    return row, col


def raster_line(start, end):
    """Eight-connected Bresenham; ties use >=dy / <=dx, in input direction."""
    y, x = start
    ey, ex = end
    dx, dy = abs(ex-x), -abs(ey-y)
    sx, sy = (1 if x < ex else -1), (1 if y < ey else -1)
    err, cells = dx+dy, [(y, x)]
    while (y, x) != (ey, ex):
        twice = 2*err
        if twice >= dy:
            err += dy
            x += sx
        if twice <= dx:
            err += dx
            y += sy
        cells.append((y, x))
    return cells


def grid_route(events, cells):
    """Collapse only consecutive repeats, preserving revisits and event links."""
    route = [cells[0]]
    point_indices = [0]
    edges = []
    for i in range(1, len(events)):
        if cells[i] != cells[i-1]:
            connection = raster_line(cells[i-1], cells[i])
            inferred = len(connection) > 2
            for target in connection[1:]:
                prior = route[-1]
                drow, dcol = target[0]-prior[0], target[1]-prior[1]
                edges.append({"from_k": len(route)-1, "to_k": len(route),
                    "from_row": prior[0], "from_col": prior[1], "to_row": target[0], "to_col": target[1],
                    "action_id": 3*(drow+1)+(dcol+1),
                    "construction_type": "inferred_connection" if inferred else "adjacent_anchors",
                    "from_event_key": events[i-1]["source_event_key"],
                    "to_event_key": events[i]["source_event_key"],
                    "bracket_start": events[i-1]["timestamp"].isoformat(),
                    "bracket_end": events[i]["timestamp"].isoformat(),
                    "bracket_hours": hours(events[i-1], events[i])})
                route.append(target)
        point_indices.append(len(route)-1)
    array = np.asarray([[row, col, k] for k, (row, col) in enumerate(route)], dtype=np.int64)
    return array, point_indices, edges


def validate_array(array, grid):
    if array.ndim != 2 or array.shape[1] != 3 or not np.issubdtype(array.dtype, np.integer):
        raise ValueError("Route arrays must have integer [row,col,k] rows")
    if not np.array_equal(array[:, 2], np.arange(len(array))):
        raise ValueError("Move indices must start at zero and increment by one")
    if np.any(array[:, :2] < 0) or np.any(array[:, 0] >= grid["rows"]) or np.any(array[:, 1] >= grid["cols"]):
        raise ValueError("Route array outside grid")
    if len(array) > 1:
        moves = np.abs(np.diff(array[:, :2], axis=0))
        if np.any(moves.max(axis=1) != 1):
            raise ValueError("Plain MaxEnt requires adjacent non-stay moves")


def span_union_hours(spans):
    total, left, right = 0.0, None, None
    for start, end in sorted(spans):
        if left is None:
            left, right = start, end
        elif start <= right:
            right = max(right, end)
        else:
            total += (right-left).total_seconds()/3600
            left, right = start, end
    return total + ((right-left).total_seconds()/3600 if left is not None else 0)


def _select_groups(checkpoint, requested, all_groups, requested_windows):
    if bool(requested) == bool(all_groups):
        raise ValueError("Choose explicit groups or all; there is no implicit production cohort")
    groups = checkpoint["groups"]
    aliases = {g["group_id"]: key for key, g in groups.items()}
    keys = set(groups) if all_groups else {aliases.get(key, key) for key in requested}
    if not keys <= groups.keys():
        raise ValueError(f"Unknown group keys: {sorted(keys-groups.keys())}")
    wanted_windows = set(requested_windows or ())
    if wanted_windows and not wanted_windows <= checkpoint["windows"].keys():
        raise ValueError("Unknown window keys")
    members = [m for m in checkpoint["members"] if m["group_key"] in keys
               and (not wanted_windows or m["window_key"] in wanted_windows)]
    if not members or wanted_windows - {m["window_key"] for m in members}:
        raise ValueError("Selected windows must belong to the explicit group selection")
    return keys, sorted(members, key=lambda m: (m["group_key"], m["window_key"]))


def export_checkpoint(checkpoint_path, output_dir, *, group_keys=None, all_groups=False,
                      window_keys=None, config=None, split_path=None, feature_maps_path=None):
    config = config or ExportConfig()
    checkpoint = load_selection_checkpoint(checkpoint_path)
    selected_groups, members = _select_groups(checkpoint, group_keys, all_groups, window_keys)
    splits = json.loads(Path(split_path).read_text()) if split_path else {}
    if not isinstance(splits, dict) or any(v not in ("train", "validation", "test", "unassigned") for v in splits.values()):
        raise ValueError("Split JSON must map original animal IDs to train/validation/test/unassigned")
    ids = {str(m["individual_id"]) for m in members}
    if split_path and not ids <= splits.keys():
        raise ValueError("A supplied animal split must assign every selected animal")
    maps = json.loads(Path(feature_maps_path).read_text()) if feature_maps_path else {}
    maps = {key: value if isinstance(value,list) else [value] for key,value in maps.items()}
    for key, entries in maps.items():
        for value in entries:
            if key not in checkpoint["grids"] or not value.get("feature_map_key"):
                raise ValueError("Feature-map manifest must reference checkpoint grid keys")
            if value.get("temporal_scope") == "bounded_period":
                start,end=map(datetime.fromisoformat,(value["valid_from"],value["valid_to"]))
                if start>=end or start.tzinfo or end.tzinfo:
                    raise ValueError("Map periods must increase and use the source's unspecified clock convention")
            elif value.get("temporal_scope") != "static_declared":
                raise ValueError("Declare map temporal_scope as bounded_period or static_declared")
            map_path = Path(value["path"])
            if not map_path.is_absolute():
                map_path = Path(feature_maps_path).resolve().parent / map_path
            shape = np.load(map_path, mmap_mode="r", allow_pickle=False).shape
            grid = checkpoint["grids"][key]
            if len(shape) not in (3, 4) or tuple(shape[1:3]) != (grid["rows"], grid["cols"]):
                raise ValueError("Feature-map array dimensions do not match grid")
            value.update(path=str(map_path.resolve()), sha256=file_hash(map_path), shape=list(shape))
    software = {p.name: file_hash(p) for p in (Path(__file__), Path(__file__).with_name("pantanal_irl_temporal.py"),
                                              Path(__file__).with_name("pantanal_checkpoint.py"))}
    identity = {"schema": EXPORT_SCHEMA, "checkpoint_sha256": file_hash(Path(checkpoint_path)/"checkpoint.json"),
        "selection_key": checkpoint["manifest"]["selection_key"], "export_config": asdict(config),
        "group_keys": sorted(selected_groups), "window_keys": sorted({m["window_key"] for m in members}),
        "animal_splits": {ident: splits.get(ident, "unassigned") for ident in sorted(ids)},
        "split_sha256": file_hash(split_path) if split_path else None,
        "feature_maps": maps, "software_sha256": software}
    export_key = "export_" + digest(identity)[:24]
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".export-", dir=root))
    try:
        data = temporary / "data"
        data.mkdir()
        trajectories, links, steps, pairs, window_diagnostics, observation_rows, edge_rows, cut_rows = [], [], [], [], [], [], [], []
        interval_summaries = []
        collar = {int(row["individual_id"]): row for row in read_table(checkpoint["root"] / "collar_metadata.csv")}
        tracks_cache, projected_cache = {}, {}
        used_event_keys = set()
        variants = ("fine", "two_hour") if config.variant == "both" else (config.variant,)

        def emit(group, window, part, variant, collection="independent", pair_id=""):
            grid = checkpoint["grids"][group["grid_key"]]
            events = part["events"]
            event_keys = [p["source_event_key"] for p in events]
            used_event_keys.update(event_keys)
            fragment_key = "fragment_" + digest([window["window_key"], variant, event_keys, asdict(config)])[:24]
            trajectory_id = "trajectory_" + digest([group["group_key"], fragment_key, collection, pair_id])[:24]
            grid_key = group["grid_key"]
            if grid_key not in projected_cache:
                projected_cache[grid_key] = (Transformer.from_crs("EPSG:4326", grid["crs"], always_xy=True), {})
            transform, cache = projected_cache[grid_key]
            cells, geometry_error = [], ""
            for p in events:
                if p["source_event_key"] not in cache:
                    try:
                        cache[p["source_event_key"]] = cell_for_point(p, grid, transform)
                    except ValueError:
                        cache[p["source_event_key"]] = None
                cells.append(cache[p["source_event_key"]])
            if None in cells:
                geometry_error = "outside_checkpoint_grid"
            duration = hours(events[0], events[-1])
            eligible = part["retained"] and not geometry_error
            reason = geometry_error or part["reason"]
            if variant == "two_hour" and not tracks_cache[window["window_key"]]["comparison_eligible"]:
                eligible = False
                reason = reason or "comparison_final_retention_below_minimum"
            array = indices = edges = None
            if not geometry_error:
                array, indices, edges = grid_route(events, cells)
                validate_array(array, grid)
            length = len(edges) if edges is not None else None
            inferred = sum(e["construction_type"] == "inferred_connection" for e in edges) if edges is not None else None
            backend = ("unsupported_geometry" if geometry_error else
                       "unsupported_residence_evidence" if length == 0 else "supported")
            choice = "unique" if length == 1 else "not_checked"
            array_path = ""
            if eligible and length:
                array_path = f"arrays/{group['group_id']}/{collection}/{variant}/{trajectory_id}.npy"
                path = temporary / array_path
                path.parent.mkdir(parents=True, exist_ok=True)
                np.save(path, array, allow_pickle=False)
            split = splits.get(str(window["individual_id"]), "unassigned")
            matches=[entry for entry in maps.get(grid_key,[]) if entry["temporal_scope"]=="static_declared" or
                     (datetime.fromisoformat(entry["valid_from"])<=events[0]["timestamp"] and
                      events[-1]["timestamp"]<datetime.fromisoformat(entry["valid_to"]))]
            if len(matches)>1:
                raise ValueError("Ambiguous feature-map period for fragment")
            features=matches[0] if matches else {}
            metadata = json.loads(group["selection_metadata_json"])
            within_budget = not metadata.get("spatial_violation_codes")
            candidate = bool(eligible and length and choice != "unique" and within_budget)
            row = {"trajectory_id": trajectory_id, "individual_id": window["individual_id"],
                "parent_window_id": window["window_key"], "legacy_window_id": window["window_id"],
                "source_bout_id": f"{window['window_key']}_bout{part['source_bout']:04d}",
                "segment_id": fragment_key, "pair_id": pair_id, "group_key": group["group_key"],
                "group_id": group["group_id"], "grid_key": grid_key, "variant": variant, "collection": collection,
                "model_backend": "plain_maxent_route", "step_semantics": "spatial_move",
                "array_path": array_path, "feature_map_key": features.get("feature_map_key", ""),
                "feature_map_status": "provided" if features else "no_matching_period" if grid_key in maps else "not_supplied",
                "source_event_ids_or_reference": f"data/point_links.csv#trajectory_id={trajectory_id}",
                "evidence_key": "evidence_"+digest([window["individual_id"], event_keys])[:24],
                "source_event_count": len(events), "first_event_key": event_keys[0], "last_event_key": event_keys[-1],
                "first_timestamp": events[0]["timestamp"].isoformat(), "last_timestamp": events[-1]["timestamp"].isoformat(),
                "fragment_duration_hours": duration, "grid_transition_count": length,
                "inferred_transition_count": inferred,
                "inferred_transition_fraction": inferred/length if length else None,
                "elapsed_minutes_per_exported_move": 60*duration/length if length else None,
                "same_cell_observation_edges": sum(a == b for a, b in zip(cells, cells[1:])) if not geometry_error else None,
                "max_observation_gap_hours": max((hours(a,b) for a,b in zip(events,events[1:])), default=0),
                "data_eligible": bool(eligible), "rejection_reason": reason,
                "backend_support_status": backend, "route_choice_status": choice,
                "within_selection_map_budget": within_budget, "optimizer_candidate": candidate,
                "optimizer_exclusion_reason": (reason if not eligible else
                    "unsupported_residence_evidence" if length==0 else "no_route_choice" if choice=="unique" else
                    "selection_map_budget_exceeded" if not within_budget else ""),
                "inputs_bound": bool(candidate and features and split != "unassigned"),
                "training_ready": False, "training_status": "requires_separate_trainer_integration", "split": split}
            trajectories.append(row)
            for i, p in enumerate(events):
                links.append({"trajectory_id": trajectory_id, "ordinal": i,
                    "source_event_key": p["source_event_key"], "event_id": p["event_id"],
                    "grid_k": indices[i] if indices is not None else None,
                    "grid_row": cells[i][0] if cells[i] is not None else None,
                    "grid_col": cells[i][1] if cells[i] is not None else None})
            for edge in edges or []:
                steps.append(dict(trajectory_id=trajectory_id, **edge))
            return row

        # Track-level files occur once per window, independently of group aliases.
        for key in sorted({m["window_key"] for m in members}):
            window = checkpoint["windows"][key]
            events = window["events"]
            used_event_keys.update(p["source_event_key"] for p in events)
            tracks = tracks_cache[key] = build_tracks(events, config)
            full_intervals=[hours(a,b) for a,b in zip(events,events[1:]) if a.get("tag_id")==b.get("tag_id")]
            schedule=collar[window["individual_id"]]
            planned=float(schedule["planned_interval_hours"]) if schedule["planned_interval_hours"] else None
            median=float(np.median(full_intervals)) if full_intervals else None
            interval_summaries.append({"window_key":key,"individual_id":window["individual_id"],
                "interval_count":len(full_intervals),"mean_hours":float(np.mean(full_intervals)) if full_intervals else None,
                "median_hours":median,"iqr_hours":float(np.quantile(full_intervals,.75)-np.quantile(full_intervals,.25)) if full_intervals else None,
                "p90_hours":float(np.quantile(full_intervals,.9)) if full_intervals else None,
                "max_hours":max(full_intervals,default=None),
                "fraction_above_four_hours":sum(dt>4 for dt in full_intervals)/len(full_intervals) if full_intervals else None,
                "planned_interval_hours":planned,"metadata_status":schedule["metadata_status"],
                "median_to_plan_ratio":median/planned if planned and median is not None else None,
                "schedule_deviation_pct":100*(median/planned-1) if planned and median is not None else None,
                "scope":"full_window_before_thinning_or_gap_cuts; no_cross_tag_edges"})
            metric_transform = Transformer.from_crs(4326, checkpoint["manifest"]["selection_config"]["spatial"]["metric_crs"], always_xy=True)
            for variant in variants:
                parts = tracks[variant]
                spans = [(p["events"][0]["timestamp"], p["events"][-1]["timestamp"])
                         for p in parts if p["retained"]]
                support = span_union_hours(spans)
                window_hours = (window["end"]-window["start"]).total_seconds()/3600
                retained_lookup = {p["source_event_key"]: (i, part["retained"])
                                   for i, part in enumerate(parts) for p in part["events"]}
                observations = events if variant == "fine" else tracks["selected"]
                for p in observations:
                    ordinal, retained = retained_lookup[p["source_event_key"]]
                    observation_rows.append({"window_key": key, "individual_id": window["individual_id"],
                        "variant": variant, "source_event_key": p["source_event_key"], "fragment_ordinal": ordinal,
                        "retained_by_fragment_rule": retained,
                        "representation_eligible": True if variant == "fine" else tracks["comparison_eligible"]})
                for i, part in enumerate(parts):
                    previous_vector,previous_regular=None,False
                    for a,b in zip(part["events"],part["events"][1:]):
                        ax,ay = metric_transform.transform(a["longitude"],a["latitude"])
                        bx,by = metric_transform.transform(b["longitude"],b["latitude"])
                        dt = hours(a,b)
                        distance = math.hypot(bx-ax,by-ay)
                        regular=variant=="two_hour" and tracks["comparison_eligible"] and part["retained"] and config.regular_min_hours<=dt<=config.regular_max_hours
                        vector=(bx-ax,by-ay)
                        angle=(math.atan2(previous_vector[0]*vector[1]-previous_vector[1]*vector[0],
                                          previous_vector[0]*vector[0]+previous_vector[1]*vector[1])
                               if previous_vector is not None and math.hypot(*previous_vector)>0 and distance>0 else None)
                        edge_rows.append({"window_key":key,"individual_id":window["individual_id"],"variant":variant,
                            "fragment_ordinal":i,"from_event_key":a["source_event_key"],"to_event_key":b["source_event_key"],
                            "dt_hours":dt,"displacement_m":distance,"displacement_speed_m_per_hour":distance/dt,
                            "retained_by_fragment_rule":part["retained"],
                            "primary_two_hour_metric":regular,"turn_angle_at_from_event_radians":angle,
                            "primary_two_hour_turn_angle":regular and previous_regular and angle is not None})
                        previous_vector,previous_regular=vector,regular
                window_diagnostics.append({"window_key": key, "individual_id": window["individual_id"],
                    "variant": variant, "raw_count": len(events), "selected_count": len(observations),
                    "retained_count": sum(len(p["events"]) for p in parts if p["retained"]),
                    "M": tracks["M"] if variant=="two_hour" else None,
                    "F": tracks["F"] if variant=="two_hour" else None,
                    "A": tracks["A"] if variant=="two_hour" else None,
                    "final_retention_fraction": tracks["final_retention_fraction"] if variant=="two_hour" else None,
                    "affected_point_fraction": tracks["affected_point_fraction"] if variant=="two_hour" else None,
                    "comparison_eligible": tracks["comparison_eligible"] if variant=="two_hour" else None,
                    "window_hours":window_hours, "parent_observed_span_hours":hours(events[0],events[-1]),
                    "bounded_gap_supported_hours":support,"bounded_gap_supported_fraction":support/window_hours,
                    "gap_threshold_hours":config.source_gap_hours if variant=="fine" else config.max_comparison_gap_hours,
                    "leading_unobserved_hours":(events[0]["timestamp"]-window["start"]).total_seconds()/3600,
                    "trailing_unobserved_hours":(window["end"]-events[-1]["timestamp"]).total_seconds()/3600,
                    "max_full_window_source_gap_hours":max((hours(a,b) for a,b in zip(events,events[1:])),default=0),
                    "max_full_window_source_gap_scope":"all_consecutive_events_including_tag_change_boundaries",
                    "max_within_tag_full_window_gap_hours":max(full_intervals,default=None),
                    "coverage_semantics":"fragment_span_union_not_continuously_observed_path"})
            for cut in tracks["cuts"]:
                cut_rows.append(dict(window_key=key, variant="two_hour", **cut))
            for a,b in zip(tracks["fine"],tracks["fine"][1:]):
                cut_rows.append({"window_key":key,"variant":"fine",
                    "from_event_key":a["events"][-1]["source_event_key"],"to_event_key":b["events"][0]["source_event_key"],
                    "gap_hours":hours(a["events"][-1],b["events"][0]),"reason":"source_gap_or_tag_boundary"})
        for member in members:
            group = checkpoint["groups"][member["group_key"]]
            window = checkpoint["windows"][member["window_key"]]
            tracks = tracks_cache[window["window_key"]]
            for variant in variants:
                for part in tracks[variant]:
                    emit(group, window, part, variant)
            if config.variant=="both" and tracks["comparison_eligible"]:
                for part in tracks["two_hour"]:
                    if not part["retained"]:
                        continue
                    start,end = part["events"][0]["timestamp"],part["events"][-1]["timestamp"]
                    fine_events = [p for p in tracks["fine"][part["source_bout"]]["events"] if start<=p["timestamp"]<=end]
                    pair_id="pair_"+digest([group["group_key"],window["window_key"],start,end,asdict(config)])[:24]
                    fine_part=dict(events=fine_events,source_bout=part["source_bout"],
                                   retained=len(fine_events)>=config.min_source_segment_points,
                                   reason="" if len(fine_events)>=config.min_source_segment_points else "short_source_fragment")
                    fine_row=emit(group,window,fine_part,"fine","paired",pair_id)
                    comparison_row=emit(group,window,part,"two_hour","paired",pair_id)
                    pair_ok=fine_row["optimizer_candidate"] and comparison_row["optimizer_candidate"]
                    for row in (fine_row,comparison_row):
                        row["optimizer_candidate"] = pair_ok
                        row["inputs_bound"] = row["inputs_bound"] and pair_ok
                        if not pair_ok and not row["optimizer_exclusion_reason"]:
                            row["optimizer_exclusion_reason"]="paired_other_arm_not_supported_or_informative"
                    pairs.append({"pair_id":pair_id,"group_key":group["group_key"],"window_key":window["window_key"],
                        "individual_id":window["individual_id"],"fine_trajectory_id":fine_row["trajectory_id"],
                        "two_hour_trajectory_id":comparison_row["trajectory_id"],
                        "first_event_key":part["events"][0]["source_event_key"],
                        "last_event_key":part["events"][-1]["source_event_key"],
                        "pair_optimizer_candidate":pair_ok,
                        "pair_status":"both_route_candidates" if pair_ok else "one_or_both_arms_not_informative_or_supported"})

        def table(name, rows, empty_columns):
            columns=list(dict.fromkeys(k for row in rows for k in row)) if rows else empty_columns
            write_table(data/name,rows,columns)
        table("trajectory_manifest.csv",trajectories,["trajectory_id","individual_id","array_path"])
        table("fragment_diagnostics.csv",trajectories,["trajectory_id","individual_id","data_eligible"])
        table("point_links.csv",links,["trajectory_id","ordinal","source_event_key","grid_k"])
        table("grid_steps.csv",steps,["trajectory_id","from_k","to_k","from_row","from_col","to_row","to_col",
            "action_id","construction_type","from_event_key","to_event_key","bracket_start","bracket_end","bracket_hours"])
        table("paired_cases.csv",pairs,["pair_id","group_key","window_key","individual_id","fine_trajectory_id",
            "two_hour_trajectory_id","first_event_key","last_event_key","pair_optimizer_candidate","pair_status"])
        table("window_diagnostics.csv",window_diagnostics,["window_key","individual_id","variant"])
        table("observation_membership.csv",observation_rows,["window_key","variant","source_event_key"])
        table("observation_edges.csv",edge_rows,["window_key","variant","from_event_key","to_event_key"])
        table("comparison_points.csv",[r for r in observation_rows if r["variant"]=="two_hour"],["window_key","source_event_key"])
        table("comparison_edges.csv",[r for r in edge_rows if r["variant"]=="two_hour"],["window_key","from_event_key","to_event_key"])
        table("fix_interval_summary.csv",interval_summaries,["window_key","individual_id","interval_count"])
        table("cuts.csv",cut_rows,["window_key","variant","from_event_key","to_event_key","reason"])
        source_rows=[dict(checkpoint["source"][key],timestamp=checkpoint["source"][key]["timestamp"].isoformat()) for key in sorted(used_event_keys)]
        table("source_points.csv",source_rows,["source_event_key","event_id","timestamp"])
        table("groups.csv",[checkpoint["groups"][k] for k in sorted(selected_groups)],["group_key","group_id","grid_key"])
        table("animal_splits.csv",[{"individual_id":i,"split":splits.get(i,"unassigned")} for i in sorted(ids)], ["individual_id","split"])
        aliases=defaultdict(list)
        for row in trajectories:
            if row["collection"]=="independent":
                aliases[(row["evidence_key"],row["variant"])].append(row)
        alias_rows=[{"evidence_key":key[0],"variant":key[1],"trajectory_ids":[r["trajectory_id"] for r in rows],
                     "group_keys":[r["group_key"] for r in rows],"occurrences":len(rows)} for key,rows in sorted(aliases.items()) if len(rows)>1]
        table("evidence_aliases.csv",alias_rows,["evidence_key","variant","trajectory_ids","group_keys","occurrences"])
        # Lists are isolated by group and collection: never merge alternative
        # groups or independent/paired versions into one accidental training fit.
        lists=defaultdict(list)
        for row in trajectories:
            if row["optimizer_candidate"] and row["array_path"]:
                lists[(row["group_id"],row["collection"],row["variant"],row["split"])].append(row["array_path"][:-4])
        for (group,collection,variant,split), basenames in sorted(lists.items()):
            path=temporary/"lists"/group/collection/variant/f"{split}.txt"
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text("\n".join(sorted(basenames))+"\n")
        (temporary/"grids.json").write_text(json_text({checkpoint["groups"][k]["grid_key"]:checkpoint["grids"][checkpoint["groups"][k]["grid_key"]] for k in selected_groups})+"\n")
        manifest={**identity,"export_key":export_key,
            "selection_policy":checkpoint["manifest"]["selection_policy"],
            "selection_rank_policy":"export policy does not update checkpoint group ranks",
            "scope":"data_export_only; no trainer repair or model fit",
            "cell_runs_status":"deferred_not_generated",
            "split_status":"provided" if split_path else "unassigned",
            "rasterization_assumptions":"eight neighbors; no barrier mask supplied; diagonal corner crossing allowed",
            "overlap_policy":"alternative group/collection lists are separate fits; pooled trainer must deduplicate shared events/edges",
            "counts":{"source_events":len(source_rows),"windows":len(tracks_cache),"groups":len(selected_groups),
                "manifest_fragments":len(trajectories),"arrays":sum(bool(r["array_path"]) for r in trajectories),
                "pairs":len(pairs),"training_ready_fragments":sum(r["training_ready"] for r in trajectories)},
            "files":file_inventory(temporary)}
        (temporary/"export_manifest.json").write_text(json_text(manifest)+"\n")
        validate_export(temporary)
        return publish_directory(temporary,root/export_key,"export_manifest.json")
    except BaseException:
        shutil.rmtree(temporary,ignore_errors=True)
        raise


def validate_export(path):
    """Check standalone artifact integrity and scientific identity contracts."""
    path=Path(path)
    manifest=json.loads((path/"export_manifest.json").read_text())
    if manifest.get("schema")!=EXPORT_SCHEMA:
        raise ValueError("Unsupported export schema")
    verify_inventory(path,manifest)
    rows=list(read_table(path/"data"/"trajectory_manifest.csv"))
    by_id={r["trajectory_id"]:r for r in rows}
    if len(by_id)!=len(rows):
        raise ValueError("Duplicate trajectory ID")
    grids=json.loads((path/"grids.json").read_text())
    source={r["source_event_key"]:r for r in read_table(path/"data"/"source_points.csv")}
    counts=defaultdict(int)
    for link in read_table(path/"data"/"point_links.csv"):
        if link["trajectory_id"] not in by_id or link["source_event_key"] not in source:
            raise ValueError("Invalid exported event link")
        row=by_id[link["trajectory_id"]]
        if source[link["source_event_key"]]["individual_id"]!=row["individual_id"]:
            raise ValueError("Exported trajectory has multiple animal owners")
        counts[link["trajectory_id"]]+=1
    edge_counts,inferred_counts=defaultdict(int),defaultdict(int)
    for edge in read_table(path/"data"/"grid_steps.csv"):
        ident=edge["trajectory_id"]
        if ident not in by_id or int(edge["from_k"])!=edge_counts[ident] or int(edge["to_k"])!=edge_counts[ident]+1:
            raise ValueError("Non-consecutive grid edge provenance")
        if edge["from_event_key"] not in source or edge["to_event_key"] not in source:
            raise ValueError("Missing source brackets for grid edge")
        edge_counts[ident]+=1
        inferred_counts[ident]+=edge["construction_type"]=="inferred_connection"
    for row in rows:
        if counts[row["trajectory_id"]]!=int(row["source_event_count"]):
            raise ValueError("Export fragment count mismatch")
        if row["split"]!=manifest["animal_splits"][row["individual_id"]]:
            raise ValueError("Inconsistent animal split")
        if row["grid_transition_count"] and (edge_counts[row["trajectory_id"]]!=int(row["grid_transition_count"]) or
                inferred_counts[row["trajectory_id"]]!=int(row["inferred_transition_count"])):
            raise ValueError("Grid-transition provenance counts disagree")
        if row["array_path"]:
            if row["array_path"] not in manifest["files"] or not (path/row["array_path"]).resolve().is_relative_to(path.resolve()):
                raise ValueError("Unverified trajectory array path")
            array=np.load(path/row["array_path"],allow_pickle=False)
            validate_array(array,grids[row["grid_key"]])
            if len(array)-1!=int(row["grid_transition_count"]):
                raise ValueError("Exported horizon mismatch")
    for pair in read_table(path/"data"/"paired_cases.csv"):
        a,b=by_id[pair["fine_trajectory_id"]],by_id[pair["two_hour_trajectory_id"]]
        for field in ("individual_id","parent_window_id","first_event_key","last_event_key","grid_key","feature_map_key","split"):
            if a[field]!=b[field]:
                raise ValueError(f"Paired arms disagree on {field}")
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint",required=True)
    parser.add_argument("--output",default=str(ROOT/"analysis"/"pantanal_irl_exports"))
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--groups",nargs="+",help="Explicit checkpoint group keys or display IDs, e.g. G01 G03")
    choice.add_argument("--all",action="store_true",help="Explicitly export all checkpoint groups as separate alternatives")
    parser.add_argument("--windows",nargs="+",help="Optional window-key filter within selected groups")
    parser.add_argument("--variant",choices=("fine","two_hour","both"),default="both")
    parser.add_argument("--animal-splits",help="JSON mapping original animal IDs to train/validation/test/unassigned")
    parser.add_argument("--feature-map-manifest",help="Optional JSON keyed by grid key; entries require feature_map_key, NPY path, and explicit static/period applicability")
    parser.add_argument("--source-gap-hours",type=float,default=4)
    parser.add_argument("--min-source-segment-points",type=int,default=5)
    parser.add_argument("--min-comparison-segment-points",type=int,default=5)
    parser.add_argument("--min-final-retention",type=float,default=0.0,
        help="Optional final F/M minimum for two_hour only, in [0,1]; 0 disables the ratio gate (default). Nonempty retained evidence is always required; .8 restores the former policy.")
    parser.add_argument("--max-affected-fraction",type=float,default=.2)
    args=parser.parse_args()
    config=ExportConfig(variant=args.variant,source_gap_hours=args.source_gap_hours,
        min_source_segment_points=args.min_source_segment_points,
        min_comparison_segment_points=args.min_comparison_segment_points,
        min_final_retention_fraction=args.min_final_retention,max_affected_fraction=args.max_affected_fraction)
    result=export_checkpoint(args.checkpoint,args.output,group_keys=args.groups,all_groups=args.all,
        window_keys=args.windows,config=config,split_path=args.animal_splits,feature_maps_path=args.feature_map_manifest)
    print(result)


if __name__=="__main__":
    main()
