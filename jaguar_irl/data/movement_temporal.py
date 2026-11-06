"""Shared observed-fix sampling and trajectory segmentation rules.

These primitives operate on one individual's datetime-stamped observations.
They never interpolate locations or relabel a longer observed interval as a
regular interval. Full-record processing and Pantanal week selection share the
same cadence, affected-point counting, and minimum-length implementation.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from math import floor
from typing import Any


@dataclass(frozen=True)
class SamplingConfig:
    """Sampling and segment cutoffs; durations are expressed in hours.

    The five-point minimum is a configurable screening floor, not a guarantee
    of biological independence or model adequacy. A tolerated irregular gap
    affects both endpoint fixes; shared endpoints are counted only once.
    """

    target_interval_hours: float = 2.0
    regular_min_hours: float = 1.5
    regular_max_hours: float = 2.5
    max_gap_hours: float = 4.0
    max_affected_point_fraction: float = 0.20
    min_subtrajectory_points: int = 5

    def __post_init__(self) -> None:
        if not 0 < self.regular_min_hours <= self.target_interval_hours <= self.regular_max_hours <= self.max_gap_hours:
            raise ValueError("Require 0 < regular_min <= target <= regular_max <= max_gap.")
        if not 0 <= self.max_affected_point_fraction <= 1:
            raise ValueError("max_affected_point_fraction must lie between 0 and 1.")
        if self.min_subtrajectory_points < 2:
            raise ValueError("Require at least two points per subtrajectory.")


def _hours(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 3600.0


def interval_metrics(points: list[dict[str, Any]], config: SamplingConfig) -> dict[str, Any]:
    """Count unique points adjacent to tolerated irregular intervals, once each.

    A four-hour edge touches two points. Two adjacent four-hour edges touch
    three unique points. This is a point fraction, distinct from missing-slot
    fraction and irregular-edge fraction. Edges over max_gap are reported as
    hard breaks and are not treated as tolerated intervals.
    """
    gaps = [_hours(a["timestamp"], b["timestamp"]) for a, b in zip(points, points[1:])]
    affected: set[int] = set()
    for i, gap in enumerate(gaps):
        if config.regular_max_hours < gap <= config.max_gap_hours:
            affected.update((i, i + 1))
    return {
        "gaps": gaps,
        "affected_indices": affected,
        "affected_points": len(affected),
        "affected_point_fraction": len(affected) / len(points) if points else 0.0,
        "regular_intervals": sum(config.regular_min_hours <= g <= config.regular_max_hours for g in gaps),
        "irregular_intervals": sum(config.regular_max_hours < g <= config.max_gap_hours for g in gaps),
        "hard_gaps": sum(g > config.max_gap_hours for g in gaps),
        "regular_fraction": sum(config.regular_min_hours <= g <= config.regular_max_hours for g in gaps) / len(gaps) if gaps else 1.0,
        "max_gap_hours": max(gaps, default=0.0),
    }


def _thin_window(records: list[dict[str, Any]], times: list[datetime], start_index: int,
                 stop_index: int, config: SamplingConfig) -> list[dict[str, Any]]:
    """Choose actual fixes closest to the next two-hour target, within tolerance.

    Prefer a regular interval; if none exists, use the earliest fix within the
    tolerated longer interval. If neither exists, retain the next available fix
    and mark a hard break later. The phase follows observed timestamps, so small
    clock drift does not cause cumulative rejection against a fixed clock grid.
    """
    selected = [records[start_index]]
    current = start_index
    while current + 1 < stop_index:
        when = times[current]
        lo = bisect_left(times, when + timedelta(hours=config.regular_min_hours), current + 1, stop_index)
        if lo >= stop_index:
            break
        hi = bisect_right(times, when + timedelta(hours=config.regular_max_hours), lo, stop_index)
        if lo < hi:
            target = when + timedelta(hours=config.target_interval_hours)
            at = bisect_left(times, target, lo, hi)
            choices = [i for i in (at - 1, at) if lo <= i < hi]
            current = min(choices, key=lambda i: (abs(times[i] - target), times[i]))
        else:
            # Earliest tolerated fix, or the first fix following a hard gap.
            current = lo
        selected.append(records[current])
    return selected


def _partition_run(points: list[dict[str, Any]], config: SamplingConfig) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
    """Partition one <=4-hour run, maximizing retained points before cut count.

    Cuts are allowed only at actual irregular intervals. A retained block must
    have >=min_subtrajectory_points and <=20% affected points. Dropped blocks
    must be shorter than the minimum. Dynamic programming looks beyond the
    first irregular edge, avoiding the arbitrary reset of a running percentage
    near the beginning of a trajectory. Ties prefer fewer retained blocks and
    then fewer total blocks. No source point is duplicated between blocks.
    """
    n = len(points)
    if n < config.min_subtrajectory_points:
        return [], points[:]
    metrics = interval_metrics(points, config)
    if metrics["hard_gaps"]:
        raise ValueError("_partition_run must receive a run without hard gaps.")
    if metrics["affected_point_fraction"] <= config.max_affected_point_fraction + 1e-12:
        return [points], []

    bad = [gap > config.regular_max_hours for gap in metrics["gaps"]]
    # If every interval is irregular, every block with at least two points
    # has 100% affected points. No admissible retained block exists. This
    # exact shortcut avoids quadratic work on long native 3- or 4-hour runs.
    if all(bad) and config.max_affected_point_fraction + 1e-12 < 1.0:
        return [], points[:]
    boundaries = [0] + [i + 1 for i, flag in enumerate(bad) if flag] + [n]
    edge_prefix = [0]
    for flag in bad:
        edge_prefix.append(edge_prefix[-1] + int(flag))
    shared_prefix = [0]
    for a, b in zip(bad, bad[1:]):
        shared_prefix.append(shared_prefix[-1] + int(a and b))

    def affected_count(left: int, right: int) -> int:
        size = right - left
        if size < 2:
            return 0
        edge_count = edge_prefix[right - 1] - edge_prefix[left]
        shared = shared_prefix[right - 2] - shared_prefix[left] if size >= 3 else 0
        return 2 * edge_count - shared

    # Each state is (retained points, negative retained blocks, negative blocks).
    scores: list[tuple[int, int, int] | None] = [None] * len(boundaries)
    previous: list[tuple[int, bool] | None] = [None] * len(boundaries)
    scores[0] = (0, 0, 0)
    for end_i in range(1, len(boundaries)):
        right = boundaries[end_i]
        for start_i in range(end_i):
            if scores[start_i] is None:
                continue
            left = boundaries[start_i]
            size = right - left
            keep = size >= config.min_subtrajectory_points
            if keep and affected_count(left, right) / size > config.max_affected_point_fraction + 1e-12:
                continue
            old = scores[start_i]
            score = (old[0] + (size if keep else 0), old[1] - int(keep), old[2] - 1)
            if scores[end_i] is None or score > scores[end_i]:
                scores[end_i] = score
                previous[end_i] = (start_i, keep)
    if scores[-1] is None:
        raise RuntimeError("Unable to partition a run into regular bursts.")
    pieces = []
    end_i = len(boundaries) - 1
    while end_i:
        start_i, keep = previous[end_i]
        pieces.append((boundaries[start_i], boundaries[end_i], keep))
        end_i = start_i
    kept, dropped = [], []
    for left, right, keep in reversed(pieces):
        if keep:
            kept.append(points[left:right])
        else:
            dropped.extend(points[left:right])
    return kept, dropped


def segment_points(points: list[dict[str, Any]], config: SamplingConfig) -> dict[str, Any]:
    """Apply hard-gap, per-segment quality, and minimum-length rules.

    The denominator for short_fragment_loss is frozen before any segmentation.
    All parent quality metrics remain available even if cuts remove irregular
    transitions from the exported subtrajectories.
    """
    source_metrics = interval_metrics(points, config)
    runs: list[list[dict[str, Any]]] = []
    for point in points:
        if not runs or _hours(runs[-1][-1]["timestamp"], point["timestamp"]) > config.max_gap_hours:
            runs.append([])
        runs[-1].append(point)
    segments, dropped = [], []
    for run in runs:
        kept_part, dropped_part = _partition_run(run, config)
        segments.extend(kept_part)
        dropped.extend(dropped_part)
    return {
        "segments": segments,
        "dropped_points": dropped,
        "source_metrics": source_metrics,
        "hard_run_count": len(runs),
        "short_fragment_loss": len(dropped) / len(points) if points else 0.0,
    }


@lru_cache(maxsize=4096)
def _period_partition_plan(gap_types: tuple[int, ...], minimum: int, budget: int):
    """Exact pooled-budget partition; 0=regular, 1=tolerated, 2=hard gap.

    States retain the best (points, -retained blocks, -total blocks) for each
    used affected-point budget. Lower-cost states with equal or better scores
    dominate higher-cost ones. Cuts are confined to irregular/hard intervals,
    and a hard gap cannot be crossed. Only blocks below the length floor may
    be discarded. The cache depends on interval categories, not clock drift.
    """
    n = len(gap_types) + 1
    hard_bounds = [0] + [i + 1 for i, kind in enumerate(gap_types) if kind == 2] + [n]
    base = [(left, right, right - left >= minimum)
            for left, right in zip(hard_bounds, hard_bounds[1:])]
    affected = [0] * n
    for i, kind in enumerate(gap_types):
        if kind == 1:
            affected[i] = affected[i + 1] = 1
    if sum(sum(affected[left:right]) for left, right, keep in base if keep) <= budget:
        return tuple(base)

    if all(kind == 1 for kind in gap_types):
        # Every retained point in an all-irregular run consumes one unit.
        keep_count = min(n, budget) if budget >= minimum else 0
        parts = [(0, keep_count, True)] if keep_count else []
        for left in range(keep_count, n, minimum - 1):
            parts.append((left, min(left + minimum - 1, n), False))
        return tuple(parts)

    boundaries = [0] + [i + 1 for i, kind in enumerate(gap_types) if kind] + [n]
    edge_prefix, shared_prefix = [0], [0]
    for kind in gap_types:
        edge_prefix.append(edge_prefix[-1] + int(kind == 1))
    for a, b in zip(gap_types, gap_types[1:]):
        shared_prefix.append(shared_prefix[-1] + int(a == b == 1))

    def cost(left, right):
        size = right - left
        edges = edge_prefix[right - 1] - edge_prefix[left]
        shared = shared_prefix[right - 2] - shared_prefix[left] if size >= 3 else 0
        return 2 * edges - shared

    states = [{0: ((0, 0, 0), None, False)}] + [{} for _ in boundaries[1:]]
    last_hard = 0
    for end_i in range(1, len(boundaries)):
        right = boundaries[end_i]
        current = states[end_i]
        for start_i in range(end_i - 1, -1, -1):
            left = boundaries[start_i]
            if left < last_hard:
                break
            size = right - left
            keep = size >= minimum
            used = cost(left, right) if keep else 0
            if used > budget:
                continue
            for old_cost, (old_score, _, _) in states[start_i].items():
                total = old_cost + used
                if total > budget:
                    continue
                score = (old_score[0] + (size if keep else 0),
                         old_score[1] - int(keep), old_score[2] - 1)
                if total not in current or score > current[total][0]:
                    current[total] = (score, (start_i, old_cost), keep)
        best = None
        for used in sorted(current):
            score = current[used][0]
            if best is not None and best >= score:
                del current[used]
            else:
                best = score
        if right < n and gap_types[right - 1] == 2:
            last_hard = right
    if not states[-1]:
        raise RuntimeError("Unable to partition the period within its affected-point budget")
    end_i = len(boundaries) - 1
    used = max(states[-1], key=lambda value: (states[-1][value][0], -value))
    parts = []
    while end_i:
        _, (start_i, previous_cost), keep = states[end_i][used]
        parts.append((boundaries[start_i], boundaries[end_i], keep))
        end_i, used = start_i, previous_cost
    return tuple(reversed(parts))


def segment_period_points(points: list[dict[str, Any]], config: SamplingConfig) -> dict[str, Any]:
    """Share one affected-endpoint budget across a complete selected period.

    The denominator is ALL resampled points before cuts or fragment removal.
    Count each retained point once when an adjacent retained interval is >2.5
    and <=4 hours. Removing a transition by cutting removes its contribution;
    a point still counts if its other retained neighbour remains irregular.
    Individual segments may exceed 20% locally when the pooled budget permits.
    The generic full-record processor's established per-bout implementation is
    separate; this entry point implements Pantanal candidate-period selection.
    """
    source = interval_metrics(points, config)
    denominator = len(points)
    budget = floor(denominator * config.max_affected_point_fraction + 1e-12)
    kinds = tuple(2 if gap > config.max_gap_hours else
                  1 if gap > config.regular_max_hours else 0 for gap in source["gaps"])
    plan = _period_partition_plan(kinds, config.min_subtrajectory_points, budget) if points else ()
    segments, dropped = [], []
    for left, right, keep in plan:
        if keep:
            segments.append(points[left:right])
        else:
            dropped.extend(points[left:right])
    affected = sum(interval_metrics(part, config)["affected_points"] for part in segments)
    assert affected <= budget
    return {"segments": segments, "dropped_points": dropped, "source_metrics": source,
            "hard_run_count": source["hard_gaps"] + bool(points),
            "short_fragment_loss": len(dropped) / denominator if denominator else 0.0,
            "retained_affected_points": affected, "affected_point_denominator": denominator,
            "affected_point_budget": budget,
            "period_affected_point_fraction": affected / denominator if denominator else 0.0}


def thin_observed_records(records: list[dict[str, Any]], config: SamplingConfig | None = None) -> list[dict[str, Any]]:
    """Return chronologically sampled observations from one full record.

    Input timestamps must be datetimes. Records are sorted by timestamp and
    event ID; duplicate timestamps retain the first event in that ordering,
    matching Pantanal selection. Returned dictionaries are the original input
    observations, not generated points. Call separately for each individual.
    This performs cadence selection only; call segment_points afterwards to
    enforce hard gaps, affected-point limits and minimum segment length.
    """
    config = config or SamplingConfig()
    if not records:
        return []
    for record in records:
        if not isinstance(record["timestamp"], datetime):
            raise TypeError("timestamp must already be a datetime.")
    individuals = {record["individual_id"] for record in records if "individual_id" in record}
    if len(individuals) > 1:
        raise ValueError("thin_observed_records requires observations from one individual.")
    ordered = sorted(records, key=lambda record: (record["timestamp"], str(record.get("event_id", ""))))
    unique = list({record["timestamp"]: record for record in reversed(ordered)}.values())
    unique.sort(key=lambda record: record["timestamp"])
    times = [record["timestamp"] for record in unique]
    return _thin_window(unique, times, 0, len(unique), config)
