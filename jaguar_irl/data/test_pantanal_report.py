"""Report contracts: ranks, flags, escaped evidence and collapsed ranking tails."""

from .pantanal_report import candidate_calendar, _rankings_section, _violation_text


def test_section_facts_show_sex_counts_and_explicit_unknowns():
    from .pantanal_report import _group_facts
    html = _group_facts({"n_individuals": 7, "n_males": 3, "n_females": 4, "n_unknown_sex": 0})
    assert '<strong>7</strong> individuals ' in html
    assert '(3M / 4F)' in html
    assert 'unknown' not in html
    html = _group_facts({"n_individuals": 3, "n_males": 1, "n_females": 1, "n_unknown_sex": 1})
    assert '(1M / 1F / 1 unknown)' in html


def group(rank, *, flagged=False, kind="main"):
    return {"group_id": f"{'R' if kind == 'relaxed' else 'G'}{rank:02d}",
            "rank": rank, "overall_rank": 99 - rank, "month": 5, "n_individuals": 2,
            "years": "2014;2015", "ids": "12;13", "candidate_list": kind,
            "has_violations": flagged, "flagged_individual_ids": "12" if flagged else "",
            "violation_text": "ID 12: Density: 60 < 68" if flagged else ""}


def test_rankings_jaguar_ids_cell_contains_counts_and_ids_in_both_lists():
    for kind in ("main", "relaxed"):
        candidate = dict(group(1, kind=kind), n_males=1, n_females=1, n_unknown_sex=0)
        html = _rankings_section([candidate], {candidate["group_id"]: [
            {"retained_fixes": 75}, {"retained_fixes": 85}]}, f"{kind}-rankings", kind)
        assert '<th scope="col">Jaguar IDs</th>' in html
        assert '<strong>2</strong> individuals' in html
        assert '(1M / 1F)' in html
        assert 'IDs: 12;13' in html


def test_calendar_flag_priority_preserves_rank_within_each_category():
    html = candidate_calendar([group(2, flagged=True, kind="relaxed"),
                              group(2, flagged=True), group(4),
                              group(1, kind="relaxed"), group(1, flagged=True), group(3)])
    links = [html.index(f'href="#{ident}"') for ident in ["G03", "G04", "G01", "G02", "R01", "R02"]]
    assert links == sorted(links)
    assert "G01 · 2 individuals · 🌎 #1" in html
    assert "#98" not in html  # Legacy overall_rank never leaks into the one-rank UI.
    assert 'class="flagged"' in html
    assert "IDs 12" in html
    assert "Density: 60 &lt; 68" in html
    assert "2014, 2015" in html


def test_each_rankings_list_keeps_only_first_seven_outside_closed_details():
    for kind in ("main", "relaxed"):
        groups = [group(n, flagged=n % 2 == 0, kind=kind) for n in range(1, 10)]
        members = {g["group_id"]: [{"retained_fixes": 68}, {"retained_fixes": 75}] for g in groups}
        html = _rankings_section(groups, members, f"{kind}-rankings", kind)
        visible, hidden = html.split('<details class="ranking-tail">')
        prefix = "G" if kind == "main" else "R"
        assert f'href="#{prefix}07"' in visible
        assert f'href="#{prefix}08"' not in visible
        assert f'href="#{prefix}08"' in hidden
        assert f'href="#{prefix}09"' in hidden
        assert " open" not in hidden
        assert "Status" not in html
        assert "Overall rank" not in html
        assert "Density: 60 &lt; 68" in html
        assert '<th scope="col">Flags</th>' in html


def test_distinct_calendar_ids_and_explanations_are_preserved():
    html = candidate_calendar([group(1, flagged=True, kind="relaxed")],
                              nav_id="relaxed-candidate-navigation", title="Relaxed")
    assert 'id="relaxed-candidate-navigation-month-5"' in html
    assert 'class="relaxed flagged"' in html
    assert _violation_text({"violation_text": "support", "support_violation_text": "support"}) == "support"


def test_cross_boundary_navigation_repeats_links_without_inventing_observed_months():
    import re
    from .pantanal_report import _group_facts

    candidate = dict(group(1), n_individuals=3, month=6, years="1999",
        observed_year_months=["2014-12", "2015-01", "2015-02", "2017-02", "2017-12"],
        month_coverage=[
            {"month":12, "years":[2014,2017], "individual_ids":[12,13], "n_individuals":2},
            {"month":1, "years":[2015], "individual_ids":[12], "n_individuals":1},
            {"month":2, "years":[2015,2017], "individual_ids":[13,14], "n_individuals":2},
        ])
    html = candidate_calendar([candidate])
    months = {int(number): content for number, content in re.findall(
        r'<section class="calendar-month" data-month="(\d+)".*?>(.*?)</section>', html)}
    assert html.count('href="#G01"') == 3
    assert 'href="#G01"' not in months[6]  # Start month is not observed coverage.
    assert 'href="#G01"' not in months[3]  # No fabricated months between sparse records.
    assert 'January data: 1/3 individuals' in months[1]
    assert 'Years: 2015</span>' in months[1]
    assert 'December data: 2/3 individuals' in months[12]
    assert 'Years: 2014, 2017</span>' in months[12]
    assert 'February data: 2/3 individuals' in months[2]
    assert 'Years: 2015, 2017</span>' in months[2]
    assert 'Dec 2014–Feb 2015; Feb 2017; Dec 2017' in html
    assert '<strong>2014, 2015, 2017</strong>' in _group_facts(candidate)
    assert '1999' not in _group_facts(candidate)


def test_period_labels_support_long_spans_and_preserve_sparse_year_months():
    from .pantanal_report import _period_labels

    assert _period_labels({"observed_year_months":["2014-12","2015-01"]}) == ["Dec 2014–Jan 2015"]
    assert _period_labels({"observed_year_months":["2014-12","2015-01","2015-02","2015-03"]}) == ["Dec 2014–Mar 2015"]
    assert _period_labels({"observed_year_months":["2015-01","2015-02","2015-03","2015-04"]}) == ["Jan–Apr 2015"]
    assert _period_labels({"observed_year_months":["2014-12","2015-02","2016-12"]}) == ["Dec 2014", "Feb 2015", "Dec 2016"]
    assert _period_labels({"observed_year_months":[]}) == []


def test_multiple_navigation_months_do_not_duplicate_ranking_rows():
    candidate = dict(group(1), observed_year_months=["2014-12","2015-01","2015-02"])
    members = {"G01":[{"retained_fixes":68},{"retained_fixes":75}]}
    nav = candidate_calendar([candidate])
    ranking = _rankings_section([candidate], members, "main-rankings", "Main")
    assert nav.count('href="#G01"') == 3
    assert ranking.count('href="#G01"') == 2  # One rank link and one group link in one row.
    assert ranking.count('<tr class="top-seven">') == 1
    assert '<th scope="col">Observed periods</th>' in ranking
    assert 'Dec 2014–Feb 2015' in ranking
    assert '<th scope="col">Month</th>' not in ranking
    assert '<th scope="col">Years</th>' not in ranking
