"""Behavioral checks for observed-only temporal selection and fragmentation."""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from jaguar_irl.data.pantanal_temporal import (
    TemporalConfig,
    _candidate,
    find_week_candidates,
    interval_metrics,
    segment_points,
)


def track(gaps, start=datetime(2015, 1, 1), individual=13):
    """Synthetic observed positions with distinguishable source events."""
    times = [start]
    for gap in gaps:
        times.append(times[-1] + timedelta(hours=gap))
    return [
        {
            "individual_id": individual,
            "timestamp": when,
            "longitude": -57.0 + index * 0.00001,
            "latitude": -17.0,
            "event_id": f"{start:%Y%m%d}-{index}",
            "study": "Jaguar_Taiama",
            "country": "Brazil",
        }
        for index, when in enumerate(times)
    ]


def short_study_config(**changes):
    return replace(
        TemporalConfig(), min_days_per_month=1, **changes
    )


def test_hourly_observations_are_thinned_to_real_two_hour_fixes():
    source = track([1] * 168)
    out = find_week_candidates(source, short_study_config())
    assert len(out["candidates"]) == 1
    candidate = out["candidates"][0]
    assert candidate["selected_fixes"] == 85
    assert candidate["n_subtrajectories"] == 1
    assert candidate["duration_days"] == 7
    assert candidate["points"][-1]["elapsed_hours"] == 168
    assert all(point["dt_hours"] == 2 for point in candidate["points"][1:])
    by_event = {point["event_id"]: point for point in source}
    for point in candidate["points"]:
        original = by_event[point["event_id"]]
        for field in ("timestamp", "longitude", "latitude", "individual_id"):
            assert point[field] == original[field]


def test_small_clock_drift_does_not_accumulate_into_fixed_grid_rejections():
    source = track([2 + 1 / 60] * 84)
    candidate = find_week_candidates(source, short_study_config())["candidates"][0]
    assert candidate["selected_fixes"] == 84
    assert candidate["regular_fraction"] == 1
    assert candidate["mean_interval_error_hours"] == pytest.approx(1 / 60)
    assert candidate["points"][-1]["timestamp"] == source[83]["timestamp"]


def test_point_fraction_counts_both_endpoints_and_shared_point_only_once():
    cfg = TemporalConfig()
    isolated = interval_metrics(track([2] * 4 + [4] + [2] * 4), cfg)
    adjacent = interval_metrics(track([2] * 3 + [4, 4] + [2] * 4), cfg)
    assert isolated["affected_indices"] == {4, 5}
    assert isolated["affected_point_fraction"] == 0.2
    assert adjacent["affected_indices"] == {3, 4, 5}
    assert adjacent["affected_point_fraction"] == 0.3
    assert isolated["irregular_intervals"] == 1
    assert adjacent["irregular_intervals"] == 2


def test_hard_gap_is_preserved_as_a_boundary_and_not_a_shorter_step():
    source = track([2] * 4 + [5] + [2] * 4)
    result = segment_points(source, TemporalConfig())
    assert [len(part) for part in result["segments"]] == [5, 5]
    assert result["source_metrics"]["max_gap_hours"] == 5
    assert result["source_metrics"]["hard_gaps"] == 1
    assert all(interval_metrics(part, TemporalConfig())["max_gap_hours"] == 2
               for part in result["segments"])
    assert not result["dropped_points"]


def test_partition_retain_points_once_and_cut_only_real_irregular_edges():
    # Whole run has 4/15 affected points and fails20%. The optimum uses two
    # bursts of5 and10points; splitting at both irregular edges needs three.
    source = track([2] * 4 + [4] + [2] * 4 + [4] + [2] * 4)
    cfg = TemporalConfig()
    result = segment_points(source, cfg)
    assert result["source_metrics"]["affected_point_fraction"] > 0.2
    assert len(result["segments"]) == 2
    assert sorted(map(len, result["segments"])) == [5, 10]
    flat = [point for part in result["segments"] for point in part]
    assert [point["event_id"] for point in flat] == [point["event_id"] for point in source]
    assert not result["dropped_points"]
    for part in result["segments"]:
        assert interval_metrics(part, cfg)["affected_point_fraction"] <= 0.2
    a, b = result["segments"]
    assert (b[0]["timestamp"] - a[-1]["timestamp"]).total_seconds() / 3600 == 4


