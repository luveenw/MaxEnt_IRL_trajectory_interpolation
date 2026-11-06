"""Synthetic regressions for ranking, advisory flags, and relaxed grouping."""

from datetime import datetime, timedelta
from statistics import fmean, pstdev, stdev
from types import SimpleNamespace

import pytest

from . import movement_processor_pantanal as processor_module
from .movement_processor_pantanal import MovementProcessor, ProcessorConfig, count_evenness


def window(ident, count=85, month=1):
    start = datetime(2010, month, 5)
    return {
        "individual_id": ident, "year": 2010, "month": month,
        "start": start, "end": start + timedelta(days=7),
        "observed_start": start, "observed_end": start + timedelta(days=7),
        "selected_fixes": count, "short_fragment_loss": 0,
        "affected_point_fraction": 0, "n_subtrajectories": 1,
        "mean_interval_error_hours": 0, "coverage_fraction": count / 85,
        "points":[{"individual_id":ident,"timestamp":start},
                  {"individual_id":ident,"timestamp":start+timedelta(days=7)}],
    }


def rank_synthetic(monkeypatch, windows, memberships, top_n=3, sexes=None):
    """Isolate ranking from tested temporal and geometry implementations."""
    def enumerate_clusters(mcps, config, available_ids, min_members):
        available = set(available_ids)
        return [{"members": tuple(members)} for members in memberships
                if len(members) >= min_members and set(members) <= available]

    monkeypatch.setattr(processor_module, "grow_cluster_candidates", enumerate_clusters)
    processor = MovementProcessor(ProcessorConfig(top_n=top_n))
    processor.individual_sexes = sexes or {}
    monkeypatch.setattr(processor, "candidate_extent",
                        lambda mcps, ids, chosen_windows: {"area_km2": 100})
    mcps = {
        item["individual_id"]: SimpleNamespace(
            full_start="2009-01-01T00:00:00", full_end="2011-01-01T00:00:00"
        )
        for item in windows
    }
    return processor.rank_groups(windows, mcps)


def test_group_sex_counts_count_individuals_not_fixes(monkeypatch):
    _, groups = rank_synthetic(monkeypatch,
        [window(1, 85), window(2, 70), window(3, 65)], [(1, 2, 3)],
        sexes={1: {"sex": "male"}, 2: {"sex": "female"}})
    assert (groups[0]["n_males"], groups[0]["n_females"], groups[0]["n_unknown_sex"]) == (1, 1, 1)
    assert groups[0]["n_individuals"] == 3


def test_balanced_count_score_penalizes_unequal_individual_contributions(monkeypatch):
    equal = count_evenness([60, 60])
    unequal = count_evenness([40, 80])
    assert equal["length_evenness"] == 1
    assert equal["point_count_cv"] == 0
    assert unequal["length_evenness"] == pytest.approx(0.9)
    assert unequal["min_max_point_ratio"] == 0.5

    _, groups = rank_synthetic(
        monkeypatch,
        [window(1, 60), window(2, 60), window(3, 40), window(4, 80)],
        [(1, 2), (3, 4)],
    )
    assert [group["ids"] for group in groups] == ["1;2", "3;4"]
    assert [group["total_fixes"] for group in groups] == [120, 120]
    assert [group["balanced_fixes_score"] for group in groups] == pytest.approx([120, 108])


def test_every_candidate_has_overall_rank_even_after_shortlist_is_full(monkeypatch):
    memberships = [(2 * i + 1, 2 * i + 2) for i in range(8)]
    windows = [window(ident, 85 - i) for i, pair in enumerate(memberships) for ident in pair]
    chosen, groups = rank_synthetic(monkeypatch, windows, memberships, top_n=3)

    assert len(chosen) == 3
    assert len(groups) == 8
    assert [group["overall_rank"] for group in groups] == list(range(1, 9))
    assert [group["rank"] for group in chosen] == [1, 2, 3]
    assert [group["overall_rank"] for group in chosen] == [1, 2, 3]


def test_top_groups_follow_score_order_without_diversity_reordering(monkeypatch):
    full = (1, 2, 3, 4, 5, 6)
    nested = (1, 2)
    independent = (7, 8)
    windows = [window(ident) for ident in range(1, 9)]
    windows += [window(ident, month=2) for ident in nested]
    chosen, groups = rank_synthetic(monkeypatch, windows, [full, nested, independent])

    assert any(group["month"] == 1 and group["ids"] == "1;2" for group in groups)
    assert [(group["month"], group["ids"]) for group in chosen] == [
        (1, "1;2;3;4;5;6"), (1, "1;2"), (1, "7;8"),
    ]
    assert [group["rank"] for group in chosen] == [1, 2, 3]
    assert [group["overall_rank"] for group in chosen] == [1, 2, 3]


