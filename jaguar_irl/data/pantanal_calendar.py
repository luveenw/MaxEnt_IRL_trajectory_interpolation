"""Calendar coverage of retained observations, independent of window length.

Coverage is computed from observed timestamps, never from the envelope between
the earliest and latest dates. It therefore supports multi-month windows and
multiple disjoint windows without inventing coverage in the intervening months.
Repeated observations from overlapping windows are counted once per animal and
timestamp; individuals are also counted once within each calendar bin.
"""

from collections import defaultdict
from datetime import datetime


CALENDAR_FIELDS = (
    "observed_months", "observed_years", "observed_year_months",
    "calendar_coverage", "month_coverage", "same_year", "shared_years",
)


def summarize_calendar(points):
    """Return actual month/year coverage for any iterable of retained fixes.

    ``calendar_coverage`` has one row per observed year-month. ``month_coverage``
    pools the same calendar month across years for the January–December index.
    ``same_year`` requires all observations to fall in a single year;
    ``shared_years`` is the intersection of years observed for each individual.
    Dates retain the input clock convention, with no inferred time-zone change.
    """
    unique = set()
    by_period, by_month, years_by_individual = defaultdict(list), defaultdict(list), defaultdict(set)
    for point in points:
        when = point["timestamp"]
        if isinstance(when, str):
            when = datetime.fromisoformat(when)
        if not isinstance(when, datetime):
            raise TypeError("Calendar coverage requires datetime or ISO timestamps")
        ident = int(point["individual_id"])
        key = ident, when
        if key in unique:
            continue
        unique.add(key)
        by_period[when.year, when.month].append(key)
        by_month[when.month].append(key)
        years_by_individual[ident].add(when.year)

    calendar_coverage = []
    for (year, month), rows in sorted(by_period.items()):
        individuals = sorted({ident for ident, _ in rows})
        timestamps = [when for _, when in rows]
        calendar_coverage.append({
            "year": year, "month": month, "year_month": f"{year:04d}-{month:02d}",
            "individual_ids": individuals, "n_individuals": len(individuals),
            "n_fixes": len(rows), "first_fix": min(timestamps), "last_fix": max(timestamps),
            "observed_dates": len({when.date() for when in timestamps}),
        })
    month_coverage = []
    for month, rows in sorted(by_month.items()):
        individuals = sorted({ident for ident, _ in rows})
        years = sorted({when.year for _, when in rows})
        month_coverage.append({
            "month": month, "years": years,
            "year_months": [f"{year:04d}-{month:02d}" for year in years],
            "individual_ids": individuals, "n_individuals": len(individuals),
            "n_fixes": len(rows),
        })
    observed_years = sorted({year for year, _ in by_period})
    shared_years = (sorted(set.intersection(*years_by_individual.values()))
                    if years_by_individual else [])
    return {
        "observed_months": sorted(by_month), "observed_years": observed_years,
        "observed_year_months": [row["year_month"] for row in calendar_coverage],
        "calendar_coverage": calendar_coverage, "month_coverage": month_coverage,
        "same_year": len(observed_years) == 1, "shared_years": shared_years,
    }