@pytest.mark.parametrize("n,retained", [(4, 0), (5, 5)])
def test_five_point_floor(n, retained):
    result = segment_points(track([2] * (n - 1)), TemporalConfig())
    assert sum(map(len, result["segments"])) == retained
    assert len(result["dropped_points"]) == n - retained


def test_short_fragment_loss_uses_all_selected_points_and_accepts_exactly_ten_percent():
    # 40 regular fixes, two 4-point fragments, then32regular fixes over167h.
    # Eight discarded fixes out of80 are exactly10%; retained endpoints still
    # span almost7days. Recomputing the denominator after deletion would fail.
    source = track([2] * 39 + [5] + [2] * 3 + [5] + [2] * 3 + [5] + [2] * 31)
    times = [point["timestamp"] for point in source]
    accepted, reason = _candidate(source, times, 0, short_study_config(max_short_fragment_loss=0.10))
    assert reason == "accepted"
    assert accepted["resampled_fixes"] == 80
    assert accepted["selected_fixes"] == 72
    assert accepted["dropped_short_fixes"] == 8
    assert accepted["short_fragment_loss"] == pytest.approx(0.1)
    assert accepted["short_fragment_warning"]
    assert accepted["max_source_gap_hours"] == 5
    assert accepted["max_within_segment_gap_hours"] == 2
    assert accepted["n_subtrajectories"] == 2
    assert all(p["dt_hours"] is None for p in accepted["points"] if p["step_index"] == 0)
    rejected, reason = _candidate(source, times, 0, short_study_config(max_short_fragment_loss=0.099))
    assert rejected is None
    assert reason == "excess_short_fragment_loss"
    rejected_default, reason = _candidate(source, times, 0, short_study_config())
    assert rejected_default is None and reason == "excess_short_fragment_loss"


@pytest.mark.parametrize("start, expected_end", [
    (datetime(2015, 1, 29), datetime(2015, 2, 5)),
    (datetime(2015, 12, 28), datetime(2016, 1, 4)),
    (datetime(2020, 2, 25), datetime(2020, 3, 3)),
])
def test_full_week_crosses_month_year_and_leap_day_boundaries(start, expected_end):
    source = track([2] * 84, start=start)
    candidate, reason = _candidate(source, [p["timestamp"] for p in source], 0, short_study_config())
    assert reason == "accepted"
    assert candidate["start"] == start
    assert candidate["end"] == expected_end
    assert candidate["selected_fixes"] == candidate["expected_fixes"] == 85
    assert candidate["duration_days"] == candidate["window_duration_days"] == 7
    assert candidate["points"][-1]["timestamp"] == expected_end
    assert candidate["crosses_month_boundary"]
    assert candidate["crosses_year_boundary"] == (start.year != expected_end.year)
    assert not candidate["window_end_exclusive"]
    assert candidate["violation_codes"] == []
    assert not candidate["requires_week_relaxation"]
    if start.year == 2020:
        assert any(p["timestamp"].date() == datetime(2020, 2, 29).date() for p in candidate["points"])


def test_crossing_a_month_does_not_waive_the_observed_span_requirement():
    short = track([2] * 72, start=datetime(2015, 1, 29))
    candidate, reason = _candidate(short, [p["timestamp"] for p in short], 0, short_study_config())
    assert candidate is None and reason == "insufficient_observed_span"


def test_window_can_cross_more_than_two_months_with_unchanged_density_reference():
    source = track([2] * (90 * 12), start=datetime(2019, 12, 15))
    cfg = short_study_config(week_days=90, min_week_observed_span_days=89.5)
    candidate, reason = _candidate(source, [p["timestamp"] for p in source], 0, cfg)
    assert reason == "accepted"
    assert candidate["window_duration_days"] == candidate["duration_days"] == 90
    assert candidate["selected_fixes"] == candidate["expected_fixes"] == 1081
    assert candidate["end"] == datetime(2020, 3, 14)
    assert {(p["timestamp"].year, p["timestamp"].month) for p in candidate["points"]} == {
        (2019, 12), (2020, 1), (2020, 2), (2020, 3)}
    assert candidate["short_fragment_loss"] == 0
    assert candidate["violation_codes"] == []


