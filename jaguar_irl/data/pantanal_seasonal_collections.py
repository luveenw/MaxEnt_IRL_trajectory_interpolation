"""Rank bounded alternative covers of seasonal groups and resolve evidence aliases.

Coverage is maximal over the supplied eligible groups (their member union), while
compactness is a deterministic seeded greedy heuristic, not an optimal set cover.
No selected observation is removed here. The member roster records which source
windows may be exported once and which are aliases or overlap accepted evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json


SEASON_PREFIXES = {"winter": "WIN", "spring": "SPR", "summer": "SUM", "autumn": "AUT"}


def _priority(group):
    return (group.get("candidate_list") == "relaxed", int(group.get("rank", 0)), group["group_id"])


def _ids(group):
    return frozenset(int(w["individual_id"]) for w in group["windows"])


def _time(value):
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _seasons(group):
    values = group.get("season_names", [])
    if isinstance(values, str):
        values = [values]
    result = {str(s).lower().removeprefix("austral ") for s in values}
    if result - SEASON_PREFIXES.keys():
        raise ValueError(f"Unknown seasons: {sorted(result - SEASON_PREFIXES.keys())}")
    return result


def _cover(groups, seed=None):
    """Prefer main groups, then ranked relaxed groups; eliminate redundant cover."""
    ordered = []
    for relaxed in (False, True):
        stage = [g for g in groups if (g.get("candidate_list") == "relaxed") == relaxed]
        if seed is not None and any(g is seed for g in stage):
            stage = [seed, *(g for g in stage if g is not seed)]
        ordered.extend(stage)
    chosen, covered = [], set()
    for group in ordered:
        members = _ids(group)
        if members - covered:
            chosen.append(group)
            covered.update(members)
    # Later/worse groups are tested first. Coverage is invariant after each cut.
    for group in sorted(chosen, key=_priority, reverse=True):
        other_ids = set().union(*(_ids(g) for g in chosen if g is not group))
        if _ids(group) <= other_ids:
            chosen.remove(group)
    return sorted(chosen, key=_priority)


def _window_roster(collection_id, groups):
    accepted = defaultdict(list)
    result = []
    for group in sorted(groups, key=_priority):
        for window in sorted(group["windows"], key=lambda w: (int(w["individual_id"]), _time(w["start"]), w["window_id"])):
            ident = int(window["individual_id"])
            start, end = _time(window["start"]), _time(window["end"])
            if end < start:
                raise ValueError(f"Window ends before it starts: {window['window_id']}")
            exact = next((row for row in accepted[ident]
                          if row["window_id"] == window["window_id"] or
                          (_time(row["window_start"]) == start and _time(row["window_end"]) == end)), None)
            overlap = next((row for row in accepted[ident]
                            if start <= _time(row["window_end"]) and end >= _time(row["window_start"])), None)
            canonical = exact or overlap
            status = "duplicate_window" if exact else "overlapping_window" if overlap else "selected"
            trajectory_ids = [str(s["trajectory_id"]) for s in window.get("segments", []) if s.get("trajectory_id")]
            if not trajectory_ids:
                trajectory_ids = list(dict.fromkeys(str(p["trajectory_id"]) for p in window.get("points", []) if p.get("trajectory_id")))
            row = {"collection_id": collection_id, "group_id": group["group_id"],
                   "window_id": window["window_id"], "individual_id": ident,
                   "selection_status": status,
                   "canonical_group_id": canonical["group_id"] if canonical else group["group_id"],
                   "canonical_window_id": canonical["window_id"] if canonical else window["window_id"],
                   "window_start": start.isoformat(), "window_end": end.isoformat(),
                   "selector_subtrajectory_ids": trajectory_ids,
                   "season_names": sorted(_seasons(group))}
            result.append(row)
            if canonical is None:
                accepted[ident].append(row)
    return result


def build_collections(groups, max_collections=7, cohort_ids=(), *, max_seed_groups=128):
    """Return collection summaries and an auditable per-group window roster.

    ``season_names`` attributes a group to any of the four seasons. Each group
    contains windows with original individual/window IDs and inclusive start/end
    bounds. Main groups precede relaxed groups; a relaxed group is eligible only
    if it introduces an animal absent from *all* main groups in that season.

    Seed at most ``max_seed_groups`` groups in rank order, plus the unseeded cover.
    All generated covers include the same attainable union. Keep distinct covers
    ordered by coverage, duplicate memberships, group count, then group ranks.
    Exact or overlapping windows for the same animal receive a single canonical
    map context using main-first group rank. Disjoint windows remain selected.
    """
    if max_collections < 1 or max_seed_groups < 0:
        raise ValueError("Require max_collections >= 1 and max_seed_groups >= 0")
    groups = sorted(list(groups), key=_priority)
    if len({g["group_id"] for g in groups}) != len(groups):
        raise ValueError("Group IDs must be globally unique")
    for group in groups:
        if not group["windows"]:
            raise ValueError("A group must have at least one member window")
        _seasons(group)
    cohort = set(map(int, cohort_ids))
    collections, members = [], []
    for season, prefix in SEASON_PREFIXES.items():
        candidates = [g for g in groups if season in _seasons(g)]
        main_union = set().union(*(_ids(g) for g in candidates if g.get("candidate_list") != "relaxed"))
        eligible = [g for g in candidates if g.get("candidate_list") != "relaxed" or _ids(g) - main_union]
        if not eligible:
            continue
        union = set().union(*(_ids(g) for g in eligible))
        choices = {}
        for seed in [None, *eligible[:max_seed_groups]]:
            cover = _cover(eligible, seed)
            signature = tuple(g["group_id"] for g in cover)
            counts = Counter(i for g in cover for i in _ids(g))
            assert set(counts) == union
            score = (-len(counts), sum(c-1 for c in counts.values()), len(cover), tuple(_priority(g) for g in cover))
            choices[signature] = (score, cover, counts)
        for rank, (_, cover, counts) in enumerate(sorted(choices.values(), key=lambda row: row[0])[:max_collections], 1):
            collection_id = f"{prefix}-C{rank:02d}"
            group_ids = [g["group_id"] for g in cover]
            contexts = [g.get("group_key") or {
                "windows": sorted((int(w["individual_id"]), w["window_id"],
                                   _time(w["start"]).isoformat(), _time(w["end"]).isoformat())
                                  for w in g["windows"]),
                "bounds": g.get("bounds"), "epsg": g.get("epsg"),
                "grid_rows": g.get("grid_rows"), "grid_cols": g.get("grid_cols"),
            } for g in cover]
            identity = {"season": season, "groups": sorted(
                json.dumps(context, sort_keys=True, separators=(",", ":")) for context in contexts)}
            collection_key = "collection_" + hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]
            roster = _window_roster(collection_id, cover)
            selected = [row for row in roster if row["selection_status"] == "selected"]
            collections.append({"collection_id": collection_id, "collection_key": collection_key,
                "season": season, "rank": rank, "group_ids": group_ids,
                "individual_ids": sorted(counts), "n_groups": len(cover), "n_individuals": len(counts),
                "duplicate_individual_ids": sorted(i for i, count in counts.items() if count > 1),
                "n_duplicate_individuals": sum(c > 1 for c in counts.values()),
                "extra_memberships": sum(c-1 for c in counts.values()),
                "membership_counts": dict(sorted(counts.items())),
                "candidate_union_ids": sorted(union), "unrepresented_cohort_ids": sorted(cohort - union),
                "n_selected_windows": len(selected), "n_suppressed_windows": len(roster)-len(selected),
                "coverage_method": "rank_seeded_greedy_union_cover",
                "coverage_is_candidate_union": True, "compactness_is_optimal": False,
                "max_seed_groups": max_seed_groups})
            members.extend(roster)
    return collections, members
