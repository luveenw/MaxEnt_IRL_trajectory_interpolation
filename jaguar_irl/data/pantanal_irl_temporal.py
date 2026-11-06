"""Export-only policies; the frozen selector's temporal rules are unchanged."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from math import floor, isfinite


@dataclass(frozen=True)
class ExportConfig:
    variant: str = "both"
    source_gap_hours: float = 4.0
    min_source_segment_points: int = 5
    min_comparison_segment_points: int = 5
    target_interval_hours: float = 2.0
    regular_min_hours: float = 1.5
    regular_max_hours: float = 2.5
    max_comparison_gap_hours: float = 4.0
    max_affected_fraction: float = 0.20
    min_final_retention_fraction: float = 0.0  # Zero disables the ratio gate; nonempty evidence is still required.
    behavior_selection: str = "all_retained"
    rasterization: str = "bresenham_e2_ge_dy_le_dx_v1"

    def __post_init__(self):
        if self.variant not in ("fine", "two_hour", "both"):
            raise ValueError("variant must be fine, two_hour or both")
        for value in asdict(self).values():
            if isinstance(value, (float, int)) and not isfinite(value):
                raise ValueError("Export thresholds must be finite")
        if not 0 < self.regular_min_hours <= self.target_interval_hours <= self.regular_max_hours <= self.max_comparison_gap_hours:
            raise ValueError("Invalid comparison interval bounds")
        if self.source_gap_hours <= 0:
            raise ValueError("Source gap must be positive")
        if min(self.min_source_segment_points, self.min_comparison_segment_points) < 1:
            raise ValueError("Observation minima must be positive")
        if not 0 <= self.max_affected_fraction <= 1 or not 0 <= self.min_final_retention_fraction <= 1:
            raise ValueError("Fractions must be within [0, 1]")
        if self.behavior_selection != "all_retained" or self.rasterization != "bresenham_e2_ge_dy_le_dx_v1":
            raise ValueError("Unsupported behavioral selection or rasterization policy")


def hours(a, b):
    return (b["timestamp"] - a["timestamp"]).total_seconds() / 3600


def source_bouts(events, config):
    """Tag changes are boundaries, not proof of biological trips/deployments."""
    parts = []
    for point in events:
        prior = parts[-1][-1] if parts else None
        if prior is None or hours(prior, point) > config.source_gap_hours or prior.get("tag_id") != point.get("tag_id"):
            parts.append([])
        parts[-1].append(point)
    return parts


def thin_bout(events, config):
    """Observed fixes only, closest to +2 h; retain first after a hard gap."""
    if not events:
        return []
    result, current = [events[0]], 0
    while current + 1 < len(events):
        at = current + 1
        while at < len(events) and hours(events[current], events[at]) < config.regular_min_hours:
            at += 1
        if at == len(events):
            break
        choices = []
        while at < len(events) and hours(events[current], events[at]) <= config.regular_max_hours:
            choices.append(at)
            at += 1
        if choices:
            current = min(choices, key=lambda i: (abs(hours(events[current], events[i]) - config.target_interval_hours),
                                                 events[i]["timestamp"], events[i]["event_id"]))
        else:
            current = at
        result.append(events[current])
    return result


def affected_count(kinds):
    indices = set()
    for i, kind in enumerate(kinds):
        if kind == 1:
            indices.update((i, i + 1))
    return len(indices)


@lru_cache(maxsize=256)
def comparison_partition(kinds, minimum, budget):
    """Exact optimization: F, fewer kept blocks, fewer cuts, earliest cuts.

    Edges: 0 regular, 1 optional cut, 2 mandatory cut. Blocks shorter than the
    observation minimum are retained in the audit but excluded from F. A/M is
    pooled across the entire window, never reset at a hard gap.
    """
    n = len(kinds) + 1
    boundaries = [0] + [i + 1 for i, k in enumerate(kinds) if k] + [n]
    forced = [0] + [i + 1 for i, k in enumerate(kinds) if k == 2] + [n]
    base = [(a, b, b - a >= minimum) for a, b in zip(forced, forced[1:])]
    if sum(affected_count(kinds[a:b-1]) for a, b, keep in base if keep) <= budget:
        return tuple(base)
    # state=(F, kept blocks, total blocks, cut positions, complete partition)
    states = [{0: (0, 0, 0, (), ())}] + [{} for _ in boundaries[1:]]
    last_hard = 0

    def better(a, b):
        return ((a[0], -a[1], -a[2]) > (b[0], -b[1], -b[2]) or
                ((a[0], -a[1], -a[2]) == (b[0], -b[1], -b[2]) and a[3] < b[3]))

    for end_i in range(1, len(boundaries)):
        right = boundaries[end_i]
        for start_i in range(end_i):
            left = boundaries[start_i]
            if left < last_hard:
                continue
            keep = right - left >= minimum
            cost = affected_count(kinds[left:right-1]) if keep else 0
            for used, old in states[start_i].items():
                if used + cost > budget:
                    continue
                new = (old[0] + (right-left if keep else 0), old[1] + int(keep), old[2] + 1,
                       old[3] + ((right,) if right < n else ()), old[4] + ((left, right, keep),))
                prior = states[end_i].get(used + cost)
                if prior is None or better(new, prior):
                    states[end_i][used + cost] = new
        if right < n and kinds[right-1] == 2:
            last_hard = right
    best = None
    for state in states[-1].values():
        if best is None or better(state, best):
            best = state
    if best is None:
        raise ValueError("No partition satisfies the configured endpoint budget/count floor")
    return best[4]


def build_tracks(events, config):
    bouts = source_bouts(events, config)
    fine = [{"events": b, "source_bout": i, "retained": len(b) >= config.min_source_segment_points,
             "reason": "" if len(b) >= config.min_source_segment_points else "short_source_fragment"}
            for i, b in enumerate(bouts)]
    selected, bout_ids = [], []
    for i, bout in enumerate(bouts):
        sampled = thin_bout(bout, config)
        selected.extend(sampled)
        bout_ids.extend([i] * len(sampled))
    kinds = tuple(2 if bout_ids[i] != bout_ids[i+1] or hours(a, b) > config.max_comparison_gap_hours
                  else 1 if hours(a, b) > config.regular_max_hours else 0
                  for i, (a, b) in enumerate(zip(selected, selected[1:])))
    m = len(selected)
    budget = floor(config.max_affected_fraction * m + 1e-12)
    plan = comparison_partition(kinds, config.min_comparison_segment_points, budget) if m else ()
    comparison = [{"events": selected[a:b], "source_bout": bout_ids[a], "retained": keep,
                   "reason": "" if keep else "short_comparison_fragment"}
                  for a, b, keep in plan]
    f = sum(b-a for a, b, keep in plan if keep)
    affected = sum(affected_count(kinds[a:b-1]) for a, b, keep in plan if keep)
    eligible = m > 0 and f > 0 and f/m + 1e-12 >= config.min_final_retention_fraction
    cuts = [{"from_event_key": selected[a-1]["source_event_key"],
             "to_event_key": selected[a]["source_event_key"],
             "gap_hours": hours(selected[a-1], selected[a]),
             "reason": "hard_boundary" if kinds[a-1] == 2 else "endpoint_budget"}
            for a, _, _ in plan if a]
    return {"fine": fine, "two_hour": comparison, "selected": selected, "cuts": cuts,
            "comparison_eligible": eligible, "M": m, "F": f, "A": affected,
            "affected_budget": budget, "final_retention_fraction": f/m if m else None,
            "affected_point_fraction": affected/m if m else None,
            "dropped_fragment_count": sum(not part["retained"] for part in comparison),
            "dropped_fragment_points": m-f}