def test_full_record_month_counts_and_tracking_span_are_descriptive():
    source = []
    for month in (1, 2, 4):
        source.extend(track([2] * 84, start=datetime(2015, month, 1)))
    output = find_week_candidates(source)
    audit = output["individuals"][0]
    assert audit["eligible"]
    assert audit["qualifying_months"] == 3
    assert audit["has_candidate"]
    assert len(output["candidates"]) == 3
    sparse = [source[0], source[85], source[170]]
    sparse_audit = find_week_candidates(sparse)["individuals"][0]
    assert sparse_audit["observed_months"] == 3
    assert sparse_audit["qualifying_months"] == 0
    assert sparse_audit["support_violation_codes"] == []
    assert not sparse_audit["support_warning"]
    assert not sparse_audit["has_candidate"]  # Window-quality rules still apply.
    short_span = []
    for month in (1, 2, 3):
        short_span.extend(track([2] * 84, start=datetime(2015, month, 1)))
    short_audit = find_week_candidates(short_span)["individuals"][0]
    assert short_audit["qualifying_months"] == 3
    assert short_audit["tracking_span_days"] < 90
    assert short_audit["support_violation_codes"] == []
    assert short_audit["eligible"]
    assert short_audit["has_candidate"]
    assert "meets_support_guideline" not in short_audit
    candidate = find_week_candidates(short_span)["candidates"][0]
    assert not candidate["support_warning"]
    assert "required_tracking_span_days" not in candidate
    assert "required_supported_months" not in candidate
    assert candidate["support_violation_text"] == ""


@pytest.mark.parametrize("native_interval", [3, 4, 5, 8])
def test_consistently_sparse_record_cannot_fabricate_a_two_hour_week(native_interval):
    source = track([native_interval] * 800)
    output = find_week_candidates(source)
    assert output["individuals"][0]["eligible"]
    assert not output["candidates"]
    assert not output["relaxed_candidates"]
    assert "No scanned parent window" in output["individuals"][0]["protected_exclusion_text"]
    assert "no_qualifying_window" in output["individuals"][0]["exclusion_reasons"]
    assert output["individuals"][0]["rejected_window_reasons"]["insufficient_selected_fixes"] > 0


def test_occasional_four_hour_interval_passes_without_becoming_two_hours():
    source = track([2] * 41 + [4] + [2] * 41)
    candidate = find_week_candidates(source, short_study_config())["candidates"][0]
    assert candidate["selected_fixes"] == 84
    assert candidate["n_subtrajectories"] == 1
    assert candidate["affected_point_fraction"] == pytest.approx(2 / 84)
    assert candidate["max_within_segment_gap_hours"] == 4
    assert sum(point["dt_hours"] == 4 for point in candidate["points"]) == 1


def test_local_two_hour_period_can_qualify_despite_sparse_remainder_of_study():
    # A median cadence of3h for an animal must not hide its genuine2h week.
    before = track([3] * 280)
    dense = track([2] * 84, start=before[-1]["timestamp"])
    after = track([3] * 400, start=dense[-1]["timestamp"] + timedelta(hours=3))
    source = before[:-1] + dense + after
    output = find_week_candidates(source)
    assert output["individuals"][0]["eligible"]
    assert output["individuals"][0]["has_candidate"]
    assert any(candidate["selected_fixes"] == 85 and candidate["regular_fraction"] == 1
               for candidate in output["candidates"])


def test_sparse_irregular_run_is_dropped_rather_than_renamed_as_regular():
    result = segment_points(track([3] * 20), TemporalConfig())
    assert result["segments"] == []
    assert result["short_fragment_loss"] == 1
    assert result["source_metrics"]["affected_point_fraction"] == 1


def test_dense_short_study_has_no_full_record_support_warning():
    out = find_week_candidates(track([2] * 84))
    assert len(out["candidates"]) == 1
    candidate = out["candidates"][0]
    assert not candidate["support_warning"]
    assert candidate["support_violation_codes"] == []
    assert candidate["qualifying_months"] == 1
    assert candidate["violation_codes"] == []
    assert candidate["protected_rules_pass"]
    assert out["individuals"][0]["scanned_windows"] > 0


def test_descriptive_month_threshold_does_not_change_window_selection():
    source = track([2] * 84)
    outputs = [find_week_candidates(source, TemporalConfig(min_days_per_month=days))
               for days in (1, 9)]
    assert [out["individuals"][0]["qualifying_months"] for out in outputs] == [1, 0]
    for key in ("candidates", "relaxed_candidates"):
        signatures = [[(w["individual_id"], w["start"], w["end"],
                        w["selected_fixes"], w["violation_codes"], w["support_warning"])
                       for w in out[key]] for out in outputs]
        assert signatures[0] == signatures[1]


