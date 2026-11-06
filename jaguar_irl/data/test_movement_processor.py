"""Synthetic integration checks for full-record processing and segment exports."""

import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from .movement_temporal import interval_metrics

from .movement_processor import (
    COL_COUNTRY, COL_EVENT, COL_ID, COL_LAT, COL_LON, COL_SPECIES,
    COL_STUDY, COL_TAG, COL_TIMESTAMP, MovementProcessor, ProcessorConfig,
)


START = datetime(2010, 1, 1)


def frame_at_hours(hours, ident=12, event_start=1, start=START, longitude=-57.01):
    """Realistic CSV columns; each row has a distinct source event and time."""
    return pd.DataFrame([
        {COL_EVENT: event_start + index,
         COL_TIMESTAMP: start + timedelta(hours=float(hour)),
         COL_LON: longitude + index * 0.000137,
         COL_LAT: -19.9 + index * 0.000083,
         COL_SPECIES: "Panthera onca", COL_TAG: f"collar-{ident}",
         COL_ID: ident, COL_STUDY: "synthetic", COL_COUNTRY: "Brazil"}
        for index, hour in enumerate(hours)
    ])


def fragment_loss_bout(isolated_points, **kwargs):
    """Five isolated fixes among 100 cannot enter any admissible segment.

    Nineteen regular runs each contain five fixes. Four-hour edges separate
    them, with isolated fixes inserted between some runs. Six inserted fixes
    instead give a loss of 6/101, just beyond the five-percent allowance.
    """
    block_sizes = []
    for index in range(19):
        block_sizes.append(5)
        if index < isolated_points:
            block_sizes.append(1)
    hours, when = [], 0
    for size in block_sizes:
        for _ in range(size):
            hours.append(when)
            when += 2
        when += 2  # Four hours from the preceding block's final observation.
    return frame_at_hours(hours, **kwargs)


def processor_for_frame(frame, tmp_path):
    # Bypass only long-record eligibility for the small segmentation fixtures.
    # The legacy eligibility rules are exercised independently below.
    config = ProcessorConfig(min_fixes=1, min_duration_days=0, max_gap_fraction=1,
                             output_dir=str(tmp_path))
    processor = MovementProcessor(config)
    processor.raw_df = frame.copy()
    processor.df = frame.copy()
    processor.compute_individual_stats()
    processor.filter_individuals()
    return processor


def test_exactly_five_percent_fragment_loss_is_accepted(tmp_path):
    processor = processor_for_frame(fragment_loss_bout(5), tmp_path)
    processor.resample_and_segment()

    assert processor.config.max_short_fragment_loss == 0.05
    assert len(processor.df) == 95
    assert processor.retained_ids == [12]
    audit = processor.bout_audit.iloc[0]
    assert audit["n_sampled"] == 100
    assert audit["n_short_fixes"] == 5
    assert audit["short_fragment_loss"] == pytest.approx(0.05)
    assert bool(audit["accepted"])
    assert audit["retained_fixes"] == 95
    assert processor.df["trajectory_id"].nunique() > 1
    assert not processor.df[COL_EVENT].duplicated().any()


def test_excess_loss_rejects_only_its_bout_and_preserves_same_animal(tmp_path):
    good = frame_at_hours(np.arange(10) * 2, event_start=1)
    bad = fragment_loss_bout(6, start=START + timedelta(days=15), event_start=1000)
    processor = processor_for_frame(pd.concat([good, bad], ignore_index=True), tmp_path)
    processor.resample_and_segment()

    assert processor.qualified_ids == processor.retained_ids == [12]
    assert set(processor.df[COL_EVENT]) == set(good[COL_EVENT])
    assert processor.df["individual_id"].unique().tolist() == [12]
    assert processor.df["split_group_id"].unique().tolist() == [12]
    rejected = processor.bout_audit.loc[~processor.bout_audit["accepted"]].iloc[0]
    assert rejected["n_sampled"] == 101
    assert rejected["n_short_fixes"] == 6
    assert rejected["short_fragment_loss"] == pytest.approx(6 / 101)
    assert rejected["rejection_reason"] == "excess_short_fragment_loss"
    assert rejected["retained_fixes"] == 0
    assert rejected["rejected_good_fixes"] == 95
    assert processor.bout_audit["accepted"].sum() == 1


