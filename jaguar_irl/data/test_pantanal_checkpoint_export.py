"""Scientific contracts and standalone/no-overwrite guarantees for the export."""
import csv
import itertools
import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from pyproj import Transformer

from .pantanal_checkpoint import (file_hash, load_selection_checkpoint, read_table,
                                 write_selection_checkpoint, _metadata)
from .movement_processor_pantanal import ProcessorConfig
from .pantanal_irl_temporal import (ExportConfig, affected_count, build_tracks,
                                    comparison_partition, thin_bout)
from .export_pantanal_irl import (cell_for_point, export_checkpoint, grid_route,
                                  raster_line, span_union_hours, validate_array)


def events(times, cells=None):
    inverse = Transformer.from_crs(32721, 4326, always_xy=True)
    result = []
    for i, hour in enumerate(times):
        row,col = cells[i] if cells else (2, i)
        lon,lat = inverse.transform(500250+500*col, 7999750-500*row)
        result.append(dict(individual_id=1, event_id=str(i), source_event_key=f"event{i}",
            timestamp=datetime(2020,1,1)+timedelta(hours=hour), longitude=lon,latitude=lat, tag_id="tag"))
    return result


@pytest.fixture
def selection(tmp_path):
    raw=events(range(15),[(2,i//2) for i in range(15)])
    raw += [dict(p,individual_id=2,event_id=f"b{p['event_id']}") for p in events(range(15),[(4,i//2) for i in range(15)])]
    path=tmp_path/"raw.csv"
    fields=["Event_ID","timestamp","location.long","location.lat","individual.local.identifier (ID)",
            "study.name","country","tag.local.identifier","gps.hdop"]
    with path.open("w",newline="") as h:
        writer=csv.DictWriter(h,fieldnames=fields); writer.writeheader()
        for line,p in enumerate(raw,2):
            writer.writerow({"Event_ID":p["event_id"],"timestamp":p["timestamp"].strftime("%m/%d/%y %H:%M"),
                "location.long":p["longitude"],"location.lat":p["latitude"],
                "individual.local.identifier (ID)":p["individual_id"],"study.name":"Pantanal",
                "country":"Brazil","tag.local.identifier":"tag","gps.hdop":"1.2"})
            p.update(source_row=line,study="Pantanal",country="Brazil")
    windows=[]
    for ident in (1,2):
        points=[r for r in raw if r["individual_id"]==ident]
        windows.append(dict(window_id=f"old{ident}",individual_id=ident,start=points[0]["timestamp"],
                            end=points[-1]["timestamp"],points=points[::2],segments=[]))
    groups=[dict(group_id=f"G{i:02}",rank=i,candidate_list="main",windows=windows,
        epsg=32721,bounds=[500000,7994000,506000+(i-1)*500,8000000],grid_rows=12,grid_cols=12+i-1,
        is_reported=i==1,is_shortlisted=i==1,spatial_violation_codes=[]) for i in (1,2)]
    config=ProcessorConfig(csv_path=str(path),output_dir=str(tmp_path/"selection"),individual_ids=(1,2))
    temporal=dict(candidates=windows,relaxed_candidates=[],individuals=[{"individual_id":i} for i in (1,2)])
    mcps={i:SimpleNamespace(properties=lambda:{"percent":95},polygon_xy=np.asarray([[0,0],[1,0],[0,1]])) for i in (1,2)}
    return dict(config=config,records=raw,temporal=temporal,groups=groups,mcps=mcps,parse_audit={})


def test_checkpoint_unthinned_deduplicated_all_groups_and_report_independent(selection):
    a=write_selection_checkpoint(**selection)
    checkpoint=load_selection_checkpoint(a)
    assert len(checkpoint["source"])==30
    assert len(checkpoint["groups"])==2  # one was not reported
    assert len(checkpoint["members"])==4
    assert len(checkpoint["windows"])==2
    assert all(len(w["events"])==15 for w in checkpoint["windows"].values())
    original=json.loads(next(iter(checkpoint["source"].values()))["original_record_json"])
    assert original["gps.hdop"]=="1.2"
    selection["config"]=replace(selection["config"],report_limit=7,top_n=3)
    for g in selection["groups"]:g["is_reported"]=not g["is_reported"]
    assert write_selection_checkpoint(**selection)==a


def test_checkpoint_detects_tampering_and_never_overwrites(selection):
    path=write_selection_checkpoint(**selection)
    with (path/"source_points.csv").open("a") as h:h.write("tampering\n")
    with pytest.raises(ValueError,match="hash mismatch"):
        load_selection_checkpoint(path)
    with pytest.raises(ValueError,match="hash mismatch"):
        write_selection_checkpoint(**selection)


def test_export_standalone_and_requires_explicit_groups_no_automatic_splits(selection,tmp_path):
    checkpoint=write_selection_checkpoint(**selection)
    Path(selection["config"].csv_path).unlink()
    with pytest.raises(ValueError,match="explicit groups"):
        export_checkpoint(checkpoint,tmp_path/"export")
    output=export_checkpoint(checkpoint,tmp_path/"export",group_keys=["G01"])
    assert not list(output.rglob("cell_runs.csv"))
    manifest=json.loads((output/"export_manifest.json").read_text())
    assert manifest["selection_policy"] == json.loads((checkpoint/"checkpoint.json").read_text())["selection_policy"]
    assert manifest["split_status"]=="unassigned"
    assert manifest["counts"]["training_ready_fragments"]==0
    trajectories=list(read_table(output/"data"/"trajectory_manifest.csv"))
    assert {r["variant"] for r in trajectories}=={"fine","two_hour"}
    assert {r["split"] for r in trajectories}=={"unassigned"}
    assert {r["collection"] for r in trajectories}=={"independent","paired"}
    assert export_checkpoint(checkpoint,tmp_path/"export",group_keys=["G01"])==output
    grid=next(iter(json.loads((output/"grids.json").read_text()).values()))
    for r in trajectories:
        if r["array_path"]:validate_array(np.load(output/r["array_path"]),grid)
    for pair in read_table(output/"data"/"paired_cases.csv"):
        entries=[r for r in trajectories if r["pair_id"]==pair["pair_id"]]
        assert len(entries)==2
        assert len({(r["first_event_key"],r["last_event_key"]) for r in entries})==1


def test_split_owner_consistent_across_group_aliases(selection,tmp_path):
    checkpoint=write_selection_checkpoint(**selection)
    split=tmp_path/"splits.json"; split.write_text(json.dumps({"1":"train","2":"test"}))
    output=export_checkpoint(checkpoint,tmp_path/"export",all_groups=True,split_path=split)
    for r in read_table(output/"data"/"trajectory_manifest.csv"):
        assert r["split"]=={"1":"train","2":"test"}[r["individual_id"]]
    assert list(read_table(output/"data"/"evidence_aliases.csv"))
    split.write_text(json.dumps({"1":"train"}))
    with pytest.raises(ValueError,match="every selected animal"):
        export_checkpoint(checkpoint,tmp_path/"export",all_groups=True,split_path=split)


def test_sex_metadata_is_independent_of_schedule_and_does_not_guess(tmp_path):
    from .pantanal_checkpoint import load_individual_sexes
    path = tmp_path / "metadata.csv"
    path.write_text("ID,Sex,Planned Schedule (h)\n1,Male,2\n2, female ,\n3,F,2\n3,M,2\n4,unknown,2\n,,\n")
    values = load_individual_sexes(path, [1, 2, 3, 4, 5])
    assert values[1]["sex"] == "male"
    assert values[2] == {"sex": "female", "sex_metadata_status": "available"}
    assert values[3] == {"sex": "unknown", "sex_metadata_status": "conflicting_rows"}
    assert values[4]["sex"] == values[5]["sex"] == "unknown"


def test_collar_blank_rows_conflicts_and_missing_values(tmp_path):
    path=tmp_path/"metadata.csv"
    path.write_text("ID,Planned Schedule (h)\n1,2\n2,3\n2,4\n3,\n,\n,\n")
    meta=_metadata(path,[1,2,3,4])
    assert meta[1]["planned_interval_hours"]==2
    assert meta[2]["metadata_status"]=="conflicting_rows"
    assert meta[3]["metadata_status"]=="unavailable_schedule"
    assert meta[4]["metadata_status"]=="missing"


def test_feature_maps_require_explicit_temporal_applicability(selection,tmp_path):
    checkpoint=write_selection_checkpoint(**selection)
    loaded=load_selection_checkpoint(checkpoint)
    group=next(g for g in loaded["groups"].values() if g["group_id"]=="G01")
    grid=loaded["grids"][group["grid_key"]]
    raster=tmp_path/"features.npy"
    np.save(raster,np.zeros((2,grid["rows"],grid["cols"])))
    path=tmp_path/"maps.json"
    entry={"feature_map_key":"map2020","path":str(raster)}
    path.write_text(json.dumps({group["grid_key"]:entry}))
    with pytest.raises(ValueError,match="temporal_scope"):
        export_checkpoint(checkpoint,tmp_path/"exports",group_keys=["G01"],feature_maps_path=path)
    entry.update(temporal_scope="bounded_period",valid_from="2021-01-01",valid_to="2022-01-01")
    path.write_text(json.dumps({group["grid_key"]:entry}))
    output=export_checkpoint(checkpoint,tmp_path/"exports",group_keys=["G01"],feature_maps_path=path)
    assert all(r["feature_map_status"]=="no_matching_period" for r in read_table(output/"data"/"trajectory_manifest.csv"))
    entry.update(valid_from="2020-01-01",valid_to="2021-01-01")
    path.write_text(json.dumps({group["grid_key"]:[entry,entry]}))
    with pytest.raises(ValueError,match="Ambiguous"):
        export_checkpoint(checkpoint,tmp_path/"exports",group_keys=["G01"],feature_maps_path=path)


def test_exact_sampler_tie_and_fine_fixes_preserved():
    source=events([0,.5,1.5,2.5,4,7,7.5,9.1,10.9])
    sampled=thin_bout(source,ExportConfig())
    assert [p["event_id"] for p in sampled]==["0","2","4","5","7","8"]
    tracks=build_tracks(source,ExportConfig())
    assert sum(len(p["events"]) for p in tracks["fine"])==len(source)


def test_final_retention_80_without_five_percent_loss_cap():
    # Nine regular retained points and an isolated tenth: 10% fragment loss.
    tracks=build_tracks(events([*range(0,18,2),30]),ExportConfig(min_final_retention_fraction=.8))
    assert (tracks["M"],tracks["F"],tracks["A"])==(10,9,0)
    assert tracks["comparison_eligible"]
    assert tracks["final_retention_fraction"]==.9
    # Four isolated points instead: 9/13 < 80%, fine evidence remains cataloged.
    failed=build_tracks(events([*range(0,18,2),30,40,50,60]),ExportConfig(min_final_retention_fraction=.8))
    assert not failed["comparison_eligible"]
    assert sum(len(p["events"]) for p in failed["fine"])==13


def test_four_hour_boundary_and_five_observation_floor():
    at=build_tracks(events([0,1,2,3,7]),ExportConfig())
    assert len(at["fine"])==1 and at["fine"][0]["retained"]
    over=build_tracks(events([0,1,2,3,7.0001]),ExportConfig())
    assert [len(p["events"]) for p in over["fine"]]==[4,1]
    assert not any(p["retained"] for p in over["fine"])
    for n in (4,5):
        tracks=build_tracks(events(range(0,2*n,2)),ExportConfig())
        assert tracks["fine"][0]["retained"]==(n==5)
        assert tracks["comparison_eligible"]==(n==5)


def test_global_endpoint_budget_and_deployment_boundaries():
    raw=events([0,3,6,8,10,12,14,16,18,20,22,24,26,28,30])
    track=build_tracks(raw,ExportConfig())
    assert track["A"]<=math_floor(.2*track["M"])
    # A regular cadence must still stop at a known change in tag.
    raw=events(range(0,20,2))
    for p in raw[5:]:p["tag_id"]="new-tag"
    track=build_tracks(raw,ExportConfig())
    assert [len(p["events"]) for p in track["fine"]]==[5,5]
    assert [len(p["events"]) for p in track["two_hour"]]==[5,5]


def math_floor(value):
    import math
    return math.floor(value+1e-12)


def exhaustive_partition(kinds,minimum,budget):
    n=len(kinds)+1
    optional=[i+1 for i,k in enumerate(kinds) if k==1]
    hard=[i+1 for i,k in enumerate(kinds) if k==2]
    choices=[]
    for mask in itertools.product((False,True),repeat=len(optional)):
        cuts=tuple(sorted(hard+[k for k,keep in zip(optional,mask) if keep]))
        bounds=(0,*cuts,n)
        parts=tuple((a,b,b-a>=minimum) for a,b in zip(bounds,bounds[1:]))
        a=sum(affected_count(kinds[left:right-1]) for left,right,keep in parts if keep)
        if a<=budget:
            f=sum(right-left for left,right,keep in parts if keep)
            choices.append(((-f,sum(keep for _,_,keep in parts),len(parts),cuts),parts))
    return min(choices)[1]


def test_partition_matches_exhaustive_objective_and_chronological_ties():
    for kinds in itertools.product(range(3),repeat=5):
        for budget in (0,1,2,4):
            assert comparison_partition(kinds,3,budget)==exhaustive_partition(kinds,3,budget)


@pytest.mark.parametrize("cells,expected",[
    ([(0,0)]*5,[(0,0,0)]),
    ([(0,0)]*6+[(0,1)],[(0,0,0),(0,1,1)]),
    ([(0,0),(0,0),(0,1),(0,1),(0,0)],[(0,0,0),(0,1,1),(0,0,2)]),
])
def test_grid_compression_preserves_returns_and_spatial_counter(cells,expected):
    array,links,edges=grid_route(events(range(len(cells))),cells)
    assert array.tolist()==[list(x) for x in expected]
    assert len(links)==len(cells)
    assert len(edges)==len(expected)-1


def test_nonadjacent_connection_counts_edges_not_inserted_cells():
    array,_,edges=grid_route(events([0,1]),[(0,0),(0,3)])
    assert array.tolist()==[[0,0,0],[0,1,1],[0,2,2],[0,3,3]]
    assert len(edges)==3
    assert all(e["construction_type"]=="inferred_connection" for e in edges)
    for a,b in itertools.product([(0,0),(3,5),(5,3),(2,8),(8,2)],repeat=2):
        route=raster_line(a,b)
        assert route[0]==a and route[-1]==b
        assert all(max(abs(y2-y1),abs(x2-x1))==1 for (y1,x1),(y2,x2) in zip(route,route[1:]))


def test_outer_boundary_handling_does_not_clip_outliers():
    grid=dict(bounds=[0,0,1000,1000],rows=2,cols=2,cell_size_m=500)
    identity=SimpleNamespace(transform=lambda x,y:(x,y))
    assert cell_for_point(dict(longitude=1000,latitude=0),grid,identity)==(1,1)
    with pytest.raises(ValueError,match="outside_checkpoint_grid"):
        cell_for_point(dict(longitude=1000.00001,latitude=0),grid,identity)


def test_coverage_unions_overlaps_instead_of_summing():
    t=datetime(2020,1,1)
    assert span_union_hours([(t,t+timedelta(hours=4)),(t+timedelta(hours=2),t+timedelta(hours=6))])==6


def test_same_cell_fragments_and_unique_routes_cataloged_not_optimized(selection,tmp_path):
    # Replace source coordinates in both the source CSV and parser records.
    for p in selection["records"]:
        p["longitude"],p["latitude"]=selection["records"][0]["longitude"],selection["records"][0]["latitude"]
    checkpoint=write_selection_checkpoint(**selection)
    out=export_checkpoint(checkpoint,tmp_path/"export",group_keys=["G01"])
    rows=list(read_table(out/"data"/"trajectory_manifest.csv"))
    assert all(r["grid_transition_count"]=="0" for r in rows)
    assert all(r["backend_support_status"]=="unsupported_residence_evidence" for r in rows)
    assert all(not r["array_path"] and r["optimizer_candidate"]=="False" for r in rows)


def test_retention_gate_disabled_by_default_but_fragment_and_gap_rules_remain():
    # Same source passes by default and fails the optional former 80% gate.
    source=events([*range(0,18,2),30,40,50,60])
    default=build_tracks(source,ExportConfig())
    strict=build_tracks(source,ExportConfig(min_final_retention_fraction=.8))
    assert ExportConfig().min_final_retention_fraction == 0
    assert default["comparison_eligible"] and not strict["comparison_eligible"]
    assert (default["M"],default["F"],default["A"]) == (13,9,0)
    assert default["final_retention_fraction"] == strict["final_retention_fraction"] == 9/13
    assert [[p["event_id"] for p in part["events"]] for part in default["two_hour"]] == [
        [p["event_id"] for p in part["events"]] for part in strict["two_hour"]]
    assert all(len(part["events"]) >= 5 for part in default["two_hour"] if part["retained"])
    assert not build_tracks([],ExportConfig())["comparison_eligible"]
    assert not build_tracks(events([0,10,20,30]),ExportConfig())["comparison_eligible"]
    for value in (-.1,1.1):
        with pytest.raises(ValueError,match="Fractions"):
            ExportConfig(min_final_retention_fraction=value)