def test_relaxed_density_and_span_are_quantified_without_relaxing_cadence():
    out = find_week_candidates(track([2] * 40))
    assert out["candidates"] == []
    assert len(out["relaxed_candidates"]) == 1
    candidate = out["relaxed_candidates"][0]
    assert candidate["selected_fixes"] == 41
    assert candidate["required_fixes"] == 68
    assert candidate["duration_days"] == pytest.approx(80 / 24)
    assert set(candidate["violation_codes"]) == {
        "insufficient_retained_fixes", "insufficient_retained_span"}
    assert "41/85" in candidate["violation_text"]
    assert "3.33 days" in candidate["violation_text"]
    assert candidate["short_fragment_loss"] == 0
    assert candidate["max_segment_affected_fraction"] == 0
    assert candidate["max_within_segment_gap_hours"] == 2


def test_relaxed_window_keeps_original_short_fragment_loss_denominator():
    source = track([2] * 9 + [5] + [2] * 3)
    diagnostics = {}
    candidate, reason = _candidate(source, [p["timestamp"] for p in source], 0,
                                   TemporalConfig(), relax_week_quality=True,
                                   diagnostics=diagnostics)
    assert candidate is None
    assert reason == "excess_short_fragment_loss"
    assert diagnostics["resampled_fixes"] == 14
    assert diagnostics["retained_fixes"] == 10
    assert diagnostics["short_fragment_loss"] == pytest.approx(4 / 14)


def test_relaxed_windows_still_split_hard_gaps_and_respect_point_fraction():
    source = track([2] * 4 + [9] + [2] * 4 + [4] + [2] * 4)
    candidate, reason = _candidate(source, [p["timestamp"] for p in source], 0,
                                   TemporalConfig(), relax_week_quality=True)
    assert reason == "accepted"
    assert candidate["requires_week_relaxation"]
    assert candidate["n_subtrajectories"] == 2
    assert candidate["max_source_gap_hours"] == 9
    assert candidate["max_within_segment_gap_hours"] == 4
    assert candidate["max_segment_affected_fraction"] <= .2
    assert candidate["short_fragment_loss"] == 0
    assert all(segment["n_points"] >= 5 for segment in candidate["segments"])


def test_relaxed_window_never_rescues_fewer_than_five_points():
    out = find_week_candidates(track([2] * 3))
    assert not out["candidates"]
    assert not out["relaxed_candidates"]
    evidence = out["individuals"][0]["best_protected_rejected_window"]
    assert evidence["retained_fixes"] == 0
    assert evidence["short_fragment_loss"] == 1


def test_main_candidate_suppresses_weaker_relaxed_candidate_in_same_month():
    out = find_week_candidates(track([2] * 84))
    assert out["candidates"]
    assert not out["relaxed_candidates"]
    assert out["individuals"][0]["relaxed_qualifying_windows"] > 0


def test_month_tail_relaxed_window_keeps_next_month_fixes_and_full_parent_duration():
    source = track([2] * 40, start=datetime(2015, 1, 29))
    out = find_week_candidates(source)
    january = [c for c in out["relaxed_candidates"] if c["month"] == 1][0]
    assert not out["candidates"]
    assert january["window_duration_days"] == january["reference_window_duration_days"] == 7
    assert january["expected_fixes"] == 85
    assert january["selected_fixes"] == 41
    assert january["end"] == datetime(2015, 2, 5)
    assert not january["window_end_exclusive"]
    assert {p["timestamp"].month for p in january["points"]} == {1, 2}
    assert set(january["violation_codes"]) == {"insufficient_retained_fixes", "insufficient_retained_span"}
    assert out["individuals"][0]["scanned_windows"] == len(source)
    assert out["individuals"][0]["scanned_cross_month_windows"] == 36
    assert out["individuals"][0]["scanned_cross_year_windows"] == 0


def test_cross_year_candidates_retain_start_year_month_for_grouping():
    source = track([2] * 84, start=datetime(2015, 12, 28))
    out = find_week_candidates(source)
    assert len(out["candidates"]) == 1
    december = out["candidates"][0]
    assert december["year"] == 2015 and december["month"] == 12
    assert {p["timestamp"].year for p in december["points"]} == {2015, 2016}
    audit = out["individuals"][0]
    assert audit["scanned_windows"] == len(source)
    assert audit["scanned_cross_month_windows"] == audit["scanned_cross_year_windows"] == 48


