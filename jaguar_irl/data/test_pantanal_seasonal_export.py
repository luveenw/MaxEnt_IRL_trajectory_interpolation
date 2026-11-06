"""Collection export contracts: canonical evidence, portability and provenance."""
import json
from pathlib import Path

import numpy as np
import pytest

from .test_pantanal_checkpoint_export import selection
from .pantanal_checkpoint import (file_inventory, load_selection_checkpoint, read_table,
                                 write_selection_checkpoint, write_table)
from .export_pantanal_irl import validate_export
from .export_pantanal_seasonal_irl import export_collection
from .pantanal_irl_temporal import ExportConfig


def seasonal_checkpoint(selection):
    path = write_selection_checkpoint(**selection)
    checkpoint = load_selection_checkpoint(path)
    groups = {r["group_id"]: r for r in checkpoint["groups"].values()}
    members, selector = [], []
    for group_id, group in groups.items():
        for key, window in checkpoint["windows"].items():
            ident = window["individual_id"]
            # Canonical group differs by animal, exercising filtered group calls.
            owner = "G01" if ident == 1 else "G02"
            segment = f"{window['window_id']}_s001"
            members.append(dict(collection_id="SUM-C01", group_id=group_id,
                group_key=group["group_key"], window_key=key, individual_id=ident,
                selection_status="selected" if group_id == owner else "duplicate_window",
                canonical_group_id=owner, selector_subtrajectory_ids_json=[segment]))
            for event in window["events"][::2]:
                selector.append(dict(group_id=group_id, window_key=key, individual_id=ident,
                    selector_subtrajectory_id=segment, source_event_key=event["source_event_key"]))
    write_table(path / "collections.csv", [dict(collection_id="SUM-C01", season="summer", rank=1,
        group_ids_json=["G01", "G02"])], ["collection_id", "season", "rank", "group_ids_json"])
    write_table(path / "collection_members.csv", members, list(members[0]))
    write_table(path / "selector_points.csv", selector, list(selector[0]))
    (path / "seasons.json").write_text(json.dumps(dict(schema="pantanal_seasons/1",
        source_url="https://www.climatestotravel.com/climate/brazil/pantanal",
        seasons=[dict(name="summer", start_month=11,start_day=15,end_month=3,end_day=22)],
        buffer_days=7,sampling_duration_days=7)))
    rehash(path)
    return path


def rehash(path):
    manifest = json.loads((path / "checkpoint.json").read_text())
    manifest["seasonal_schema"] = "pantanal_seasonal_checkpoint/1"
    manifest["files"] = {k:v for k,v in file_inventory(path).items() if k != "checkpoint.json"}
    (path / "checkpoint.json").write_text(json.dumps(manifest))


def test_collection_export_filters_memberships_and_is_portable(selection, tmp_path):
    cp = seasonal_checkpoint(selection)
    Path(selection["config"].csv_path).unlink()
    output = export_collection(cp, "SUM-C01", tmp_path / "tracking")
    manifest = validate_export(output)
    rows = list(read_table(output / "data" / "trajectory_manifest.csv"))
    assert {r["individual_id"] for r in rows} == {"1", "2"}
    assert all(r["group_id"] == ("G01" if r["individual_id"] == "1" else "G02") for r in rows)
    assert all(r["split"] == "unassigned" and r["training_ready"] == "False" for r in rows)
    assert manifest["counts"]["source_events"] == 30
    assert manifest["counts"]["windows"] == 2
    assert output.name.startswith("summer-SUM-C01-")
    assert not (output / ".working").exists()
    assert {r["variant"] for r in rows} == {"fine", "two_hour"}
    assert all(json.loads(r["selector_subtrajectory_ids_json"]) for r in rows)
    for row in rows:
        if row["array_path"]:
            assert Path(row["array_path"]).name.startswith(f"jaguar_{row['individual_id']}_")
            array = np.load(output / row["array_path"])
            assert np.array_equal(array[:,2], np.arange(len(array)))
    crosswalk = list(read_table(output / "data" / "selector_export_crosswalk.csv"))
    assert {r["trajectory_id"] for r in crosswalk} == {r["trajectory_id"] for r in rows}
    # Every list points to a canonical local file; paired/independent stay separate.
    for path in (output / "lists").rglob("*.txt"):
        assert all((output / (line + ".npy")).exists() for line in path.read_text().splitlines())
    second = export_collection(cp, "SUM-C01", tmp_path / "tracking")
    assert output != second  # separate timestamped invocations, same semantic export
    assert validate_export(second)["export_key"] == manifest["export_key"]


def test_collection_rejects_unknown_and_shared_source_ownership(selection, tmp_path):
    cp = seasonal_checkpoint(selection)
    with pytest.raises(ValueError, match="known collection"):
        export_collection(cp, "missing", tmp_path / "out")
    rows = list(read_table(cp / "collection_members.csv"))
    rows[0]["selection_status"] = "selected"
    rows[0]["canonical_group_id"] = rows[0]["group_id"]
    duplicate = next(r for r in rows if r["individual_id"] == rows[0]["individual_id"] and r["group_id"] != rows[0]["group_id"])
    duplicate["selection_status"] = "selected"
    duplicate["canonical_group_id"] = duplicate["group_id"]
    write_table(cp / "collection_members.csv", rows, list(rows[0]))
    rehash(cp)
    with pytest.raises(ValueError, match="repeat source evidence"):
        export_collection(cp, "SUM-C01", tmp_path / "out")


def test_collection_requires_verified_seasons_and_source_crosswalk(selection, tmp_path):
    cp = seasonal_checkpoint(selection)
    (cp / "seasons.json").write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        export_collection(cp, "SUM-C01", tmp_path / "out")
    rehash(cp)
    with pytest.raises(ValueError, match="season definitions"):
        export_collection(cp, "SUM-C01", tmp_path / "out")


def test_collection_variant_and_original_animal_splits(selection, tmp_path):
    cp = seasonal_checkpoint(selection)
    splits = tmp_path / "splits.json"
    splits.write_text(json.dumps({"1":"train","2":"test"}))
    output = export_collection(cp,"SUM-C01",tmp_path / "tracking",
        config=ExportConfig(variant="fine"),split_path=splits)
    rows=list(read_table(output / "data" / "trajectory_manifest.csv"))
    assert {r["variant"] for r in rows} == {"fine"}
    assert all(r["split"]=={"1":"train","2":"test"}[r["individual_id"]] for r in rows)
    assert validate_export(output)["counts"]["pairs"] == 0