def test_actual_gap_timing_shared_grid_and_ids_survive_segment_export(tmp_path):
    # Exactly two of ten observations touch the four-hour interval.
    first = frame_at_hours([0, 2, 4, 6, 10, 12, 14, 16, 18, 20], event_start=1)
    second = frame_at_hours(np.arange(6) * 2, start=START + timedelta(days=5),
                            event_start=100, longitude=-56.98)
    processor = processor_for_frame(pd.concat([first, second], ignore_index=True), tmp_path)
    processor.resample_and_segment()
    processor.project_to_utm()
    grids = processor.discretize_to_grid()
    assert len(grids) == 2

    common_grids = set()
    saw_four_hour_gap = False
    for trajectory_id, data in grids.items():
        selected = processor.df.loc[processor.df["trajectory_id"] == trajectory_id]
        selected = selected.sort_values("step_index")
        trajectory = data["trajectory"]
        count = len(selected)
        assert trajectory.shape == (count, 3)
        assert np.issubdtype(trajectory.dtype, np.integer)
        np.testing.assert_array_equal(trajectory[:, 2], np.arange(count))
        assert data["grid_shape"][2] == count
        assert data["individual_id"] == data["split_group_id"] == 12
        assert data["trajectory_id"] == trajectory_id
        assert data["utm_epsg"] == 32721
        assert data["cell_size_m"] == 500
        assert data["time_axis"] == "observation_index_not_elapsed_time"
        assert data["trajectory_columns"] == ["row", "col", "step_index"]
        common_grids.add((tuple(data["grid_bounds_m"]), tuple(data["grid_shape"][:2]),
                          data["utm_epsg"]))

        xmin, ymin, xmax, ymax = data["grid_bounds_m"]
        rows, cols = data["grid_shape"][:2]
        cell = data["cell_size_m"]
        assert data["grid_origin"] == pytest.approx((xmin, ymin))
        assert data["grid_origin_top_left"] == pytest.approx((xmin, ymax))
        assert xmax - xmin == pytest.approx(cols * cell)
        assert ymax - ymin == pytest.approx(rows * cell)
        # Check each observation against its returned cell's physical bounds.
        for (row, col, _), (_, point) in zip(trajectory, selected.iterrows()):
            assert 0 <= row < rows and 0 <= col < cols
            assert xmin + col * cell - 1e-6 <= point["utm_x"] <= xmin + (col + 1) * cell + 1e-6
            assert ymax - (row + 1) * cell - 1e-6 <= point["utm_y"] <= ymax - row * cell + 1e-6

        dates = pd.to_datetime(data["timestamps"])
        observed_dt = np.diff(dates.to_numpy()) / np.timedelta64(1, "h")
        np.testing.assert_allclose(data["dt_hours"][1:], observed_dt)
        elapsed = (dates - dates[0]).total_seconds() / 3600
        np.testing.assert_allclose(data["elapsed_hours"], elapsed)
        assert data["dt_hours"][0] is None
        assert data["event_ids"] == selected[COL_EVENT].tolist()
        if 4 in data["dt_hours"]:
            saw_four_hour_gap = True
            assert trajectory[4, 2] == 4  # Observation index, not elapsed hours.
            assert data["elapsed_hours"][4] == 10
    assert len(common_grids) == 1
    assert saw_four_hour_gap

    processor.export_trajectories(grids)
    basenames = (tmp_path / "basename.txt").read_text().splitlines()
    assert len(basenames) == 2
    metadata_by_id = {}
    for basename in basenames:
        tracking = tmp_path / "tracking"
        loaded = np.load(tracking / f"{basename}.npy", allow_pickle=False)
        metadata = json.loads((tracking / f"{basename}_meta.json").read_text())
        metadata_npy = np.load(tracking / f"{basename}_meta.npy", allow_pickle=True).item()
        ident = metadata["trajectory_id"]
        np.testing.assert_array_equal(loaded, grids[ident]["trajectory"])
        assert metadata["time_axis"] == "observation_index_not_elapsed_time"
        assert metadata["dt_hours"] == metadata_npy["dt_hours"]
        assert metadata["dt_hours"][0] is None
        metadata_by_id[ident] = metadata
    assert set(metadata_by_id) == set(grids)
    assert any(4 in meta["dt_hours"] for meta in metadata_by_id.values())
    exported_points = pd.read_csv(tmp_path / "selected_points.csv")
    assert len(exported_points) == 16
    assert 4 in exported_points["dt_hours"].tolist()
    assert exported_points["source_dt_hours"].max() > 4
    assert exported_points["individual_id"].unique().tolist() == [12]
    summary = pd.read_csv(tmp_path / "individual_summary.csv")
    assert len(summary) == 1 and summary.iloc[0]["n_fixes"] == 16
    assert len(pd.read_csv(tmp_path / "trajectory_manifest.csv")) == 2


def test_no_eligible_individual_produces_valid_empty_exports(tmp_path):
    source = tmp_path / "input.csv"
    frame_at_hours(np.arange(10) * 2).to_csv(source, index=False)
    output = tmp_path / "output"
    processor = MovementProcessor(ProcessorConfig(csv_path=str(source), output_dir=str(output)))
    grids = processor.run_pipeline()

    assert grids == {}
    assert processor.qualified_ids == processor.retained_ids == []
    assert (output / "basename.txt").read_text() == ""
    assert not list((output / "tracking").glob("*.npy"))
    for filename in ("selected_points.csv", "trajectory_manifest.csv", "bout_audit.csv"):
        assert pd.read_csv(output / filename).empty
    summary = pd.read_csv(output / "individual_summary.csv")
    assert len(summary) == 1
    assert not bool(summary.iloc[0]["eligible"])
    assert summary.iloc[0]["n_fixes"] == 0