def test_full_parent_prevents_month_clipping_from_hiding_fragment_loss():
    # Ten regular January fixes form a valid prefix. Four February fixes are
    # an isolated short fragment; the full parent must include them in loss.
    source = track([2] * 9 + [8] + [2] * 3, start=datetime(2015, 1, 31))
    january_prefix = [p for p in source if p["timestamp"].month == 1]
    assert len(january_prefix) == 10
    assert segment_points(january_prefix, TemporalConfig())["short_fragment_loss"] == 0
    diagnostics = {}
    candidate, reason = _candidate(source, [p["timestamp"] for p in source], 0,
                                   TemporalConfig(), relax_week_quality=True,
                                   diagnostics=diagnostics)
    assert candidate is None and reason == "excess_short_fragment_loss"
    assert diagnostics["crosses_month_boundary"]
    assert diagnostics["window_duration_days"] == 7
    assert diagnostics["end"] == datetime(2015, 2, 7)
    assert diagnostics["resampled_fixes"] == 14
    assert diagnostics["retained_fixes"] == 10
    assert diagnostics["short_fragment_loss"] == pytest.approx(4 / 14)


def test_period_budget_can_support_an_irregular_segment_above_twenty_percent_locally():
    # Sixty-five regular points and ten native3hpoints separated by a hard gap.
    # Ten affected points /75 sampled points passes, even though the final
    # segment has100% affected points locally.
    source = track([2]*64 + [5] + [3]*9)
    candidate,reason = _candidate(source,[p['timestamp'] for p in source],0,short_study_config())
    assert reason=='accepted'
    assert candidate['selected_fixes']==candidate['resampled_fixes']==75
    assert [s['n_points'] for s in candidate['segments']]==[65,10]
    assert candidate['retained_affected_points']==10
    assert candidate['affected_point_denominator']==75
    assert candidate['affected_point_fraction']==pytest.approx(10/75)
    assert candidate['max_segment_affected_fraction']==1
    assert candidate['short_fragment_loss']==0


def test_period_budget_denominator_is_frozen_before_short_fragments_are_dropped():
    source=track([2]*4+[3]+[2]*4+[3]+[2]*8+[5])
    result=segment_points(source,TemporalConfig())
    assert len(source)==20
    assert list(map(len,result['segments']))==[19]
    assert len(result['dropped_points'])==1
    assert result['retained_affected_points']==4
    assert result['affected_point_denominator']==20
    assert result['period_affected_point_fraction']==.2
    assert interval_metrics(result['segments'][0],TemporalConfig())['affected_point_fraction']> .2
    assert result['short_fragment_loss']==.05


def test_period_budget_is_shared_between_hard_gap_runs_and_not_reset_for_each():
    gaps=[2]*4+[3]+[2]*4+[3]+[2]*4
    source=track(gaps+[5]+gaps)
    cfg=TemporalConfig()
    result=segment_points(source,cfg)
    assert len(source)==30
    assert sum(map(len,result['segments']))==30
    assert result['retained_affected_points']<=6
    assert result['affected_point_denominator']==30
    assert result['period_affected_point_fraction']<=.2
    assert max(interval_metrics(s,cfg)['affected_point_fraction'] for s in result['segments'])>.2
    assert all(interval_metrics(s,cfg)['max_gap_hours']<=4 for s in result['segments'])


def test_period_optimizer_matches_exhaustive_small_partitions():
    import random
    from itertools import product
    from jaguar_irl.data.movement_temporal import _period_partition_plan
    rng=random.Random(88)
    for _ in range(80):
        kinds=tuple(rng.randrange(3) for _ in range(8))
        minimum=rng.randrange(2,6)
        budget=rng.randrange(0,10)
        optional=[i+1 for i,k in enumerate(kinds) if k==1]
        hard={i+1 for i,k in enumerate(kinds) if k==2}
        best=None
        for bits in product((False,True),repeat=len(optional)):
            bounds=sorted({0,9,*hard,*[cut for cut,take in zip(optional,bits) if take]})
            kept=blocks=affected=0
            for left,right in zip(bounds,bounds[1:]):
                if right-left>=minimum:
                    kept+=right-left;blocks+=1
                    touched=set()
                    for i in range(left,right-1):
                        if kinds[i]==1:touched.update((i,i+1))
                    affected+=len(touched)
            if affected<=budget:
                score=(kept,-blocks,-(len(bounds)-1))
                if best is None or score>best:best=score
        plan=_period_partition_plan(kinds,minimum,budget)
        actual=(sum(b-a for a,b,keep in plan if keep),
                -sum(keep for a,b,keep in plan),-len(plan))
        assert actual==best,(kinds,minimum,budget,plan,best)
