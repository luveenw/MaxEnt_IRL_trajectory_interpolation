"""Export one explicitly selected seasonal collection on its canonical local maps.

Arrays use the established integer [row, col, k] convention; k is a spatial
move index. This adapter preserves fine/two-hour and paired diagnostics without
changing the locked selector, checkpoint loader, or original exporter.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import tempfile
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .export_pantanal_irl import EXPORT_SCHEMA, ROOT, export_checkpoint, validate_export
from .pantanal_checkpoint import (digest, file_hash, file_inventory, json_text,
                                 load_selection_checkpoint, read_table, write_table)
from .pantanal_irl_temporal import ExportConfig

SEASONAL_CHECKPOINT_SCHEMA = "pantanal_seasonal_checkpoint/1"
SEASONAL_EXPORT_SCHEMA = "pantanal_seasonal_export/1"


def _safe(value):
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(value))


def _table(path, rows, fallback):
    columns = list(dict.fromkeys(k for row in rows for k in row)) or fallback
    write_table(path, rows, columns)


def _collection_plan(checkpoint, collection_id):
    root, manifest = checkpoint["root"], checkpoint["manifest"]
    if manifest.get("seasonal_schema") != SEASONAL_CHECKPOINT_SCHEMA:
        raise ValueError("Expected a seasonal selection checkpoint")
    required = ("seasons.json", "collections.csv", "collection_members.csv", "selector_points.csv")
    if any(name not in manifest["files"] for name in required):
        raise ValueError("Seasonal checkpoint must inventory season, collection and selector-point files")
    seasons = json.loads((root / "seasons.json").read_text())
    if not isinstance(seasons, (dict, list)) or not seasons:
        raise ValueError("Missing season definitions")
    collections = list(read_table(root / "collections.csv"))
    matches = [r for r in collections if r["collection_id"] == collection_id]
    if len(matches) != 1:
        raise ValueError("Choose exactly one known collection ID")
    collection = matches[0]
    if (not isinstance(seasons, dict) or seasons.get("schema") != "pantanal_seasons/1"
            or collection["season"] not in {r.get("name") for r in seasons.get("seasons", [])}):
        raise ValueError("Collection season is absent from declared season definitions")
    definitions = seasons["seasons"]
    if len({r["name"] for r in definitions}) != len(definitions):
        raise ValueError("Duplicate season definitions")
    for definition in definitions:
        try:
            datetime(2000, int(definition["start_month"]), int(definition["start_day"]))
            datetime(2000, int(definition["end_month"]), int(definition["end_day"]))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Invalid season boundary definition") from error
    group_ids = json.loads(collection["group_ids_json"])
    if not isinstance(group_ids, list) or not group_ids or len(set(group_ids)) != len(group_ids):
        raise ValueError("Collection group IDs must be a nonempty unique list")
    groups_by_id = {g["group_id"]: g for g in checkpoint["groups"].values()}
    if not set(group_ids) <= groups_by_id.keys():
        raise ValueError("Collection references an unknown group")
    valid_members = {(r["group_key"], r["window_key"], int(r["individual_id"])) for r in checkpoint["members"]}
    members = [r for r in read_table(root / "collection_members.csv") if r["collection_id"] == collection_id]
    selected, seen, events_by_animal = [], set(), defaultdict(set)
    for row in members:
        if row["group_id"] not in group_ids or row["group_key"] != groups_by_id[row["group_id"]]["group_key"]:
            raise ValueError("Collection member group ownership mismatch")
        triple = row["group_key"], row["window_key"], int(row["individual_id"])
        if triple not in valid_members or triple in seen:
            raise ValueError("Invalid or duplicate collection membership")
        seen.add(triple)
        if row["selection_status"] not in ("selected", "duplicate_window", "overlapping_window"):
            raise ValueError("Unknown collection evidence status")
        if row["selection_status"] != "selected":
            continue
        if row["canonical_group_id"] != row["group_id"]:
            raise ValueError("Selected evidence must belong to its canonical group")
        window = checkpoint["windows"][row["window_key"]]
        event_keys = {p["source_event_key"] for p in window["events"]}
        if events_by_animal[triple[2]] & event_keys:
            raise ValueError("Selected collection windows repeat source evidence")
        events_by_animal[triple[2]].update(event_keys)
        selected.append(row)
    if not selected:
        raise ValueError("Collection has no selected source evidence")
    # Interval overlap without an identical observed event is also excluded by
    # the collection contract; compare actual configured window bounds.
    by_animal = defaultdict(list)
    for row in selected:
        w = checkpoint["windows"][row["window_key"]]
        by_animal[w["individual_id"]].append((w["start"], w["end"]))
    for spans in by_animal.values():
        spans.sort()
        if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
            raise ValueError("Selected collection windows overlap in time")
    selector = defaultdict(lambda: defaultdict(set))
    for row in read_table(root / "selector_points.csv"):
        if row["group_id"] not in group_ids:
            continue
        key = row["group_id"], row["window_key"]
        if (groups_by_id[row["group_id"]]["group_key"], row["window_key"], int(row["individual_id"])) not in valid_members:
            raise ValueError("Selector point references invalid group membership")
        source = checkpoint["source"].get(row["source_event_key"])
        w = checkpoint["windows"].get(row["window_key"])
        if source is None or w is None or source["individual_id"] != int(row["individual_id"]) or w["individual_id"] != int(row["individual_id"]):
            raise ValueError("Invalid selector-point ownership")
        if row["source_event_key"] not in {e["source_event_key"] for e in w["events"]}:
            raise ValueError("Selector point does not belong to window")
        selector[key][row["selector_subtrajectory_id"]].add(row["source_event_key"])
    for row in selected:
        expected = set(json.loads(row["selector_subtrajectory_ids_json"]))
        if expected != set(selector[row["group_id"], row["window_key"]]):
            raise ValueError("Selector IDs do not match collection membership")
    return collection, members, selected, selector, seasons


def export_collection(checkpoint_path, collection_id, output_root=None, config=None,
                      split_path=None, feature_maps_path=None):
    """Export canonical evidence only; each run gets a timestamped directory."""
    config = config or ExportConfig()
    checkpoint = load_selection_checkpoint(checkpoint_path)
    collection, memberships, selected, selector, seasons = _collection_plan(checkpoint, collection_id)
    output_root = Path(output_root or ROOT / "data" / "tracking")
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".seasonal-export-", dir=output_root))
    try:
        data = temporary / "data"
        data.mkdir()
        upstream = temporary / ".working"
        by_group = defaultdict(list)
        for row in selected:
            by_group[row["group_id"]].append(row["window_key"])
        merged, schemas, grids, upstream_manifests = defaultdict(list), {}, {}, {}
        for group_id, window_keys in sorted(by_group.items()):
            result = export_checkpoint(checkpoint_path, upstream, group_keys=[group_id],
                window_keys=sorted(window_keys), config=config, split_path=split_path,
                feature_maps_path=feature_maps_path)
            upstream_manifests[group_id] = validate_export(result)
            grids.update(json.loads((result / "grids.json").read_text()))
            trajectories = list(read_table(result / "data" / "trajectory_manifest.csv"))
            for row in trajectories:
                if row["array_path"]:
                    folder = Path(row["variant"]) if row["collection"] == "independent" else Path("paired") / row["variant"]
                    name = (f"jaguar_{row['individual_id']}_{row['parent_window_id'][-12:]}_"
                            f"{row['segment_id'][-12:]}_{row['grid_key'][-10:]}_{row['trajectory_id'][-10:]}.npy")
                    new_path = folder / name
                    (temporary / folder).mkdir(parents=True, exist_ok=True)
                    if (temporary / new_path).exists():
                        raise ValueError("Canonical trajectory filename collision")
                    shutil.copyfile(result / row["array_path"], temporary / new_path)
                    row["array_path"] = new_path.as_posix()
                row.update(season=collection["season"], seasonal_collection_id=collection_id)
            replacements = {"trajectory_manifest.csv": trajectories, "fragment_diagnostics.csv": trajectories}
            for path in sorted((result / "data").glob("*.csv")):
                rows = replacements.get(path.name)
                if rows is None:
                    rows = list(read_table(path))
                with path.open(newline="") as handle:
                    schemas[path.name] = next(csv.reader(handle))
                merged[path.name].extend(rows)
        # Canonical windows are disjoint; some group-level metadata and source
        # catalog rows can still repeat. Deduplicate identical records only.
        for name, rows in merged.items():
            merged[name] = list({json_text(row): row for row in rows}.values())
        trajectories = merged["trajectory_manifest.csv"]
        events_by_trajectory = defaultdict(set)
        for row in merged["point_links.csv"]:
            events_by_trajectory[row["trajectory_id"]].add(row["source_event_key"])
        crosswalk = []
        for row in trajectories:
            matches = []
            for segment_id, source_keys in sorted(selector[row["group_id"], row["parent_window_id"]].items()):
                overlap = source_keys & events_by_trajectory[row["trajectory_id"]]
                if overlap:
                    matches.append(segment_id)
                    crosswalk.append({"collection_id": collection_id, "individual_id": row["individual_id"],
                        "group_id": row["group_id"], "window_key": row["parent_window_id"],
                        "selector_subtrajectory_id": segment_id, "trajectory_id": row["trajectory_id"],
                        "export_fragment_id": row["segment_id"], "variant": row["variant"],
                        "representation_collection": row["collection"],
                        "shared_source_event_count": len(overlap), "shared_source_event_keys_json": sorted(overlap)})
            row["selector_subtrajectory_ids_json"] = matches
        merged["fragment_diagnostics.csv"] = trajectories
        for name, rows in merged.items():
            _table(data / name, rows, schemas[name])
        _table(data / "selector_export_crosswalk.csv", crosswalk,
               ["collection_id", "individual_id", "selector_subtrajectory_id", "trajectory_id"])
        _table(data / "collection_members.csv", memberships, ["collection_id", "group_id", "window_key"])
        _table(data / "collections.csv", [collection], ["collection_id", "season"])
        context_groups = [g for g in checkpoint["groups"].values()
                          if g["group_id"] in json.loads(collection["group_ids_json"])]
        _table(data / "collection_groups.csv", context_groups, ["group_key", "group_id"])
        context_windows = []
        for key in sorted({r["window_key"] for r in memberships}):
            row = {k: v for k, v in checkpoint["windows"][key].items() if k != "events"}
            row["start"], row["end"] = row["start"].isoformat(), row["end"].isoformat()
            context_windows.append(row)
        _table(data / "collection_windows.csv", context_windows, ["window_key", "individual_id"])

        lists = defaultdict(list)
        for row in trajectories:
            if row["optimizer_candidate"] == "True" and row["array_path"]:
                lists[row["collection"], row["variant"], row["split"]].append(row["array_path"][:-4])
        for (kind, variant, split), names in lists.items():
            path = temporary / "lists" / kind / variant / f"{split}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(sorted(names)) + "\n")
        shutil.rmtree(upstream)
        (temporary / "grids.json").write_text(json_text(grids) + "\n")
        (temporary / "seasons.json").write_text(json_text(seasons) + "\n")
        provenance = temporary / "provenance"
        provenance.mkdir()
        (provenance / "upstream_export_manifests.json").write_text(json_text(upstream_manifests) + "\n")
        (provenance / "selection_checkpoint_manifest.json").write_text(json_text(checkpoint["manifest"]) + "\n")
        split_values = {r["individual_id"]: r["split"] for r in merged["animal_splits.csv"]}
        identity = {"schema": EXPORT_SCHEMA, "seasonal_export_schema": SEASONAL_EXPORT_SCHEMA,
            "checkpoint_sha256": file_hash(Path(checkpoint_path) / "checkpoint.json"),
            "selection_key": checkpoint["manifest"]["selection_key"], "collection_id": collection_id,
            "season": collection["season"], "collection": collection, "export_config": asdict(config),
            "upstream_export_keys": {g: m["export_key"] for g, m in upstream_manifests.items()},
            "software_sha256": {Path(__file__).name: file_hash(__file__)}, "animal_splits": split_values}
        export_key = "seasonal_export_" + digest(identity)[:24]
        now = datetime.now(timezone.utc)
        manifest = {**identity, "export_key": export_key, "created_utc": now.isoformat(),
            "array_columns": ["row", "col", "k"], "step_semantics": "spatial_move",
            "source_timezone": checkpoint["manifest"].get("source_timezone"),
            "selection_policy": checkpoint["manifest"]["selection_policy"],
            "scope": "data_export_only; no trainer repair or model fit",
            "overlap_policy": "canonical collection-selected nonoverlapping windows only; paired and independent lists are alternative fits",
            "split_status": "provided" if split_path else "unassigned",
            "counts": {"source_events": len(merged["source_points.csv"]), "windows": len(selected),
                "groups": len(by_group), "manifest_fragments": len(trajectories),
                "arrays": sum(bool(r["array_path"]) for r in trajectories),
                "pairs": len(merged["paired_cases.csv"]), "training_ready_fragments": 0},
            "files": file_inventory(temporary)}
        (temporary / "export_manifest.json").write_text(json_text(manifest) + "\n")
        validate_export(temporary)
        target = output_root / f"{_safe(collection['season']).lower()}-{_safe(collection_id)}-{now:%Y%m%dT%H%M%S%fZ}-{export_key[-12:]}"
        if target.exists():
            raise FileExistsError(target)
        temporary.rename(target)
        return target
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--output", default=str(ROOT / "data" / "tracking"))
    parser.add_argument("--variant", choices=("fine", "two_hour", "both"), default="both")
    parser.add_argument("--animal-splits")
    parser.add_argument("--feature-map-manifest")
    parser.add_argument("--source-gap-hours", type=float, default=4)
    parser.add_argument("--min-source-segment-points", type=int, default=5)
    parser.add_argument("--min-comparison-segment-points", type=int, default=5)
    parser.add_argument("--max-affected-fraction", type=float, default=.2)
    parser.add_argument("--min-final-retention", type=float, default=0,
                        help="Optional two-hour F/M minimum; 0 disables the ratio gate")
    args = parser.parse_args()
    config = ExportConfig(variant=args.variant, source_gap_hours=args.source_gap_hours,
        min_source_segment_points=args.min_source_segment_points,
        min_comparison_segment_points=args.min_comparison_segment_points,
        max_affected_fraction=args.max_affected_fraction,
        min_final_retention_fraction=args.min_final_retention)
    print(export_collection(args.checkpoint, args.collection, args.output, config,
                           args.animal_splits, args.feature_map_manifest))


if __name__ == "__main__":
    main()
