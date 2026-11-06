"""Coverage follows observations across windows, years, and sparse months."""

from datetime import datetime

from .pantanal_calendar import summarize_calendar


def point(ident, date):
    return {"individual_id":ident, "timestamp":datetime.fromisoformat(date)}


def test_cross_year_counts_distinct_members_and_actual_year_coverage():
    rows = [point(1,"2014-12-31T23:00"), point(1,"2015-01-01T01:00"),
            point(2,"2015-01-02T12:00"), point(2,"2016-01-02T12:00")]
    result = summarize_calendar(rows)
    assert result["observed_year_months"] == ["2014-12","2015-01","2016-01"]
    assert result["observed_years"] == [2014,2015,2016]
    assert result["same_year"] is False
    assert result["shared_years"] == [2015]
    january, december = result["month_coverage"]
    assert january["individual_ids"] == [1,2]
    assert january["n_individuals"] == 2
    assert january["n_fixes"] == 3
    assert january["years"] == [2015,2016]
    assert december["individual_ids"] == [1]
    assert december["years"] == [2014]


def test_disjoint_windows_do_not_invent_coverage_or_count_overlapping_fixes_twice():
    rows = [point(12,"2013-01-02T12:00"), point(12,"2013-01-02T12:00"),
            point(12,"2013-03-02T12:00"), point(12,"2013-04-02T12:00"),
            point(13,"2013-04-02T12:00"), point(12,"2014-09-02T12:00")]
    result = summarize_calendar(rows)
    assert result["observed_months"] == [1,3,4,9]
    assert result["observed_year_months"] == ["2013-01","2013-03","2013-04","2014-09"]
    assert sum(c["n_fixes"] for c in result["calendar_coverage"]) == 5
    assert result["calendar_coverage"][2]["n_individuals"] == 2
    assert result["calendar_coverage"][2]["observed_dates"] == 1


def test_empty_and_serialized_point_inputs():
    assert summarize_calendar([])["same_year"] is False
    assert summarize_calendar([])["shared_years"] == []
    result = summarize_calendar([{"individual_id":"12","timestamp":"2015-04-02 12:00:00"}])
    assert result["same_year"] is True
    assert result["shared_years"] == [2015]
    assert result["calendar_coverage"][0]["individual_ids"] == [12]