def report_candidates(top_n=7, count=48):
    """Shortlist diversity skips some higher-scoring overall candidates."""
    groups = [{"overall_rank": rank, "ids": f"{rank};{rank + 100}"}
              for rank in range(1, count + 1)]
    selected = [dict(groups[overall_rank - 1], rank=rank,
                     group_id=f"G{rank:02d}")
                for rank, overall_rank in enumerate(range(1, 3 * top_n, 3), 1)]
    return selected, groups


@pytest.mark.parametrize("top_n, limit, expected_count", [
    (7, None, 48),
    (7, 35, 35),
    (3, 3, 3),
    (7, 60, 48),
])
def test_report_preserves_rank_order_for_every_candidate(top_n, limit, expected_count):
    selected, groups = report_candidates(top_n)
    original_selected = [dict(group) for group in selected]
    original_groups = [dict(group) for group in groups]
    processor = MovementProcessor(ProcessorConfig(top_n=top_n, report_limit=limit))

    reported, decorated = processor.groups_for_report(selected, groups)

    expected_order = list(range(1, 49))
    assert len(reported) == expected_count
    assert len(decorated) == len(groups) == 48
    assert [group["overall_rank"] for group in reported] == expected_order[:expected_count]
    assert [group["overall_rank"] for group in decorated] == list(range(1, 49))
    assert len({group["overall_rank"] for group in decorated}) == 48
    assert len({group["group_id"] for group in decorated}) == 48
    assert [group["group_id"] for group in reported[:top_n]] == [
        group["group_id"] for group in original_selected
    ]
    assert [group["rank"] for group in reported[:top_n]] == list(range(1, top_n + 1))
    assert all(group["is_shortlisted"] for group in reported[:top_n])
    assert all(not group["is_shortlisted"] for group in reported[top_n:])
    assert [group["rank"] for group in reported] == expected_order[:expected_count]
    assert [group["report_order"] for group in reported] == list(range(1, expected_count + 1))
    assert sum(group["is_reported"] for group in decorated) == expected_count
    assert sum(group["is_shortlisted"] for group in decorated) == top_n

    # The report and complete candidate export must identify the same rows,
    # with the same rank order and potentially different lengths.
    exported_by_rank = {group["overall_rank"]: group for group in decorated}
    assert all(group == exported_by_rank[group["overall_rank"]] for group in reported)
    assert all(group["is_reported"] for group in reported)
    assert selected == original_selected
    assert groups == original_groups


def test_group_ids_and_shortlist_ranks_do_not_change_when_report_is_truncated():
    selected, groups = report_candidates()
    identity_by_limit = []
    for limit in (None, 7, 35):
        processor = MovementProcessor(ProcessorConfig(top_n=7, report_limit=limit))
        reported, decorated = processor.groups_for_report(selected, groups)
        identity_by_limit.append({group["overall_rank"]: (
            group["group_id"], group["report_order"], group["is_shortlisted"], group["rank"]
        ) for group in decorated})
        expected = 48 if limit is None else limit
        assert {group["overall_rank"] for group in reported} == {
            group["overall_rank"] for group in decorated if group["is_reported"]
        }
        assert sum(group["is_reported"] for group in decorated) == expected
    assert identity_by_limit[0] == identity_by_limit[1] == identity_by_limit[2]


def test_report_limit_cannot_hide_part_of_the_shortlist():
    with pytest.raises(ValueError, match="report_limit"):
        MovementProcessor(ProcessorConfig(top_n=7, report_limit=3))


def test_no_candidates_produces_empty_report_and_candidate_export():
    assert MovementProcessor().groups_for_report([], []) == ([], [])


@pytest.mark.parametrize("counts", [[40, 80], [5, 20, 80], [68, 80, 82, 85, 85]])
def test_jain_evenness_matches_population_cv_not_sample_cv(counts):
    measured = count_evenness(counts)
    population_cv = pstdev(counts) / fmean(counts)
    sample_cv = stdev(counts) / fmean(counts)

    assert measured["point_count_cv"] == pytest.approx(population_cv)
    assert measured["length_evenness"] == pytest.approx(1 / (1 + population_cv ** 2))
    assert measured["point_count_cv"] != pytest.approx(sample_cv)
    assert measured["length_evenness"] != pytest.approx(1 / (1 + sample_cv ** 2))