def test_legacy_eligibility_uses_sixty_days_and_inclusive_empty_day_fraction():
    # Both records have >100 fixes and >60 days' span. ID12 has data on exactly
    # half of 62 calendar dates; ID13 has data on fewer than half and fails.
    half_days = list(range(30)) + [61]
    fewer_days = list(range(29)) + [61]
    halves = frame_at_hours([day * 24 + hour for day in half_days for hour in (0, 2, 4, 6)])
    fewer = frame_at_hours([day * 24 + hour for day in fewer_days for hour in (0, 2, 4, 6)],
                           ident=13, event_start=1000)
    daily = frame_at_hours([day * 24 + hour for day in range(61) for hour in (0, 2)],
                           ident=14, event_start=2000)
    processor = MovementProcessor()
    processor.df = pd.concat([halves, fewer, daily], ignore_index=True)
    processor.raw_df = processor.df.copy()
    stats = processor.compute_individual_stats().set_index(COL_ID)
    assert processor.config.min_fixes == 100
    assert processor.config.min_duration_days == 60
    assert processor.config.max_gap_fraction == 0.50
    assert stats.loc[12, "gap_fraction"] == pytest.approx(0.5)
    assert stats.loc[13, "gap_fraction"] > 0.5
    assert stats.loc[14, "gap_fraction"] == 0
    assert (stats["duration_days"] < 90).all()
    assert processor.filter_individuals() == [12, 14]


def observations(hours, individual=12):
    start = pd.Timestamp("2015-01-28")
    return pd.DataFrame([
        {COL_ID: individual, COL_EVENT: f"event_{i}",
         COL_TIMESTAMP: start + pd.Timedelta(hours=hour),
         COL_LON: -57.0, COL_LAT: -17.0}
        for i, hour in enumerate(hours)
    ])


def test_full_record_sampling_crosses_months_and_keeps_observed_events():
    processor = MovementProcessor()
    source = observations(range(14 * 24 + 1))
    result = processor.sample_individual(source)
    selected = result["selected_points"]

    assert len(selected) == 169
    assert [p[COL_EVENT] for p in selected] == source.iloc[::2][COL_EVENT].tolist()
    assert selected[-1]["timestamp"] - selected[0]["timestamp"] == pd.Timedelta(days=14)
    assert {p["timestamp"].month for p in selected} == {1, 2}
    assert len(result["bouts"]) == len(result["bouts"][0]["segments"]) == 1
    assert all(p[COL_ID] == 12 for p in selected)


def test_hard_gaps_separate_bouts_and_short_fragment_loss_stays_auditable():
    result = MovementProcessor().sample_individual(observations([0, 2, 4, 6, 8, 20, 22, 24]))
    first, second = result["bouts"]

    assert len(first["segments"][0]) == 5
    assert first["short_fragment_loss"] == 0
    assert second["segments"] == []
    assert second["short_fragment_loss"] == 1
    assert [p[COL_EVENT] for p in second["dropped_points"]] == ["event_5", "event_6", "event_7"]
    assert result["resampled_fixes"] == 8  # Denominator includes short fragments.


def test_tolerated_four_hour_interval_preserves_real_timestamps():
    processor = MovementProcessor()
    result = processor.sample_individual(observations([0, 2, 4, 6, 8, 12, 14, 16, 18, 20]))
    segment = result["bouts"][0]["segments"][0]
    quality = interval_metrics(segment, processor.config.sampling_config())

    assert len(segment) == 10
    assert quality["affected_point_fraction"] == pytest.approx(0.2)
    assert quality["max_gap_hours"] == 4
    assert segment[5]["timestamp"] - segment[4]["timestamp"] == pd.Timedelta(hours=4)


@pytest.mark.parametrize("interval", [3, 4, 5, 8])
def test_consistently_sparse_record_produces_no_qualifying_segments(interval):
    result = MovementProcessor().sample_individual(observations(range(0, 300, interval)))
    assert not any(bout["segments"] for bout in result["bouts"])


def test_conflicting_timestamps_and_mixed_animals_require_explicit_resolution():
    processor = MovementProcessor()
    with pytest.raises(ValueError, match="duplicate"):
        processor.sample_individual(observations([0, 2, 2, 4]))
    with pytest.raises(ValueError, match="exactly one individual"):
        processor.sample_individual(pd.concat([observations([0, 2]), observations([0, 2], 13)]))
