"""Versioned, lossless source checkpoints for the Pantanal selector.

Only events in returned candidate windows are checkpointed, not every scanned
window or the entire study. All cohort support/QC summaries are preserved.
Neither this module nor its loader changes selection, ranks, or report files.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

SCHEMA = "pantanal_selection_checkpoint/1"
SELECTION_POLICY = "pantanal_selection_descriptive_full_record_support_v3"


def json_text(value):
    def default(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Path):
            return str(obj)
        if hasattr(obj, "item"):
            return obj.item()
        raise TypeError(type(obj).__name__)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=default,
                      allow_nan=False)


def digest(value):
    return hashlib.sha256(json_text(value).encode()).hexdigest()


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_table(path, rows, columns):
    """Explicit headers also describe empty products; iterate rather than copy."""
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json_text(value) if isinstance(value, (dict, list, tuple))
                             else value for key, value in row.items()})


def read_table(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def file_inventory(root):
    inventory = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            item = {"sha256": file_hash(path), "bytes": path.stat().st_size}
            if path.suffix == ".csv":
                item["rows"] = sum(1 for _ in read_table(path))
            inventory[path.relative_to(root).as_posix()] = item
    return inventory


def verify_inventory(root, manifest):
    root = Path(root).resolve()
    for name, info in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"Missing or unsafe artifact path: {name}")
        if path.stat().st_size != info["bytes"] or file_hash(path) != info["sha256"]:
            raise ValueError(f"Artifact hash mismatch: {name}")
        if "rows" in info and sum(1 for _ in read_table(path)) != info["rows"]:
            raise ValueError(f"Artifact row count mismatch: {name}")


def publish_directory(temporary, destination, manifest_name):
    """Atomic directory publication; identical reruns reuse verified contents."""
    temporary, destination = Path(temporary), Path(destination)
    if destination.exists():
        old = json.loads((destination / manifest_name).read_text())
        new = json.loads((temporary / manifest_name).read_text())
        verify_inventory(destination, old)
        if old != new:
            raise FileExistsError(f"Refusing to replace a different artifact: {destination}")
        shutil.rmtree(temporary)
    else:
        os.rename(temporary, destination)
    return destination


def _metadata(path, wanted):
    if path is None or not Path(path).is_file():
        return {i: {"individual_id": i, "metadata_status": "missing",
                    "planned_interval_hours": None, "metadata_json": {}} for i in wanted}
    by_id = defaultdict(list)
    for row in read_table(path):
        if not any(value.strip() for value in row.values() if value):
            continue  # The supplied metadata file has trailing empty CSV rows.
        by_id[int(row["ID"])].append(row)
    result = {}
    for ident in wanted:
        entries = by_id[ident]
        status, planned = "missing", None
        if len(entries) > 1:
            status = "conflicting_rows"
        elif entries:
            try:
                planned = float(entries[0]["Planned Schedule (h)"])
                if not math.isfinite(planned) or planned <= 0:
                    raise ValueError()
                status = "available"
            except (ValueError, TypeError, KeyError):
                planned, status = None, "unavailable_schedule"
        # Names/contact details do not support movement processing.
        public = [{k: v for k, v in row.items() if k not in ("Contact", "Project Leader")}
                  for row in entries]
        result[ident] = {"individual_id": ident, "metadata_status": status,
                         "planned_interval_hours": planned, "metadata_json": public}
    return result


def load_individual_sexes(path, wanted):
    """Read sex independently of schedule validity; never infer missing values."""
    result = {}
    for ident, metadata in _metadata(path, wanted).items():
        entries = metadata["metadata_json"]
        if len(entries) != 1:
            result[ident] = {"sex": "unknown", "sex_metadata_status":
                             "conflicting_rows" if entries else "missing"}
            continue
        value = str(entries[0].get("Sex") or "").strip().lower()
        sex = {"male": "male", "m": "male", "female": "female", "f": "female"}.get(value, "unknown")
        result[ident] = {"sex": sex, "sex_metadata_status":
                         "available" if sex != "unknown" else "unavailable_sex"}
    return result


def write_selection_checkpoint(config, records, temporal, groups, mcps, parse_audit,
                               *, checkpoint_root=None, collar_metadata_path=None):
    """Preserve every returned candidate, including those absent from groups.

    The selector remains the legacy two-hour/5%-fragment-loss selection policy.
    Export policies have separate hashes and cannot retroactively change ranks.
    """
    source_hash = file_hash(config.csv_path)
    config_value = asdict(config)
    policy = {k: v for k, v in config_value.items()
              if k not in ("csv_path", "output_dir", "top_n", "report_limit")}
    code_dir = Path(__file__).parent
    software = {name: file_hash(code_dir / name) for name in (
        "movement_processor_pantanal.py", "pantanal_temporal.py", "movement_temporal.py",
        "pantanal_spatial.py", "pantanal_calendar.py", "pantanal_checkpoint.py")}
    metadata_hash = (file_hash(collar_metadata_path)
                     if collar_metadata_path and Path(collar_metadata_path).is_file() else None)
    identity = {"schema": SCHEMA, "source_sha256": source_hash,
                "collar_metadata_sha256": metadata_hash, "selection_config": policy,
                "software_sha256": software}
    selection_key = "selection_" + digest(identity)[:24]
    root = Path(checkpoint_root or Path(config.output_dir) / "checkpoints")
    root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".checkpoint-", dir=root))
    try:
        by_id = defaultdict(list)
        for row in records:
            by_id[row["individual_id"]].append(row)
        for values in by_id.values():
            values.sort(key=lambda r: (r["timestamp"], str(r["event_id"])))
        times = {i: [r["timestamp"] for r in rows] for i, rows in by_id.items()}
        source_by_row, source_key_by_row, windows, links = {}, {}, [], []
        window_keys = {}
        for kind, items in (("main", temporal["candidates"]),
                            ("relaxed", temporal["relaxed_candidates"])):
            for window in sorted(items, key=lambda w: w["window_id"]):
                ident = window["individual_id"]
                lo = bisect_left(times[ident], window["start"])
                hi = bisect_right(times[ident], window["end"])
                values = by_id[ident][lo:hi]
                key = "window_" + digest([source_hash, ident, window["start"], window["end"]])[:24]
                if window["window_id"] in window_keys:
                    raise ValueError("Duplicate candidate window")
                window_keys[window["window_id"]] = key
                for ordinal, row in enumerate(values):
                    source_row = row["source_row"]
                    event_key = "event_" + digest([source_hash, ident, str(row["event_id"]), source_row])[:24]
                    source_by_row[source_row] = row
                    source_key_by_row[source_row] = event_key
                    links.append({"window_key": key, "ordinal": ordinal,
                                  "source_event_key": event_key, "context_only": False})
                scalar = {k: v for k, v in window.items() if k not in ("points", "segments")}
                windows.append({"window_key": key, "window_id": window["window_id"],
                    "individual_id": ident, "candidate_list": kind,
                    "start": window["start"].isoformat(), "end": window["end"].isoformat(),
                    "end_inclusive": True, "source_count": len(values),
                    "source_first": values[0]["timestamp"].isoformat(),
                    "source_last": values[-1]["timestamp"].isoformat(),
                    "selection_metadata_json": scalar})
        source, rejected = [], []
        valid_rows = {r["source_row"] for r in records}
        wanted = set(config.individual_ids)
        # Re-read in a stream to preserve original timestamp spelling, tags and
        # all available accuracy columns without changing legacy record exports.
        with Path(config.csv_path).open(newline="", encoding="utf-8-sig") as handle:
            for line, original in enumerate(csv.DictReader(handle), 2):
                ident = int(original["individual.local.identifier (ID)"])
                if ident not in wanted:
                    continue
                if line not in valid_rows:
                    rejected.append({"source_row": line, "individual_id": ident,
                        "reason": "invalid_timestamp_or_coordinate", "original_record_json": original})
                if line not in source_by_row:
                    continue
                row = source_by_row[line]
                source.append({"source_event_key": source_key_by_row[line],
                    "event_id": str(row["event_id"]), "individual_id": ident,
                    "source_row": line, "timestamp": row["timestamp"].isoformat(),
                    "original_timestamp": original["timestamp"], "timezone_status": "unspecified",
                    "longitude": row["longitude"], "latitude": row["latitude"],
                    "study": row["study"], "country": row.get("country", ""),
                    "tag_id": original.get("tag.local.identifier", ""),
                    "qc_status": "accepted", "original_record_json": original})
        source.sort(key=lambda r: (r["individual_id"], r["timestamp"], r["source_row"]))
        group_rows, member_rows, grids = [], [], {}
        for group in sorted(groups, key=lambda g: (g["candidate_list"], g["rank"])):
            grid = {"crs": f"EPSG:{group['epsg']}", "bounds": group["bounds"],
                    "rows": group["grid_rows"], "cols": group["grid_cols"],
                    "cell_size_m": config.spatial.cell_size_m,
                    "origin": "upper_left", "row_direction": "south", "col_direction": "east",
                    "outer_boundary": "inclusive_last_cell_exact_boundary_only",
                    "action_offsets": [[r, c] for r in (-1, 0, 1) for c in (-1, 0, 1) if r or c],
                    "barrier_status": "not_supplied", "diagonal_corner_crossing": "allowed"}
            grid_key = "grid_" + digest(grid)[:24]
            grids[grid_key] = dict(grid_key=grid_key, **grid)
            member_keys = sorted(window_keys[w["window_id"]] for w in group["windows"])
            group_key = "group_" + digest([selection_key, member_keys, grid_key])[:24]
            scalar = {k: v for k, v in group.items()
                      if k not in ("windows", "is_reported", "is_shortlisted")}
            group_rows.append({"group_key": group_key, "group_id": group["group_id"],
                "grid_key": grid_key, "candidate_list": group["candidate_list"], "rank": group["rank"],
                "feature_map_key": "", "feature_map_status": "not_supplied",
                "selection_metadata_json": scalar})
            for w in sorted(group["windows"], key=lambda w: w["individual_id"]):
                member_rows.append({"group_key": group_key, "window_key": window_keys[w["window_id"]],
                                    "individual_id": w["individual_id"]})
        if len({g["group_key"] for g in group_rows}) != len(group_rows):
            raise ValueError("Generated group identities collide")
        metadata = _metadata(collar_metadata_path, config.individual_ids)
        tables = {
            "source_points.csv": (source, ["source_event_key", "event_id", "individual_id", "source_row",
                "timestamp", "original_timestamp", "timezone_status", "longitude", "latitude", "study",
                "country", "tag_id", "qc_status", "original_record_json"]),
            "windows.csv": (windows, ["window_key", "window_id", "individual_id", "candidate_list", "start",
                "end", "end_inclusive", "source_count", "source_first", "source_last", "selection_metadata_json"]),
            "window_events.csv": (links, ["window_key", "ordinal", "source_event_key", "context_only"]),
            "groups.csv": (group_rows, ["group_key", "group_id", "grid_key", "candidate_list", "rank",
                "feature_map_key", "feature_map_status", "selection_metadata_json"]),
            "group_members.csv": (member_rows, ["group_key", "window_key", "individual_id"]),
            "cohort_audit.csv": ([{"individual_id": r["individual_id"], "audit_json": r}
                                   for r in temporal["individuals"]], ["individual_id", "audit_json"]),
            "qc_rejections.csv": (rejected, ["source_row", "individual_id", "reason", "original_record_json"]),
            "collar_metadata.csv": ([metadata[i] for i in sorted(metadata)],
                ["individual_id", "metadata_status", "planned_interval_hours", "metadata_json"]),
            "mcp_summary.csv": ([{"individual_id": i, "properties_json": m.properties(),
                "polygon_xy_json": m.polygon_xy.tolist()} for i, m in sorted(mcps.items())],
                ["individual_id", "properties_json", "polygon_xy_json"]),
        }
        for name, (rows, columns) in tables.items():
            write_table(temporary / name, rows, columns)
        (temporary / "grids.json").write_text(json_text(grids) + "\n")
        manifest = {**identity, "selection_key": selection_key,
            "source_scope": "union_of_returned_candidate_windows_not_all_scanned_windows_or_full_study",
            "selection_policy": SELECTION_POLICY,
            "source_timezone": "unspecified; no conversion", "window_boundary": "inclusive_both_ends",
            "parse_audit": dict(parse_audit), "cohort_ids": list(config.individual_ids),
            "counts": {"source_events": len(source), "windows": len(windows), "groups": len(group_rows),
                       "group_members": len(member_rows), "cohort_individuals": len(config.individual_ids)},
            "rasterization": "exporter_defined_and_versioned_not_applied_in_checkpoint",
            "files": file_inventory(temporary)}
        (temporary / "checkpoint.json").write_text(json_text(manifest) + "\n")
        load_selection_checkpoint(temporary)
        return publish_directory(temporary, root / selection_key, "checkpoint.json")
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def load_selection_checkpoint(path):
    """Validate hashes/foreign keys and return self-contained typed records."""
    root = Path(path)
    manifest = json.loads((root / "checkpoint.json").read_text())
    if manifest.get("schema") != SCHEMA:
        raise ValueError("Unsupported selection checkpoint schema")
    verify_inventory(root, manifest)

    def keyed(name, key):
        rows = list(read_table(root / name))
        result = {r[key]: r for r in rows}
        if len(result) != len(rows):
            raise ValueError(f"Duplicate {key} in {name}")
        return result

    source = keyed("source_points.csv", "source_event_key")
    for row in source.values():
        row["individual_id"] = int(row["individual_id"])
        row["timestamp"] = datetime.fromisoformat(row["timestamp"])
        row["longitude"], row["latitude"] = float(row["longitude"]), float(row["latitude"])
        if not (-180 <= row["longitude"] <= 180 and -90 <= row["latitude"] <= 90):
            raise ValueError("Invalid checkpoint coordinate")
    windows, groups = keyed("windows.csv", "window_key"), keyed("groups.csv", "group_key")
    events = defaultdict(list)
    for row in read_table(root / "window_events.csv"):
        if row["window_key"] not in windows or row["source_event_key"] not in source:
            raise ValueError("Invalid window-event foreign key")
        if row["context_only"] != "False":
            raise ValueError("Schema 1 does not export context-only events")
        events[row["window_key"]].append((int(row["ordinal"]), source[row["source_event_key"]]))
    for key, w in windows.items():
        w["individual_id"] = int(w["individual_id"])
        w["start"], w["end"] = datetime.fromisoformat(w["start"]), datetime.fromisoformat(w["end"])
        ordered = sorted(events[key], key=lambda pair: pair[0])
        if [p[0] for p in ordered] != list(range(int(w["source_count"]))):
            raise ValueError("Window event count/order mismatch")
        w["events"] = [p[1] for p in ordered]
        if len({p["source_event_key"] for p in w["events"]}) != len(ordered):
            raise ValueError("Duplicate source event in window")
        for index, point in enumerate(w["events"]):
            if point["individual_id"] != w["individual_id"] or not w["start"] <= point["timestamp"] <= w["end"]:
                raise ValueError("Window ownership or time bounds mismatch")
            if index and point["timestamp"] <= w["events"][index - 1]["timestamp"]:
                raise ValueError("Non-increasing window timestamps")
    grids = json.loads((root / "grids.json").read_text())
    members = list(read_table(root / "group_members.csv"))
    seen = set()
    for row in members:
        pair = (row["group_key"], row["window_key"])
        if pair in seen or pair[0] not in groups or pair[1] not in windows:
            raise ValueError("Duplicate or invalid group membership")
        seen.add(pair)
        if int(row["individual_id"]) != windows[pair[1]]["individual_id"]:
            raise ValueError("Group member ownership mismatch")
    for g in groups.values():
        if g["grid_key"] not in grids:
            raise ValueError("Missing group grid")
    expected = manifest["counts"]
    if (len(source), len(windows), len(groups), len(members)) != (
            expected["source_events"], expected["windows"], expected["groups"], expected["group_members"]):
        raise ValueError("Checkpoint counts disagree")
    return {"root": root, "manifest": manifest, "source": source, "windows": windows,
            "groups": groups, "members": members, "grids": grids}
