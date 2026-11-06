"""Select observed, approximately two-hour jaguar fixes and seven-day windows.

This module is independent of the legacy IRL/model code. Actual timestamps and
elapsed durations are retained: a tolerated four-hour interval is never relabelled
as a two-hour interval and no missing location is interpolated.

The configurable five-point minimum, 5% short-fragment loss ceiling and seven-day
window are operational screening choices, not literature-derived guarantees of
biological independence or model adequacy. Full-record month counts are descriptive.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from math import ceil
from typing import Any

# Reexport the established temporal API while keeping the implementation shared
# with the general full-record movement processor.
from .movement_temporal import (
    SamplingConfig, _hours, _partition_run, _thin_window,
    interval_metrics, segment_period_points as segment_points, thin_observed_records,
)


@dataclass(frozen=True)
class TemporalConfig(SamplingConfig):
    """All temporal cutoffs; durations are hours unless named otherwise."""

    max_short_fragment_loss: float = 0.05
    short_fragment_warning_fraction: float = 0.05
    week_days: float = 7.0
    min_week_coverage: float = 0.80
    min_week_observed_span_days: float = 6.5
    min_days_per_month: int = 7  # Descriptive month-count definition, never an eligibility rule.

    def __post_init__(self) -> None:
        super().__post_init__()
        for name in ("max_short_fragment_loss",
                     "short_fragment_warning_fraction", "min_week_coverage"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must lie between 0 and 1.")
        if self.week_days <= 0:
            raise ValueError("Require a positive window.")
        if not 0 <= self.min_week_observed_span_days <= self.week_days:
            raise ValueError("Observed span must be between zero and the window duration.")
        if self.min_days_per_month < 1:
            raise ValueError("The descriptive month-count date threshold must be positive.")


def _candidate(records: list[dict[str, Any]], times: list[datetime], start_index: int,
               config: TemporalConfig, *, relax_week_quality: bool = False,
               diagnostics: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
    """Evaluate one complete parent window; only density/span may be relaxed.

    The loss denominator is always the complete observed-fix thinning of this
    configured-duration window, before segmentation. Calendar boundaries do not
    clip the window or relax its quality rules. Its endpoint is inclusive, so an
    exact two-hour schedule contributes both endpoints to the reference count.
    Record endings naturally shorten observed coverage but not the parent window
    or its density reference. No arbitrary shorter endpoints are searched.
    """
    start = times[start_index]
    end = start + timedelta(days=config.week_days)
    crosses_month = (start.year, start.month) != (end.year, end.month)
    crosses_year = start.year != end.year
    stop = bisect_right(times, end, start_index)
    selected = _thin_window(records, times, start_index, stop, config)
    expected = int(round(config.week_days * 24 / config.target_interval_hours)) + 1
    minimum = ceil(expected * config.min_week_coverage)
    selected_days = _hours(selected[0]["timestamp"], selected[-1]["timestamp"]) / 24
    segmented = segment_points(selected, config)
    retained = [p for part in segmented["segments"] for p in part]
    observed_days = (_hours(retained[0]["timestamp"], retained[-1]["timestamp"]) / 24
                     if retained else 0.0)
    strict_reason = (
        "insufficient_selected_fixes" if len(selected) < minimum else
        "insufficient_observed_span" if selected_days < config.min_week_observed_span_days else
        "excess_short_fragment_loss" if segmented["short_fragment_loss"] > config.max_short_fragment_loss + 1e-12 else
        "insufficient_retained_fixes" if len(retained) < minimum else
        "insufficient_retained_span" if observed_days < config.min_week_observed_span_days else
        "accepted"
    )
    protected_failures = []
    if segmented["short_fragment_loss"] > config.max_short_fragment_loss + 1e-12:
        protected_failures.append("excess_short_fragment_loss")
    if not retained:
        protected_failures.append("no_subtrajectory_meets_protected_rules")
    source = segmented["source_metrics"]
    diagnostic = {
        "start": start, "end": end, "window_duration_days": config.week_days,
        "crosses_month_boundary": crosses_month, "crosses_year_boundary": crosses_year,
        "resampled_fixes": len(selected),
        "retained_fixes": len(retained), "dropped_short_fixes": len(segmented["dropped_points"]),
        "short_fragment_loss": segmented["short_fragment_loss"],
        "required_max_short_fragment_loss": config.max_short_fragment_loss,
        "retained_span_days": observed_days, "required_fixes": minimum,
        "required_observed_span_days": config.min_week_observed_span_days,
        "parent_affected_point_fraction": source["affected_point_fraction"],
        "parent_regular_fraction": source["regular_fraction"],
        "max_source_gap_hours": source["max_gap_hours"], "hard_gaps": source["hard_gaps"],
        "n_subtrajectories": len(segmented["segments"]),
        "retained_affected_points": segmented["retained_affected_points"],
        "affected_point_denominator": segmented["affected_point_denominator"],
        "affected_point_budget": segmented["affected_point_budget"],
        "period_affected_point_fraction": segmented["period_affected_point_fraction"],
        "protected_failure_codes": protected_failures,
        "strict_rejection_reason": strict_reason,
    }
    if diagnostics is not None:
        diagnostics.update(diagnostic)
    if not relax_week_quality and strict_reason != "accepted":
        return None, strict_reason
    if protected_failures:
        return None, protected_failures[0]
    observed_start, observed_end = retained[0]["timestamp"], retained[-1]["timestamp"]
    violation_codes, violation_texts = [], []
    if len(retained) < minimum:
        violation_codes.append("insufficient_retained_fixes")
        violation_texts.append(
            f"Density: {len(retained)}/{expected} reference fixes ({len(retained) / expected:.1%}); "
            f"requires at least {minimum} ({config.min_week_coverage:.0%}) in the {config.week_days:g}-day window.")
    if observed_days < config.min_week_observed_span_days:
        violation_codes.append("insufficient_retained_span")
        violation_texts.append(
            f"Observed span: {observed_days:.2f} days; requires at least "
            f"{config.min_week_observed_span_days:g} days within the {config.week_days:g}-day window.")
    individual = records[start_index]["individual_id"]
    window_id = f"jaguar_{individual}_{start:%Y%m%dT%H%M%S}"
    source_dt = {id(point): (None if i == 0 else _hours(selected[i - 1]["timestamp"], point["timestamp"]))
                 for i, point in enumerate(selected)}
    exported, summaries = [], []
    regular_count = interval_count = affected_count = 0
    max_gap = 0.0
    errors = []
    for ordinal, part in enumerate(segmented["segments"], 1):
        trajectory_id = f"{window_id}_s{ordinal:03d}"
        metrics = interval_metrics(part, config)
        regular_count += metrics["regular_intervals"]
        interval_count += len(part) - 1
        affected_count += metrics["affected_points"]
        max_gap = max(max_gap, metrics["max_gap_hours"])
        errors.extend(abs(g - config.target_interval_hours) for g in metrics["gaps"])
        for step, point in enumerate(part):
            exported.append(dict(point, trajectory_id=trajectory_id, window_id=window_id,
                                 step_index=step,
                                 dt_hours=None if step == 0 else _hours(part[step - 1]["timestamp"], point["timestamp"]),
                                 source_dt_hours=source_dt[id(point)],
                                 elapsed_hours=_hours(part[0]["timestamp"], point["timestamp"]),
                                 window_elapsed_hours=_hours(start, point["timestamp"]),
                                 affected_by_gap=step in metrics["affected_indices"]))
        summaries.append({
            "trajectory_id": trajectory_id, "individual_id": individual,
            "start": part[0]["timestamp"], "end": part[-1]["timestamp"],
            "duration_hours": _hours(part[0]["timestamp"], part[-1]["timestamp"]),
            "n_points": len(part), "affected_point_fraction": metrics["affected_point_fraction"],
            "regular_fraction": metrics["regular_fraction"], "max_gap_hours": metrics["max_gap_hours"],
        })
    for summary in summaries:
        summary.update(period_affected_points=affected_count,
                       period_resampled_fixes=len(selected),
                       period_affected_point_fraction=affected_count / len(selected))
    source = segmented["source_metrics"]
    candidate = {
        "individual_id": individual, "window_id": window_id,
        "violation_codes": violation_codes, "violation_text": " ".join(violation_texts),
        "requires_week_relaxation": bool(violation_codes),
        "required_fixes": minimum, "required_coverage_fraction": config.min_week_coverage,
        "required_observed_span_days": config.min_week_observed_span_days,
        "protected_rules_pass": True,
        "year": start.year, "month": start.month,
        "study": records[start_index].get("study", ""),
        "country": records[start_index].get("country", ""),
        "start": start, "end": end, "window_end_exclusive": False,
        "crosses_month_boundary": crosses_month, "crosses_year_boundary": crosses_year,
        "observed_start": observed_start, "observed_end": observed_end,
        "duration_days": observed_days, "window_duration_days": config.week_days,
        "reference_window_duration_days": config.week_days,
        "raw_fixes": stop - start_index, "resampled_fixes": len(selected),
        "selected_fixes": len(retained), "expected_fixes": expected,
        "coverage_fraction": min(1.0, len(retained) / expected),
        "regular_fraction": regular_count / interval_count if interval_count else 1.0,
        "affected_point_fraction": affected_count / len(selected),
        "retained_affected_points": affected_count,
        "affected_point_denominator": len(selected),
        "affected_point_budget": segmented["affected_point_budget"],
        "retained_affected_point_fraction": affected_count / len(retained),
        "affected_point_scope": "candidate_period_before_fragment_removal",
        "parent_affected_point_fraction": source["affected_point_fraction"],
        "parent_regular_fraction": source["regular_fraction"],
        "max_gap_hours": max_gap, "max_within_segment_gap_hours": max_gap,
        "max_source_gap_hours": source["max_gap_hours"], "hard_gaps": source["hard_gaps"],
        "n_subtrajectories": len(summaries),
        "short_fragment_loss": segmented["short_fragment_loss"],
        "short_fragment_warning": segmented["short_fragment_loss"] > config.short_fragment_warning_fraction + 1e-12,
        "dropped_short_fixes": len(segmented["dropped_points"]),
        "dropped_event_ids": [p.get("event_id") for p in segmented["dropped_points"]],
        "max_segment_affected_fraction": max(s["affected_point_fraction"] for s in summaries),
        "mean_interval_error_hours": sum(errors) / len(errors) if errors else 0.0,
        "usable_duration_hours": sum(s["duration_hours"] for s in summaries),
        "points": exported, "segments": summaries,
    }
    return candidate, "accepted"


def _rank(candidate: dict[str, Any]) -> tuple:
    return (candidate["selected_fixes"], -candidate["short_fragment_loss"],
            candidate["regular_fraction"], -candidate["n_subtrajectories"],
            -candidate["mean_interval_error_hours"], -candidate["max_source_gap_hours"])


def find_week_candidates(records: list[dict[str, Any]], config: TemporalConfig | None = None) -> dict[str, Any]:
    """Return main/relaxed weekly candidates and quantitative exclusion evidence.

    Full-study span/month support is advisory. Both candidate collections always
    satisfy the same protected cadence and segmentation rules. Relaxed candidates
    may fail only the configured count or observed-span minimum. Every scan starts
    at an actual fix and evaluates its full configured duration, even across any
    number of calendar months or years. Best candidates remain grouped by the
    observation start year/month; actual retained calendar coverage is a separate
    property. A start month with a main candidate does not also return a weaker
    relaxed candidate. Record-tail candidates retain the full density reference.
    """
    config = config or TemporalConfig()
    by_id: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if not isinstance(record["timestamp"], datetime):
            raise TypeError("timestamp must already be a datetime.")
        by_id[record["individual_id"]].append(record)
    candidates, relaxed_candidates, individual_audit = [], [], []
    for individual in sorted(by_id, key=lambda value: (str(type(value)), value)):
        raw = sorted(by_id[individual], key=lambda r: (r["timestamp"], str(r.get("event_id", ""))))
        unique = list({r["timestamp"]: r for r in reversed(raw)}.values())
        unique.sort(key=lambda r: r["timestamp"])
        times = [r["timestamp"] for r in unique]
        dates_by_month: dict[tuple[int, int], set] = defaultdict(set)
        for when in times:
            dates_by_month[when.year, when.month].add(when.date())
        qualifying_months = [m for m, dates in dates_by_month.items() if len(dates) >= config.min_days_per_month]
        span_days = _hours(times[0], times[-1]) / 24
        # Preserve neutral fields for report/checkpoint compatibility. Full-record
        # span and month availability are descriptive, not quality warnings.
        support = {
            "support_warning": False,
            "support_violation_codes": [],
            "support_violation_text": "",
            "month_summary_min_observed_days": config.min_days_per_month,
        }
        audit = {
            "individual_id": individual, "study": raw[0].get("study", ""),
            "country": raw[0].get("country", ""),
            "n_raw_fixes": len(raw), "n_unique_fixes": len(unique),
            "duplicate_timestamps": len(raw) - len(unique),
            "first_fix": times[0], "last_fix": times[-1],
            "tracking_span_days": span_days, "observed_months": len(dates_by_month),
            "qualifying_months": len(qualifying_months),
            "qualifying_month_labels": [f"{y:04d}-{m:02d}" for y, m in sorted(qualifying_months)],
            "monthly_observed_days": {f"{y:04d}-{m:02d}": len(days) for (y, m), days in sorted(dates_by_month.items())},
            **support, "eligible": True,
            "exclusion_reasons": [], "scanned_windows": 0,
            "scanned_cross_month_windows": 0, "scanned_cross_year_windows": 0,
            "qualifying_windows": 0,
            "relaxed_qualifying_windows": 0, "protected_qualifying_windows": 0,
            "n_candidate_months": 0, "has_candidate": False,
            "n_relaxed_candidate_months": 0, "has_relaxed_candidate": False,
            "rejected_window_reasons": {}, "protected_rejection_reasons": {},
            "best_protected_rejected_window": {},
        }
        best: dict[tuple[int, int], dict[str, Any]] = {}
        relaxed_best: dict[tuple[int, int], dict[str, Any]] = {}
        rejected, protected_rejected = Counter(), Counter()
        best_failed_key = None
        for index, when in enumerate(times):
            audit["scanned_windows"] += 1
            end = when + timedelta(days=config.week_days)
            if (when.year, when.month) != (end.year, end.month):
                audit["scanned_cross_month_windows"] += 1
            if when.year != end.year:
                audit["scanned_cross_year_windows"] += 1
            diagnostic = {}
            candidate, reason = _candidate(unique, times, index, config,
                                            relax_week_quality=True, diagnostics=diagnostic)
            if diagnostic["strict_rejection_reason"] != "accepted":
                rejected[diagnostic["strict_rejection_reason"]] += 1
            if candidate is None:
                protected_rejected.update(diagnostic["protected_failure_codes"])
                failure_key = (diagnostic["retained_fixes"], -diagnostic["short_fragment_loss"],
                               diagnostic["resampled_fixes"], diagnostic["retained_span_days"])
                if best_failed_key is None or failure_key > best_failed_key:
                    best_failed_key = failure_key
                    audit["best_protected_rejected_window"] = diagnostic
                continue
            audit["protected_qualifying_windows"] += 1
            candidate.update(support)
            candidate["months_available"] = len(dates_by_month)
            candidate["qualifying_months"] = len(qualifying_months)
            candidate["individual_first_fix"] = times[0]
            candidate["individual_last_fix"] = times[-1]
            candidate["individual_tracking_span_days"] = span_days
            key = when.year, when.month
            if candidate["requires_week_relaxation"]:
                audit["relaxed_qualifying_windows"] += 1
                if key not in relaxed_best or _rank(candidate) > _rank(relaxed_best[key]):
                    relaxed_best[key] = candidate
            else:
                audit["qualifying_windows"] += 1
                if key not in best or _rank(candidate) > _rank(best[key]):
                    best[key] = candidate
        for key in best:
            relaxed_best.pop(key, None)
        audit["rejected_window_reasons"] = dict(rejected)
        audit["protected_rejection_reasons"] = dict(protected_rejected)
        audit["n_candidate_months"] = len(best)
        audit["has_candidate"] = bool(best)
        audit["n_relaxed_candidate_months"] = len(relaxed_best)
        audit["has_relaxed_candidate"] = bool(relaxed_best)
        if not best:
            audit["exclusion_reasons"].append("no_qualifying_window")
        if not best and not relaxed_best:
            audit["exclusion_reasons"].append("no_window_satisfies_protected_rules")
        evidence = audit["best_protected_rejected_window"]
        if not best and not relaxed_best and evidence:
            audit["protected_exclusion_text"] = (
                f"No scanned parent window ({config.week_days:g} days) satisfies "
                f"protected cadence/segmentation. Best rejected window "
                f"{evidence['start']:%Y-%m-%d %H:%M} to {evidence['end']:%Y-%m-%d %H:%M}: "
                f"{evidence['retained_fixes']}/{evidence['resampled_fixes']} sampled fixes can be retained; "
                f"{evidence['short_fragment_loss']:.1%} short-fragment loss exceeds the "
                f"{config.max_short_fragment_loss:.0%} ceiling. Before splitting, "
                f"{evidence['parent_affected_point_fraction']:.1%} of points touch "
                f">{config.regular_max_hours:g}–{config.max_gap_hours:g}h intervals; "
                f"{evidence['hard_gaps']} gaps exceed {config.max_gap_hours:g}h "
                f"(maximum {evidence['max_source_gap_hours']:.2f}h). Retained subtrajectories must "
                f"have at least {config.min_subtrajectory_points} points. Retained irregular-gap endpoints "
                f"across all segments must not exceed {config.max_affected_point_fraction:.0%} of "
                f"all {evidence['resampled_fixes']} resampled parent-window points.")
        else:
            audit["protected_exclusion_text"] = ""
        candidates.extend(best[key] for key in sorted(best))
        relaxed_candidates.extend(relaxed_best[key] for key in sorted(relaxed_best))
        individual_audit.append(audit)
    return {"candidates": candidates, "relaxed_candidates": relaxed_candidates,
            "individuals": individual_audit, "config": asdict(config)}