def test_window_warning_is_visible_without_reordering_by_flag(monkeypatch):
    flagged = dict(window(1), violation_codes=["insufficient_retained_span"],
                   violation_text="Observed span: 6.4 days; requires at least 6.5 days.")
    chosen, groups = rank_synthetic(monkeypatch,
        [flagged, window(2), window(3, 70), window(4, 70)], [(1, 2), (3, 4)])
    assert groups[0]["ids"] == "1;2"
    assert groups[0]["has_violations"]
    assert groups[0]["flagged_individual_ids"] == "1"
    assert "ID 1: Observed span: 6.4 days" in groups[0]["violation_text"]
    assert not groups[1]["has_violations"]
    assert chosen == groups


def test_secondary_fallback_is_a_flagged_pair_and_prefers_nearby_mcp(monkeypatch):
    processor = MovementProcessor()
    monkeypatch.setattr(processor_module, "grow_cluster_candidates", lambda *args, **kwargs: [])
    def extent(mcps, ids, chosen, allow_over_budget=False):
        assert allow_over_budget
        # The farther animal would produce the smaller map, but the pair
        # within the normal five-kilometre gap must be preferred.
        return {"width_km":45, "height_km":25 if 2 in ids else 20,
                "area_km2":1125 if 2 in ids else 900}
    monkeypatch.setattr(processor, "candidate_extent", extent)
    monkeypatch.setattr(processor_module, "polygon_distance_m",
                        lambda a, b:4000 if {a, b} == {1, 2} else 9000)
    mcps = {i:SimpleNamespace(polygon_xy=i, full_start="2009-01-01T00:00:00",
                            full_end="2011-01-01T00:00:00") for i in (1, 2, 3)}
    _, groups = processor.rank_groups([window(i) for i in mcps], mcps, secondary_for_ids={1})
    assert len(groups) == 1
    group = groups[0]
    assert group["group_id"] == "R01"
    assert group["ids"] == "1;2"
    assert group["new_individual_ids"] == "1"
    assert group["generation_method"] == "minimum_extent_pair"
    assert group["pair_mcp_gap_km"] == 4
    assert group["spatial_violation_codes"] == ["map_side_limit"]
    assert "45.0 × 25.0 km" in group["spatial_violation_text"]
    assert "40 km limit" in group["spatial_violation_text"]


def test_secondary_groups_must_include_an_individual_absent_from_main(monkeypatch):
    processor = MovementProcessor()
    monkeypatch.setattr(processor_module, "grow_cluster_candidates",
                        lambda *args, **kwargs:[{"members":(1, 2)}])
    # No candidate has the absent animal, so no extent computation should run.
    assert processor.rank_groups([window(1), window(2)], {}, secondary_for_ids={3}) == ([], [])


def test_group_year_labels_use_retained_dates_not_just_window_start_year(monkeypatch):
    windows = [window(1,month=12), window(2,month=12)]
    start = datetime(2010,12,29)
    windows[0].update(start=start,end=start+timedelta(days=7),observed_start=start,
                      observed_end=start+timedelta(days=7),
                      points=[{"individual_id":1,"timestamp":start},
                              {"individual_id":1,"timestamp":start+timedelta(days=7)}])
    _, groups = rank_synthetic(monkeypatch,windows,[(1,2)])
    assert len(groups)==1
    group=groups[0]
    assert group["grouping_month"]==12
    assert group["grouping_years"]==[2010]
    assert group["same_start_year"] is True
    assert group["same_year"] is False
    assert group["years"]=="2010;2011"
    assert group["shared_years"]==[2010]
    assert group["observed_year_months"]==["2010-12","2011-01"]


def test_same_month_pair_can_group_individuals_from_different_calendar_years(monkeypatch):
    windows = []
    for ident, year in [(1,2009),(2,2013)]:
        start = datetime(year,12,29)
        end = start + timedelta(days=7)
        record = window(ident,month=12)
        record.update(year=year,start=start,end=end,observed_start=start,observed_end=end,
                      points=[{"individual_id":ident,"timestamp":start},
                              {"individual_id":ident,"timestamp":end}])
        windows.append(record)
    _, groups = rank_synthetic(monkeypatch,windows,[(1,2)])
    assert len(groups)==1
    group=groups[0]
    assert group["ids"]=="1;2"
    assert group["grouping_month"]==12
    assert group["grouping_years"]==[2009,2013]
    assert group["observed_year_months"]==["2009-12","2010-01","2013-12","2014-01"]
    assert group["same_year"] is False
    assert group["same_start_year"] is False
    assert group["shared_years"]==[]
    january, december = group["month_coverage"]
    assert january["years"]==[2010,2014]
    assert december["years"]==[2009,2013]
    assert january["n_individuals"]==december["n_individuals"]==2
