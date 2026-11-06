from datetime import datetime, timedelta

import pytest

from jaguar_irl.data.pantanal_seasonal_collections import build_collections


def group(name, ids, rank=1, season="winter", relaxed=False, starts=None):
    windows=[]
    for ident in ids:
        start=datetime(2020,6,1)+timedelta(days=(starts or {}).get(ident,0))
        key=f"animal{ident}_{start:%Y%m%d}"
        windows.append({"individual_id":ident,"window_id":key,"start":start,"end":start+timedelta(days=7),
                        "segments":[{"trajectory_id":key+"_s001"}],"points":[]})
    return {"group_id":name,"rank":rank,"season_names":[season],
            "candidate_list":"relaxed" if relaxed else "main","windows":windows}


def test_full_union_cover_removes_proper_subset_and_records_missing_cohort():
    groups=[group("G1",[1,2],1),group("G2",[1,2,3],2),group("G3",[4],3)]
    collections, members=build_collections(groups,cohort_ids=range(1,6))
    assert len(collections)==1
    c=collections[0]
    assert c["group_ids"]==["G2","G3"]
    assert c["individual_ids"]==[1,2,3,4]
    assert c["unrepresented_cohort_ids"]==[5]
    assert c["extra_memberships"]==0
    assert all(m["selection_status"]=="selected" for m in members)


def test_relaxed_groups_only_introduce_main_absent_animals_and_keep_full_cover():
    groups=[group("G1",[1,2]),group("R1",[1],1,relaxed=True),group("R2",[2,3],2,relaxed=True)]
    collections,members=build_collections(groups)
    c=collections[0]
    assert c["group_ids"]==["G1","R2"]
    assert c["candidate_union_ids"]==[1,2,3]
    assert c["duplicate_individual_ids"]==[2] and c["extra_memberships"]==1
    duplicates=[r for r in members if r["selection_status"]=="duplicate_window"]
    assert len(duplicates)==1 and duplicates[0]["canonical_group_id"]=="G1"


def test_overlap_is_suppressed_and_disjoint_windows_survive_with_manifest_ids():
    groups=[group("G1",[1,2],1),group("G2",[1,3],2,starts={1:5}),group("G3",[1,4],3,starts={1:20})]
    collections,members=build_collections(groups)
    rows=[r for r in members if r["individual_id"]==1 and r["collection_id"]==collections[0]["collection_id"]]
    assert [r["selection_status"] for r in rows]==["selected","overlapping_window","selected"]
    assert rows[1]["canonical_window_id"]==rows[0]["window_id"]
    assert all(r["selector_subtrajectory_ids"] for r in rows)
    assert collections[0]["n_selected_windows"]==5


def test_touching_inclusive_windows_overlap():
    _,rows=build_collections([group("G1",[1,2]),group("G2",[1,3],2,starts={1:7})])
    assert next(r for r in rows if r["group_id"]=="G2" and r["individual_id"]==1)["selection_status"]=="overlapping_window"


def test_seasons_and_alternatives_are_deterministic_under_input_reordering():
    groups=[group("G1",[1,2],1),group("G2",[2,3],2),group("G3",[1,3],3)]
    groups[0]["season_names"].append("spring")
    first=build_collections(groups,max_collections=3,cohort_ids=[1,2,3])
    second=build_collections(reversed(groups),max_collections=3,cohort_ids=[1,2,3])
    assert first==second
    winter=[c for c in first[0] if c["season"]=="winter"]
    assert len(winter)>=2
    assert all(c["n_individuals"]==3 for c in winter)
    assert len({c["collection_key"] for c in first[0]})==len(first[0])
    assert next(c for c in first[0] if c["season"]=="spring")["individual_ids"]==[1,2]


def test_validation_and_no_groups():
    assert build_collections([])==([],[])
    with pytest.raises(ValueError,match="globally unique"):
        build_collections([group("G1",[1]),group("G1",[2])])
    with pytest.raises(ValueError,match="max_collections"):
        build_collections([],max_collections=0)
    with pytest.raises(ValueError,match="Unknown"):
        build_collections([group("G1",[1],season="monsoon")])


def test_collection_key_uses_evidence_and_map_context_not_display_rank():
    a=group("G1",[1,2],1)
    b=group("G2",[3,4],2)
    before,_=build_collections([a,b])
    a["group_id"],b["group_id"]="G99","G98"
    a["rank"],b["rank"]=10,9
    after,_=build_collections([a,b])
    assert before[0]["collection_key"]==after[0]["collection_key"]
    b["bounds"]=[0,0,1000,1000]
    changed,_=build_collections([a,b])
    assert changed[0]["collection_key"]!=after[0]["collection_key"]
