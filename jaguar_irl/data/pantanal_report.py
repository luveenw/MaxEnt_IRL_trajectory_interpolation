"""Render the Pantanal selection result as an offline report and scientific figures.

``write_report(output_dir, result)`` consumes the plain dictionaries produced by
the data-selection pipeline. It neither changes selections nor imports any model
or training code. The HTML embeds its figures so that index.html can be copied
on its own; the PNG figures are also kept in images/ for reuse.
"""

from __future__ import annotations

import base64
from collections import defaultdict
from datetime import datetime
from html import escape
import json
import math
import os
from pathlib import Path
import re
import textwrap
from typing import Mapping

from .pantanal_metric_notes import METRIC_NOTES_HTML


MONTHS = ("", "January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December")

CALENDAR_CSS = """
.candidate-calendar{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;align-items:start}
.calendar-month{border:1px solid #cddbdd;border-radius:8px;overflow:hidden;background:#fff}
.calendar-month h3{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:0;padding:11px 12px;background:#eef3f4;font-size:16px}
.month-count{font-size:11px;font-weight:400;color:#52636c;white-space:nowrap}
.month-candidates{list-style:none;margin:0;padding:8px;display:grid;gap:6px;max-height:25rem;overflow-y:auto}
.month-candidates a{display:block;padding:8px;border:1px solid #b5d7d3;border-radius:4px;background:transparent;--selected-background:#f1f7f6;text-decoration:none;font-size:12px;line-height:1.5;font-weight:400}
.month-candidates a[aria-current="location"]{font-weight:700;background:var(--selected-background)}
.month-candidates a:hover,.month-candidates a:focus-visible{outline:2px solid #327d8a;outline-offset:1px}
.month-candidates a.top-seven{--selected-background:#e8f3ef;border-color:#80b8aa}
.month-candidates a.flagged{--selected-background:#fff4df;border-color:#d8af6c;color:#795116}
.month-candidates a.relaxed{--selected-background:#f9eaf0;border-color:#c894ab;color:#7d3656}
.candidate-years,.candidate-flag,.candidate-periods,.candidate-members{display:block;font-size:11px;font-weight:inherit;margin-top:2px}
.candidate-years,.candidate-periods,.candidate-members{color:#52636c}.candidate-flag{color:inherit}
.calendar-empty{padding:4px 8px;color:#52636c;font-size:12px}
.group-title{display:flex;align-items:center;flex-wrap:wrap;gap:9px}
.rank-pill,.month-chip{display:inline-block;border-radius:4px;padding:3px 8px;font-size:13px;background:#e5f2ef;color:#205a50}
.rank-pill{font-variant-numeric:tabular-nums;white-space:nowrap;background:#edf2f6;color:#445d6c}.rank-pill.top-seven{background:#e5f2ef;color:#205a50}
.rank-pill.flagged{background:#fff0ce;color:#795116}.rank-pill.relaxed{background:#f6e1eb;color:#7d3656}
.month-chip{font-size:12px;font-weight:600}.period-list{display:grid;gap:3px;min-width:140px}.period-list span{white-space:nowrap}.group-title .rank-context{font-size:12px;color:#52636c;font-weight:400}
.fact-detail{font-size:11px}
.flag-note{border-left:4px solid #d8af6c;background:#fff8eb;padding:13px 16px;border-radius:0 6px 6px 0}
.flag-note.relaxed{border-color:#c894ab;background:#fdf1f6}.clear-note{color:#52636c}
.ranking-section{scroll-margin-top:16px}.ranking-tail summary{color:#146474}.ranking-tail{margin-top:-10px}
.overview tr.flagged td{background:#fff9ee}.overview tr.relaxed td{background:#fdf3f7}
.overview .rank-pill{font-size:12px}.overview .flag-cell{min-width:220px;max-width:420px;font-size:12px}
.flag-list{margin:0;padding-left:18px}.flag-list li+li{margin-top:4px}
.list-heading{margin-top:44px;padding:16px 20px;background:#f0f5f5;border-left:4px solid #7daea5;border-radius:4px}
.list-heading.relaxed{background:#fcf0f5;border-color:#c894ab}.list-heading h2{margin:0 0 8px}
.float-nav{position:fixed;right:22px;bottom:22px;z-index:20;display:flex;flex-direction:column-reverse;align-items:flex-end;gap:8px}
.float-nav button{border:1px solid #85ada6;border-radius:50%;width:48px;height:48px;background:#e5f2ef;color:#205a50;font-size:22px;cursor:pointer;box-shadow:0 3px 14px #203b3b26}
.float-nav-links{display:flex;flex-direction:column;align-items:flex-end;gap:7px;opacity:0;visibility:hidden;transform:translateY(12px);transition:opacity .16s,transform .16s,visibility .16s}
.float-nav:hover .float-nav-links,.float-nav:focus-within .float-nav-links,.float-nav.is-open .float-nav-links{opacity:1;visibility:visible;transform:translateY(0)}
.float-nav-links a{display:block;border:1px solid #b9d2cc;border-radius:7px;padding:8px 12px;background:#f1f8f6;text-decoration:none;font-size:13px;box-shadow:0 2px 8px #203b3b14}
.float-nav a:focus-visible,.float-nav button:focus-visible{outline:2px solid #327d8a;outline-offset:3px}
@media(prefers-reduced-motion:reduce){.float-nav-links{transition:none}}
@media(max-width:1000px){.candidate-calendar{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.candidate-calendar{grid-template-columns:1fr}.float-nav{right:12px;bottom:12px}}
@media print{.candidate-calendar{grid-template-columns:repeat(3,minmax(0,1fr))}.month-candidates{max-height:none;overflow:visible}.calendar-month{break-inside:avoid}.float-nav{display:none}}
"""

CALENDAR_SCRIPT = """<script>
(function(){
  const links = Array.from(document.querySelectorAll('.month-candidates a'));
  const sections = Array.from(document.querySelectorAll('section.group'));
  const ids = new Set(sections.map(function(section){return section.id;}));
  const select = function(id){
    links.forEach(function(link){
      if(link.getAttribute('href') === '#' + id){link.setAttribute('aria-current','location');}
      else{link.removeAttribute('aria-current');}
    });
  };
  let pending = false;
  const update = function(){
    pending = false;
    let active = '';
    const marker = Math.min(150, window.innerHeight / 3);
    for(const section of sections){
      const rect = section.getBoundingClientRect();
      if(rect.top <= marker && rect.bottom > marker){active = section.id;break;}
      if(rect.top > marker && rect.top < window.innerHeight / 2){active = section.id;break;}
    }
    select(active);
  };
  const schedule = function(){if(!pending){pending=true;window.requestAnimationFrame(update);}};
  const fromHash = function(){
    const id = window.location.hash.slice(1);
    if(ids.has(id)){select(id);}else{schedule();}
  };
  links.forEach(function(link){link.addEventListener('click',function(){
    select(link.getAttribute('href').slice(1));
  });});
  window.addEventListener('hashchange',fromHash);
  window.addEventListener('scroll',schedule,{passive:true});
  window.addEventListener('resize',schedule);
  fromHash();
})();
</script>"""


def _true(value):
    return str(value).lower() in ("true", "1")


def _flagged(group):
    return (_true(group.get("has_violations")) or _true(group.get("support_warning"))
            or bool(group.get("violation_codes")) or bool(group.get("violation_text")))


def _group_style(group):
    if group.get("candidate_list") == "relaxed":
        return "relaxed flagged"
    if _flagged(group):
        return "flagged"
    return "top-seven" if int(group.get("rank") or 0) <= 7 else ""


def _violation_text(row):
    combined = str(row.get("violation_text") or "").strip()
    support = str(row.get("support_violation_text") or "").strip()
    if support and support not in combined:
        combined = f"{combined} {support}".strip()
    return combined


def _observed_periods(row):
    """Return represented year-months; never expand a first/last date envelope."""
    values = row.get("observed_year_months")
    if values is None and "calendar_coverage" in row:
        values = [item["year_month"] for item in row["calendar_coverage"]]
    if values is None:
        # Compatibility for older single-month exports and small fixtures.
        years = row.get("observed_years")
        if years is None:
            years = str(row.get("years") or row.get("year") or "").split(";")
        month = row.get("month")
        values = [f"{int(year):04d}-{int(month):02d}" for year in years if year and month]
    periods = set()
    for value in values:
        year, month = map(int, str(value).split("-"))
        if not 1 <= month <= 12:
            raise ValueError(f"Invalid observed month: {value}")
        periods.add((year, month))
    return sorted(periods)


def _period_labels(row):
    """Compress consecutive represented months, preserving gaps and year changes."""
    periods = _observed_periods(row)
    runs = []
    for period in periods:
        if runs and period[0] * 12 + period[1] == runs[-1][-1][0] * 12 + runs[-1][-1][1] + 1:
            runs[-1].append(period)
        else:
            runs.append([period])
    labels = []
    for run in runs:
        first, last = run[0], run[-1]
        start_month, end_month = MONTHS[first[1]][:3], MONTHS[last[1]][:3]
        if first == last:
            labels.append(f"{start_month} {first[0]}")
        elif first[0] == last[0]:
            labels.append(f"{start_month}–{end_month} {first[0]}")
        else:
            labels.append(f"{start_month} {first[0]}–{end_month} {last[0]}")
    return labels


def _period_label(row):
    return "; ".join(_period_labels(row)) or "No retained observations"


def _navigation_months(group):
    """Month-specific contributor counts and years, from retained-point metadata."""
    if "month_coverage" in group:
        return sorted(group["month_coverage"], key=lambda item: int(item["month"]))
    periods = _observed_periods(group)
    return [{"month": month, "years": sorted({year for year, m in periods if m == month}),
             "n_individuals": group.get("n_individuals", 0)}
            for month in sorted({month for _, month in periods})]


def candidate_calendar(groups, *, nav_id="candidate-navigation", title="🗓️ All candidates by month"):
    """Repeat links across observed months while retaining one group identity."""
    by_month = defaultdict(list)
    for group in groups:
        seen = set()
        for coverage in _navigation_months(group):
            month = int(coverage["month"])
            if not 1 <= month <= 12:
                raise ValueError(f"Invalid candidate month: {month}")
            if month not in seen:
                by_month[month].append((group, coverage))
                seen.add(month)
    parts = [f'<nav id="{escape(nav_id, quote=True)}" aria-label="{escape(title, quote=True)}">',
             f'<h2>{escape(title)}</h2>',
             '<p>A group appears in every calendar month containing retained observations. '
             'Repeated links lead to the same group section; monthly counts overlap, while report totals count unique groups. '
             'Each link reports the contributing individuals and observation years for that month. '
             'Within each month, unflagged main groups appear first, then flagged main groups, then relaxed groups, '
             'with rank order within each category. The 🌎 number is the rank in the main (G) or relaxed (R) list. '
             'Green marks the first seven unflagged ranks; amber marks main-list flags; rose marks relaxed groups.</p>',
             '<div class="candidate-calendar">']
    for month in range(1, 13):
        candidates = sorted(by_month[month], key=lambda item: (
            2 if item[0].get("candidate_list") == "relaxed" else int(_flagged(item[0])),
            int(item[0].get("rank") or 0)))
        count = len(candidates)
        heading_id = f"{nav_id}-month-{month}"
        parts.append(f'<section class="calendar-month" data-month="{month}" aria-labelledby="{heading_id}">'
                     f'<h3 id="{heading_id}">{MONTHS[month]}'
                     f'<span class="month-count">{count} {"group" if count == 1 else "groups"}</span></h3>'
                     '<ul class="month-candidates">')
        for group, coverage in candidates:
            label = (f"{group['group_id']} · {group['n_individuals']} individuals"
                     f" · 🌎 #{group.get('rank', '—')}")
            years = ", ".join(map(str, sorted(set(coverage.get("years", [])))))
            flag = ""
            if _flagged(group):
                ids = str(group.get("flagged_individual_ids") or "").replace(";", ", ")
                label_flag = "⚑ Review flags" + (f" · IDs {ids}" if ids else "")
                flag = f'<span class="candidate-flag">{escape(label_flag)}</span>'
            parts.append(f'<li><a class="{_group_style(group)}" '
                         f'href="#{escape(_slug(group["group_id"]), quote=True)}" '
                         f'title="{escape(_violation_text(group), quote=True)}">{escape(label)}'
                         f'<span class="candidate-periods">🗓️ {escape(_period_label(group))}</span>'
                         f'<span class="candidate-members">{MONTHS[month]} data: '
                         f'{escape(_text(coverage.get("n_individuals")))}/{escape(_text(group["n_individuals"]))} individuals</span>'
                         f'<span class="candidate-years">Years: {escape(years)}</span>{flag}</a></li>')
        if not candidates:
            parts.append('<li class="calendar-empty">No candidate groups</li>')
        parts.append('</ul></section>')
    parts.append('</div></nav>')
    return "".join(parts)


def _text(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _num(value, digits=1) -> str:
    try:
        number = float(value)
        return f"{number:,.{digits}f}" if math.isfinite(number) else "—"
    except (TypeError, ValueError):
        return "—"


def _pct(value, digits=1) -> str:
    try:
        return _num(float(value) * 100, digits) + "%"
    except (TypeError, ValueError):
        return "—"


def _date(value) -> str:
    if value is None:
        return "—"
    try:
        when = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        return when.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(value)


def _month(value) -> str:
    try:
        return MONTHS[int(value)]
    except (IndexError, TypeError, ValueError):
        return _text(value)


def _slug(value) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", str(value)).strip("-") or "group"


def _individual_count_html(group, member_count=0):
    count = int(group.get("n_individuals", member_count))
    males, females = int(group.get("n_males", 0)), int(group.get("n_females", 0))
    unknown = int(group.get("n_unknown_sex", count - males - females))
    sex_counts = f"{males}M / {females}F" + (f" / {unknown} unknown" if unknown else "")
    sex_label = f"{males} male, {females} female" + (f", {unknown} unknown sex" if unknown else "")
    return (f'<strong>{count}</strong> individuals '
            f'<span class="sex-counts" aria-label="{sex_label}">({sex_counts})</span>')


def _sex_marker(sex):
    """Use the same shape/label for fixes and their individual legend handle."""
    return {"male": ("^", "M"), "female": ("o", "F")}.get(str(sex).lower(), ("x", "?"))


def _group_facts(group, member_count=0):
    years = escape(", ".join(map(str, sorted({year for year, _ in _observed_periods(group)}))))
    selected_dates = (f"{escape(_date(group.get('selected_start')))} → "
                      f"{escape(_date(group.get('selected_end')))}")
    full_dates = (f"{escape(_date(group.get('full_start')))} → "
                  f"{escape(_date(group.get('full_end')))}")
    return (
        '<div class="facts">'
        f'<p>{_individual_count_html(group, member_count)}</p>'
        f'<p><strong>{_num(group.get("area_km2"), 0)} km² · {_num(group.get("n_grid_cells"), 0)} cells</strong> '
        f'<span class="fact-detail">({_num(group.get("width_km"))} × {_num(group.get("height_km"))} km)</span></p>'
        f'<p><strong>{_num(group.get("selected_span_days"))}</strong> '
        f'<span class="fact-detail">({selected_dates})</span> '
        f'<strong>of {_num(group.get("full_span_days"))} days</strong> '
        f'<span class="fact-detail">({full_dates})</span></p>'
        f'<p><span class="fact-detail">from</span> <strong>{years}</strong></p>'
        f'<p><strong>{_num(group.get("shared_week_overlap_days"), 2)} days</strong> '
        '<span class="fact-detail">span overlaps between individuals</span></p>'
        '</div>'
    )


class _HtmlCell(str):
    """Markup assembled by this module, with imported values escaped at construction."""


def _flags_cell(row):
    """Keep a single diagnostic inline; separate multiple criteria into bullets."""
    text = _violation_text(row)
    criteria = (r"Calendar window:|Density:|"
                r"Observed span:|Map rectangle |Map area |MCP-to-MCP gap ")
    parts = re.split(r"(?<=\.)\s+(?=(?:ID \d+: )?(?:" + criteria + r"))", text)
    items, individual = [], ""
    for part in parts:
        match = re.match(r"(ID \d+: )", part)
        if match:
            individual = match.group(1)
        elif individual and not part.startswith(("Map rectangle ", "Map area ", "MCP-to-MCP gap ")):
            part = individual + part
        if part:
            items.append(part)
    if len(items) > 1:
        return _HtmlCell('<ul class="flag-list">' + ''.join(
            f'<li>{escape(item)}</li>' for item in items) + '</ul>')
    return _HtmlCell(escape(text or "None"))


def _rows_table(headers, rows, classes="", row_classes=()) -> str:
    head = "".join(f"<th scope=\"col\">{escape(str(h))}</th>" for h in headers)
    body = "".join(
        (f'<tr class="{escape(row_classes[index], quote=True)}">'
         if index < len(row_classes) and row_classes[index] else "<tr>")
        + "".join(f"<td>{v if isinstance(v, _HtmlCell) else escape(_text(v))}</td>" for v in row) + "</tr>"
        for index, row in enumerate(rows)
    )
    return f'<div class="table-wrap"><table class="{classes}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _embedded_png(path: Path, alt: str, css_class="") -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return (f'<img class="{css_class}" alt="{escape(alt, quote=True)}" loading="lazy" '
            f'decoding="async" src="data:image/png;base64,{encoded}">')


def _config_rows(config: Mapping, prefix=""):
    for key, value in sorted(config.items()):
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping):
            yield from _config_rows(value, name)
        else:
            yield name, value


def _rings(geometry):
    kind = geometry.get("type")
    if kind == "Polygon":
        yield from geometry["coordinates"]
    elif kind == "MultiPolygon":
        for polygon in geometry["coordinates"]:
            yield from polygon


def _group_ids(group, members):
    if members:
        return sorted({int(row["individual_id"]) for row in members})
    raw = group.get("ids", [])
    return sorted(map(int, raw.split(";") if isinstance(raw, str) else raw))


def _point_stats(members):
    counts = [int(row["retained_fixes"]) for row in members]
    if not counts:
        return counts, None, None, None
    mean = sum(counts) / len(counts)
    cv = math.sqrt(sum((n - mean) ** 2 for n in counts) / len(counts)) / mean if mean else 0.0
    jain = sum(counts) ** 2 / (len(counts) * sum(n * n for n in counts)) if any(counts) else 0.0
    ratio = min(counts) / max(counts) if any(counts) else 0.0
    return counts, cv, jain, ratio


def _rankings_section(candidate_groups, members_by_group, table_id, title):
    headers = ["Rank", "Group", "Observed periods", "Jaguar IDs", "Fixes", "Point CV ↓", "Jain ↑",
               "Min/max ↑", "Extent (km × km)", "Area (km²)", "Grid cells", "Flags"]
    rows = []
    for group in candidate_groups:
        members = members_by_group[str(group["group_id"])]; _, cv, jain, ratio = _point_stats(members)
        link = f'#{escape(_slug(group["group_id"]), quote=True)}'
        style = _group_style(group)
        rows.append([
            _HtmlCell(f'<a class="rank-pill {style}" href="{link}">#{escape(_text(group.get("rank")))}</a>'),
            _HtmlCell(f'<a href="{link}">{escape(_text(group["group_id"]))}</a>'),
            _HtmlCell('<div class="period-list">' + ''.join(
                f'<span>{escape(label)}</span>' for label in _period_labels(group)) + '</div>'),
            _HtmlCell(f'<div>{_individual_count_html(group, len(members))}</div>'
                      f'<div class="fact-detail">IDs: {escape(_text(group.get("ids")))}</div>'),
            group.get("total_fixes"),
            _num(cv, 3), _num(jain, 4), _num(ratio, 3),
            f"{_num(group.get('width_km'))} × {_num(group.get('height_km'))}",
            _num(group.get("area_km2"), 0), group.get("n_grid_cells"),
            _HtmlCell(f'<div class="flag-cell">{_flags_cell(group)}</div>'),
        ])
    styles = [_group_style(g) for g in candidate_groups]
    html = [f'<section class="ranking-section" id="{table_id}"><h2>{escape(title)}</h2>']
    if not rows:
        html.append('<p>No groups satisfy the rules for this list.</p>')
    else:
        html.append(_rows_table(headers, rows[:7], "overview", styles[:7]))
        if len(rows) > 7:
            html.extend(['<details class="ranking-tail">',
                         f'<summary>📋 Show ranks 8–{len(rows)} ({len(rows) - 7} groups)</summary>',
                         _rows_table(headers, rows[7:], "overview", styles[7:]), '</details>'])
    html.append('</section>')
    return "".join(html)


def write_report(output_dir, result: Mapping) -> Path:
    """Write index.html and PNG figures; return the absolute HTML path.

    Main groups use ``report_groups``, ``report_group_members`` and ``report_points``.
    The second list uses ``relaxed_report_groups``, ``relaxed_group_members`` and
    ``relaxed_points``. Each list's rank matches its detailed section order.
    Combined overview figures show the first seven main groups; every group in
    either list gets its own map and point-count figure. MCP geometry is WGS84.
    Group bounds and EPSG describe the metric, buffered output rectangle.
    All dates in this report retain the input CSV's clock convention.
    """
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    image_dir = out / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(out / ".mplconfig"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    from pyproj import Transformer

    main_groups = [dict(group, candidate_list="main") for group in
                   sorted(result.get("report_groups", result.get("candidate_groups", [])),
                          key=lambda row: int(row.get("rank") or row.get("report_order") or 0))]
    relaxed_groups = [dict(group, candidate_list="relaxed") for group in
                      sorted(result.get("relaxed_report_groups", []),
                             key=lambda row: int(row.get("rank") or row.get("report_order") or 0))]
    groups = main_groups + relaxed_groups
    top_groups = main_groups[:7]

    def group_label(group):
        return (f"#{group.get('rank', '—')} · {group['group_id']}\n"
                + textwrap.fill(_period_label(group), width=48))

    report_members = (list(result.get("report_group_members", result.get("group_members", [])))
                      + list(result.get("relaxed_group_members", [])))
    report_points = (list(result.get("report_points", result.get("selected_points", [])))
                     + list(result.get("relaxed_points", [])))
    members_by_group = defaultdict(list)
    points_by_group = defaultdict(list)
    for row in report_members:
        members_by_group[str(row["group_id"])].append(row)
    for rows in members_by_group.values():
        rows.sort(key=lambda row: int(row["individual_id"]))
    for row in report_points:
        points_by_group[str(row["group_id"])].append(row)
    config = result.get("config", {})
    temporal = config.get("temporal", config)
    spatial = config.get("spatial", config)
    regular_min = float(temporal.get("regular_min_hours", 1.5))
    regular_max = float(temporal.get("regular_max_hours", 2.5))
    max_gap = float(temporal.get("max_gap_hours", 4.0))
    max_affected = float(temporal.get("max_affected_point_fraction", 0.20))
    min_points = int(temporal.get("min_subtrajectory_points", 5))
    max_short_loss = float(temporal.get("max_short_fragment_loss", 0.05))
    min_coverage = float(temporal.get("min_week_coverage", 0.80))
    week_days = float(temporal.get("week_days", 7))
    target_interval = float(temporal.get("target_interval_hours", 2))
    expected_fixes = int(round(week_days * 24 / target_interval)) + 1
    segment_quality = {}
    for key, points in points_by_group.items():
        by_trajectory = defaultdict(list)
        for point in points:
            by_trajectory[int(point["individual_id"]), str(point.get("trajectory_id", ""))].append(point)
        for (ident, _), series in by_trajectory.items():
            times = sorted(p["timestamp"] if isinstance(p["timestamp"], datetime)
                           else datetime.fromisoformat(str(p["timestamp"])) for p in series)
            affected = set()
            for j, (a, b) in enumerate(zip(times, times[1:])):
                gap = (b - a).total_seconds() / 3600
                if regular_max < gap <= max_gap:
                    affected.update((j, j + 1))
            item = segment_quality.setdefault((key, ident), {
                "max_affected": 0.0, "min_points": len(series), "usable_hours": 0.0})
            item["max_affected"] = max(item["max_affected"], len(affected) / len(series))
            item["min_points"] = min(item["min_points"], len(series))
            item["usable_hours"] += (times[-1] - times[0]).total_seconds() / 3600
    mcps = {}
    for feature in result.get("mcps_geojson", {}).get("features", []):
        prop = feature.get("properties", {})
        ident = prop.get("individual_id", prop.get("id"))
        if ident is not None:
            mcps[int(ident)] = feature["geometry"]
    all_ids = sorted({int(row["individual_id"]) for row in report_members})
    palette = plt.get_cmap("tab20")
    color_order = list(range(0, 20, 2)) + list(range(1, 20, 2))
    colors = {ident: palette(color_order[j % 20]) for j, ident in enumerate(all_ids)}

    def draw_map(ax, group, compact=False):
        key = str(group["group_id"])
        members = members_by_group[key]
        ids = _group_ids(group, members)
        sexes = {int(member["individual_id"]): member.get("sex", "unknown") for member in members}
        raw_bounds = group.get("bounds")
        bounds = json.loads(raw_bounds) if isinstance(raw_bounds, str) else raw_bounds
        epsg = group.get("epsg", 32721)
        target = f"EPSG:{epsg}" if str(epsg).isdigit() else str(epsg)
        project = Transformer.from_crs("EPSG:4326", target, always_xy=True)
        if bounds is None:
            xy = [project.transform(float(p["longitude"]), float(p["latitude"]))
                  for p in points_by_group[key]]
            if not xy:
                ax.text(0.5, 0.5, "No spatial data", ha="center", transform=ax.transAxes)
                return
            bounds = (min(p[0] for p in xy) - 1000, min(p[1] for p in xy) - 1000,
                      max(p[0] for p in xy) + 1000, max(p[1] for p in xy) + 1000)
        xmin, ymin, xmax, ymax = map(float, bounds)
        width, height = (xmax - xmin) / 1000, (ymax - ymin) / 1000
        for ident in ids:
            color = colors.get(ident, palette(0))
            marker, sex_label = _sex_marker(sexes.get(ident, "unknown"))
            for ring in _rings(mcps.get(ident, {})):
                lon, lat = zip(*ring)
                x, y = project.transform(lon, lat)
                ax.plot([(v - xmin) / 1000 for v in x], [(v - ymin) / 1000 for v in y],
                        color=color, lw=1, alpha=0.65, linestyle="--")
            trajectories = defaultdict(list)
            for point in points_by_group[key]:
                if int(point["individual_id"]) == ident:
                    trajectories[str(point.get("trajectory_id", ident))].append(point)
            for points in trajectories.values():
                points.sort(key=lambda p: str(p["timestamp"]))
                x, y = project.transform([float(p["longitude"]) for p in points],
                                         [float(p["latitude"]) for p in points])
                ax.plot([(v - xmin) / 1000 for v in x], [(v - ymin) / 1000 for v in y],
                        color=color, lw=1.1, marker=marker, markersize=3.5, alpha=0.9)
            ax.plot([], [], color=color, lw=1.7, marker=marker, markersize=5,
                    label=f"{ident} ({sex_label})")
        title = group_label(group)
        ax.set_title(title + f"\n{width:.1f} × {height:.1f} km = {width * height:,.0f} km²",
                     loc="left", fontsize=10 if compact else 12, pad=8)
        ax.set_xlim(0, width)
        ax.set_ylim(0, height)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("Easting from extent west (km)", fontsize=8 if compact else 10)
        ax.set_ylabel("Northing from extent south (km)", fontsize=8 if compact else 10)
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.yaxis.set_major_locator(MaxNLocator(4))
        ax.tick_params(labelsize=8 if compact else 9)
        ax.grid(color="#dedede", lw=0.5)
        legend_title = "Jaguar ID / sex (M: male, F: female)"
        if any(_sex_marker(sexes.get(ident))[1] == "?" for ident in ids):
            legend_title += "\n?: unknown sex"
        ax.legend(title=legend_title, ncol=min(4, max(1, len(ids))), loc="upper center",
                  bbox_to_anchor=(0.5, -0.18), frameon=False, fontsize=7 if compact else 8,
                  title_fontsize=8)

    def draw_counts(ax, group, compact=False):
        members = members_by_group[str(group["group_id"])]
        counts, cv, jain, ratio = _point_stats(members)
        ids = [int(row["individual_id"]) for row in members]
        ax.bar(range(len(ids)), counts, color="#327d8a", width=0.65)
        ax.set_xticks(range(len(ids)), list(map(str, ids)), rotation=45 if len(ids) > 9 else 0)
        ax.set_xlabel("Jaguar ID")
        ax.set_ylabel("Retained fixes")
        title = group_label(group)
        detail = f"CV {_num(cv, 3)} · Jain {_num(jain, 4)} · min/max {_num(ratio, 3)}"
        ax.set_title(title + "\n" + detail, loc="left", fontsize=10 if compact else 12)
        for j, n in enumerate(counts):
            ax.text(j, n, str(n), ha="center", va="bottom", fontsize=8 if compact else 9)
        ax.set_ylim(0, max(counts, default=1) * 1.23)
        ax.yaxis.set_major_locator(MaxNLocator(4, integer=True))
        ax.grid(axis="y", color="#dedede", lw=0.5)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)

    def save_figure(fig, name):
        path = image_dir / name
        fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return path

    group_figures = {}
    for group in groups:
        key = str(group["group_id"])
        fig, ax = plt.subplots(figsize=(6.4, 6.3), constrained_layout=True)
        draw_map(ax, group)
        map_path = save_figure(fig, f"candidate_{_slug(key)}_map.png")
        fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.8), constrained_layout=True,
                                 gridspec_kw={"width_ratios": [1.65, 1]})
        draw_counts(axes[0], group)
        counts, *_ = _point_stats(members_by_group[key])
        if counts:
            axes[1].hist(counts, bins=min(5, max(1, len(set(counts)))), color="#7a8c91",
                         edgecolor="white")
        axes[1].set_title("Distribution across individuals", fontsize=10, loc="left")
        axes[1].set_xlabel("Retained fixes per jaguar")
        axes[1].set_ylabel("Number of jaguars")
        axes[1].yaxis.set_major_locator(MaxNLocator(integer=True))
        axes[1].xaxis.set_major_locator(MaxNLocator(4))
        axes[1].spines[["top", "right"]].set_visible(False)
        counts_path = save_figure(fig, f"candidate_{_slug(key)}_point_counts.png")
        group_figures[key] = (map_path, counts_path)

    combined_maps = combined_counts = None
    if top_groups:
        nrows = math.ceil(len(top_groups) / 2)
        for kind, draw, height in (("maps", draw_map, 4.8), ("point_counts", draw_counts, 3.3)):
            fig, axes = plt.subplots(nrows, 2, figsize=(12, height * nrows),
                                     constrained_layout=True, squeeze=False)
            for ax, group in zip(axes.flat, top_groups):
                draw(ax, group, compact=True)
            for ax in list(axes.flat)[len(top_groups):]:
                ax.set_visible(False)
            title = ("First seven groups: full-study MCP95 and selected trajectories" if kind == "maps"
                     else "First seven groups: point-count balance across individuals")
            fig.suptitle(title, fontsize=15, x=0.02, ha="left")
            path = save_figure(fig, f"candidate_{kind}.png")
            if kind == "maps":
                combined_maps = path
            else:
                combined_counts = path

    membership = result.get("membership_summary", {})
    membership_note = ""
    if membership:
        main_count = len(membership.get("main_individual_ids", []))
        new_relaxed_count = len(membership.get("relaxed_only_individual_ids", []))
        missing_count = len(membership.get("unrepresented_individual_ids", []))
        membership_note = (f'<p><strong>Individual coverage:</strong> {main_count} individuals appear in the main list; '
                           f'{new_relaxed_count} more appear only in the relaxed list; {missing_count} remain absent from both. '
                           '<a href="#individual-audit">Review individual coverage and exclusions</a>.</p>')
    generated_count = result.get("generated_group_count", len(main_groups))
    relaxed_count = result.get("relaxed_generated_group_count", len(relaxed_groups))
    parts = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             "<title>Pantanal trajectory candidates</title>",
             """<style>
body{font:15px/1.5 system-ui,sans-serif;color:#202b31;background:#fff;margin:0 auto;padding:28px;max-width:1300px}
h1{font-size:28px;margin:0 0 10px}h2{font-size:21px;margin:30px 0 12px}h3{font-size:17px;margin:20px 0 8px}
p{max-width:1100px}a{color:#146474}table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
th{text-align:left;background:#eef3f4;font-weight:600}th,td{padding:9px 10px;border-bottom:1px solid #dbe2e4;vertical-align:top}
.table-wrap{overflow-x:auto;margin:12px 0 20px}.overview{font-size:12px}img{max-width:100%;height:auto}.map{display:block;max-width:740px}
.muted{color:#52636c}.group{margin-top:42px;padding-top:10px;border-top:1px solid #b9c8cd}.facts{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 28px;font-size:14px}
.facts p{margin:4px 0}details{margin:18px 0}summary{cursor:pointer;font-weight:600}code{font-size:13px;overflow-wrap:anywhere}
.back-link{font-size:13px}section,nav{scroll-margin-top:18px}
@media(max-width:600px){body{padding:14px}h1{font-size:24px}th,td{padding:7px}}
@media print{body{max-width:none;padding:0;font-size:11px}.group{break-before:page}.table-wrap{overflow:visible}details{display:block}}
""" + CALENDAR_CSS + "</style></head><body id=\"top\">",
             "<h1>Pantanal trajectory candidates</h1>",
             f'<p class="report-links"><a href="#candidate-navigation">🗓️ Candidate navigation</a> · '
             '<a href="#ranking-tables">🌎 Rankings</a> · <a href="#point-count-metrics">Metric definitions and sources</a></p>',
             f"<p>{len(result.get('individuals', []))} cohort individuals audited. "
             f"{len(main_groups)} of {_num(generated_count, 0)} main groups and "
             f"{len(relaxed_groups)} of {_num(relaxed_count, 0)} relaxed groups are shown. "
             "Groups pool windows by their starting calendar month. Retained observations may span multiple months or years.</p>",
             membership_note,
             '<details id="rules-summary"><summary>Cadence, density and segmentation rules</summary>',
             f'<p><strong>Cadence (protected):</strong> choose observed fixes nearest {_num(target_interval, 0)} hours apart; '
             f'regular intervals are {_num(regular_min)}–{_num(regular_max)} hours. Gaps above {_num(regular_max)} '
             f'and up to {_num(max_gap)} hours can remain within segments when their retained affected endpoints '
             f'total at most {_pct(max_affected, 0)} of all resampled points in the individual candidate period, '
             'counted before cuts and fragment removal. Count each affected point once, even if both neighboring gaps are irregular.</p>',
             f'<p><strong>Segmentation (protected):</strong> gaps longer than {_num(max_gap)} hours break the trajectory. '
             'Split at irregular transitions as needed to meet the affected-point ceiling. '
             f'Keep segments of at least {min_points} points; dropping shorter fragments may lose at most {_pct(max_short_loss, 0)} '
             'of all selected parent-window points before splitting. The denominator is never reset to a favorable fragment.</p>',
             f'<p><strong>Density and span:</strong> main-list windows retain at least {math.ceil(expected_fixes * min_coverage)} '
             f'of {expected_fixes} reference fixes ({_pct(min_coverage, 0)}), spanning at least '
             f'{_num(temporal.get("min_week_observed_span_days", 6.5))} days within a {_num(week_days, 0)}-day window '
             'that may cross month or year boundaries. These thresholds can be relaxed in the second list, with the measured deficits shown.</p>',
             '<p><strong>Full-record summaries:</strong> tracking span and observed year-month counts are descriptive only; '
             'they have no inclusion threshold, warning, ranking penalty or relaxed-group trigger. '
             'Sex counts use collar metadata; missing or conflicting values are shown as unknown. '
             'No locations are interpolated, and actual timestamps remain in the exports.</p></details>',
             "<p><strong>Dates:</strong> selected start/end describe the earliest and latest selected records. "
             "These date envelopes may include gaps between records or individual windows and do not establish continuous coverage. "
             "Individual windows below identify the actual periods needed for covariate extraction. "
             "Full-study dates describe the data used to construct each MCP95. Observed-period labels identify months containing retained fixes; "
             "a range joins consecutive represented months and does not imply continuous observations. Month-specific years and contributor counts "
             "are calculated from retained timestamps rather than from the group date envelope. Timestamps retain the CSV clock convention; no time zone is inferred.</p>",
             '<div id="ranking-tables">',
             "<p><strong>Reading the ranks:</strong> candidate groups are ranked independently within the main and relaxed lists "
             "by decreasing balanced-fix score, defined as the total number of retained fixes multiplied by Jain's index of "
             "evenness in individual point counts. Ties are resolved successively by higher median fix-count coverage, "
             "lower median affected-point fraction, and smaller map area, followed by calendar month and individual identifiers. "
             "Tables and detailed sections follow rank order. Flags do not modify the ranking score. Within each calendar month, "
             "navigation links are arranged as unflagged main groups, flagged main groups, and relaxed groups, "
             "with rank order maintained within each category.</p>",
             _rankings_section(main_groups, members_by_group, "main-rankings", "🌎 Main candidate rankings"),
             '<p><a href="data/all_group_candidates.csv">Main rankings (CSV)</a></p>',
             "<p>The separate list below includes individuals absent from all main groups, "
             "relaxing the stated density, observed-span, MCP-proximity, or map-budget requirements. The four-hour within-segment gap ceiling, period-wide affected-point budget, "
             "the five-point minimum, and the 5% short-fragment-loss ceiling remain enforced. Every exception is described with its measured value.</p>",
             _rankings_section(relaxed_groups, members_by_group, "relaxed-rankings", "🌎 Relaxed candidate rankings"),
             '<p><a href="data/relaxed_group_candidates.csv">Relaxed rankings (CSV)</a></p></div>',
             "<p>Groups are alternatives and can reuse individuals and fixes; they are not independent replicates. "
             "The relaxed list is for inspection and comparison, not a declaration that its groups are ready for training.</p>",
             "<p>An individual missing from the main list may have a sparse or short window, or need a larger or more separated spatial group. "
             "The second list exposes those cases. An individual without any window satisfying the protected cadence and segmentation rules "
             "still cannot be added: relaxing density or geography does not fix irregular sampling or excessive fragment loss. "
             '<a href="#individual-audit">Its measured failures remain available in the individual audit</a>.</p>',
             METRIC_NOTES_HTML,
             "<p class=\"muted\">Min/max is the smallest individual count divided by the largest. "
             "These measures compare individual contributions and are distinct from variation in subtrajectory lengths.</p>",
             "<p>Area and dimensions refer to the buffered, grid-aligned map rectangle, not the summed MCP area. "
             "MCP95 outlines use full-study locations before temporal filtering. "
             "Dashed lines are MCP95 boundaries; solid lines connect selected fixes only within their recorded subtrajectory. "
             "A 95% MCP is a trimmed convex hull used here as a proximity proxy.</p>"]
    same_year = result.get("best_same_year_candidate")
    if same_year:
        same_year_id = str(same_year.get("group_id", ""))
        same_year_link = (f'<a href="#{escape(_slug(same_year_id), quote=True)}">'
                          f'View {escape(same_year_id)} in this report</a> · '
                          if same_year_id in {str(g["group_id"]) for g in groups} else "")
        parts.append(
            f"<p><strong>Best same-year alternative:</strong> rank {escape(_text(same_year.get('rank')))}, "
            f"{escape(_period_label(same_year))}, "
            f"IDs {escape(_text(same_year.get('ids')))}, {_num(same_year.get('total_fixes'), 0)} retained fixes, "
            f"{_num(same_year.get('area_km2'), 2)} km². Shared year does not require the individuals' windows to overlap. "
            + same_year_link +
            '<a href="data/all_group_candidates.csv">Full generated candidate ranking (CSV)</a>.</p>')
    if combined_maps:
        parts.append(f'<p><a href="{escape(combined_maps.relative_to(out).as_posix())}">📋 First seven maps (PNG)</a> · '
                     f'<a href="{escape(combined_counts.relative_to(out).as_posix())}">First seven count charts (PNG)</a>. '
                     'Every group has its own figures below.</p>')
    parts.append('<p><strong>Map symbols:</strong> triangles mark male fixes, circles female fixes, '
                 'and crosses unknown sex. Colors identify individuals; dashed outlines show their full-study MCP95.</p>')
    parts.append(candidate_calendar(groups))
    parts.append('<p><a href="data/group_month_coverage.csv">Calendar-month coverage (CSV)</a> · '
                 '<a href="data/group_year_month_coverage.csv">Year-month coverage (CSV)</a></p>')
    previous_list = None
    for group in groups:
        key = str(group["group_id"]); members = members_by_group[key]
        map_path, counts_path = group_figures[key]
        list_kind = group["candidate_list"]
        if list_kind != previous_list:
            title = "Main candidate groups" if list_kind == "main" else "Relaxed candidate groups"
            parts.append(f'<div class="list-heading {list_kind}" id="{list_kind}-groups"><h2>{title}</h2>'
                         '<p>Groups appear in rank order within this list.</p></div>')
            previous_list = list_kind
        rank_markup = f'<span class="rank-pill {_group_style(group)}">#{escape(_text(group.get("rank")))}</span>'
        month_markup = " ".join(
            f'<span class="month-chip">🗓️ {escape(label)}</span>' for label in _period_labels(group))
        violations = _violation_text(group)
        if violations:
            review_note = (f'<p class="flag-note {list_kind}"><strong>Review flags:</strong> {escape(violations)} '
                           'The selected subtrajectories still satisfy the protected cadence and segmentation rules below.</p>')
        else:
            review_note = '<p class="clear-note">No window-quality or spatial-budget flags for this group.</p>'
        parts.extend([
            f'<section class="group" id="{escape(_slug(key), quote=True)}">',
            f'<h2 class="group-title">{rank_markup} {escape(key)} {month_markup}</h2>',
            _group_facts(group, len(members)),
            review_note,
            _embedded_png(map_path, f"MCP95 polygons and selected subtrajectories for {key}", "map"),
            _embedded_png(counts_path, f"Retained fix counts by jaguar and count histogram for {key}"),
            _rows_table(["ID", "Study", "Observed periods", "Selected start", "Selected end", "Selected days", "Usable hours", "Fixes", "Subtrajectories", "Flags"],
                        [[r.get("individual_id"), r.get("study"), _period_label(r), _date(r.get("selected_start")), _date(r.get("selected_end")),
                          _num(r.get("selected_duration_days"), 2),
                          _num(r.get("usable_duration_hours", segment_quality.get((key, int(r["individual_id"])), {}).get("usable_hours")), 1),
                          r.get("retained_fixes"), r.get("n_subtrajectories"), _flags_cell(r)]
                         for r in members]),
            "<p class=\"muted\">Selected days is the elapsed span from the first to last retained fix. Usable hours sums "
            "the elapsed durations within retained subtrajectories, excluding the gaps between them. "
            "The intersection of selected spans is a date-range comparison, not proof of uninterrupted simultaneous fixes.</p>",
            _rows_table(["ID", "Retained affected points / all resampled points (period)", "Parent-window affected points", "Max segment affected points (diagnostic)", "Shortest segment (points)", "Short-fragment loss", f"Year-months with ≥{temporal.get('min_days_per_month', 7)} observed dates (descriptive)"],
                        [[r.get("individual_id"),
                          f"{_text(r.get('retained_affected_points'))}/{_text(r.get('affected_point_denominator'))} ({_pct(r.get('affected_point_fraction'))})",
                          _pct(r.get("parent_affected_point_fraction")),
                          _pct(r.get("max_segment_affected_fraction", segment_quality.get((key, int(r["individual_id"])), {}).get("max_affected"))),
                          segment_quality.get((key, int(r["individual_id"])), {}).get("min_points"),
                          _pct(r.get("short_fragment_loss")), r.get("qualifying_months")]
                         for r in members]),
            _rows_table(["ID", "Full-study start", "Full-study end", "Full-study duration (days)"],
                        [[r.get("individual_id"), _date(r.get("full_start")), _date(r.get("full_end")),
                          _num(r.get("full_duration_days"), 1)] for r in members]),
            '<p class="back-link"><a href="#candidate-navigation">Back to all candidate links</a></p>',
            "</section>",
        ])

    parts.extend(["<h2>Selection rules and audit</h2>",
                  f"<p>Regular selected intervals are {_num(regular_min)}–{_num(regular_max)} hours. "
                  f"A final subtrajectory may contain gaps up to {_num(max_gap)} hours and must contain at least {min_points} points. "
                  f"The parent {_num(week_days, 0)}-day window may contain multiple valid subtrajectories. "
                  f"Across all retained segments, the number of unique points touching retained irregular intervals must be at most {_pct(max_affected, 0)} "
                  "of all resampled parent-window points before cuts or fragment removal. The denominator is fixed for the complete individual period. "
                  "A segment can exceed this percentage locally; segment-level fractions are diagnostic. "
                  "Cuts remove transitions from the affected-point numerator without resetting the denominator.</p>",
                  f"<p>Dropping short fragments may remove at most {_pct(max_short_loss, 0)} of the "
                  f"resampled candidate points. A main-list candidate must retain at least {_pct(min_coverage, 0)} of "
                  f"{expected_fixes} expected fixes at an exact {_num(target_interval, 0)}-hour cadence. The expected count is a reference, "
                  "not a mathematical maximum under the interval tolerance. "
                  f"Its retained observations must span at least {_num(temporal.get('min_week_observed_span_days', 6.5))} days "
                  f"within a complete {_num(week_days, 0)}-day envelope, including observations across month and year boundaries. "
                  "The relaxed list may fall below these density and observed-span thresholds; the exact deficits are flagged. Calendar boundaries do not shorten windows or constitute a violation. "
                  "Actual timestamps and elapsed durations are preserved; no missing positions are interpolated.</p>",
                  "<p><strong>Descriptive full-record coverage:</strong> report tracking span, observed year-months, "
                  f"and year-months containing at least {_num(temporal.get('min_days_per_month', 7), 0)} observed dates. "
                  "No minimum number of months or tracking days is required or flagged. "
                  "Only selected-window quality and spatial-budget exceptions generate group review flags.</p>",
                  "<p>All 56 Pantanal individuals are included in the cohort audit. Individuals without usable regular two-hour periods "
                  "are excluded from candidate selection. A study-wide median interval is diagnostic and does not automatically "
                  "exclude every member, because collar schedules can change within studies and individuals.</p>",
                  "<p>In the individual audit, full-record duration/month counts do not determine window eligibility. "
                  "An individual can have a long record yet no usable window, or have usable windows but no group "
                  "that satisfies the spatial map budget. The complete generated ranking is not an exhaustive search of every possible "
                  "combination: candidate generation retains the best qualifying window per individual and window-start month/year, then grows bounded MCP groups. "
                  "Calendar navigation uses every month with retained observations, independently of this starting-month grouping rule.</p>",
                  f"<p>Spatial growth uses a {_num(spatial.get('growth_buffer_km', 5))} km gap allowance from the current MCP union. "
                  f"The main-list map has {_num(spatial.get('export_padding_km', 5))} km padding and is capped at "
                  f"{_num(spatial.get('max_extent_side_km', 40))} km per side and {_num(spatial.get('max_extent_area_km2', 1600), 0)} km². "
                  "A relaxed group may also exceed the MCP growth-gap allowance to connect a previously excluded individual; "
                  "its observed separation and the original limit are flagged. Any spatial exception is recorded against the original limits. "
                  f"Distances and areas are calculated in {escape(_text(spatial.get('metric_crs', 'EPSG:32721')))}; GeoJSON coordinates are WGS84. "
                  f"The grid cell size is {_num(spatial.get('cell_size_m', 500), 0)} m.</p>",
                  "<p>The period affected-point fraction counts each retained point once if either retained adjacent gap is outside the regular interval "
                  "but within the allowed maximum, divided by all resampled points in the individual period before fragmentation. "
                  "Short-fragment loss uses the same fixed resampled-point denominator, "
                  "not against every raw high-frequency fix. Gaps and discarded fragments are not joined into observed movements. "
                  "The numeric configuration below records the thresholds used for this run.</p>",
                  "<details><summary>Run configuration</summary>",
                  _rows_table(["Setting", "Value"], _config_rows(config)), "</details>"])
    parts.append('<section id="individual-audit"><h2>Individual coverage audit</h2></section>')
    ungrouped = [row for row in result.get("individuals", [])
                 if "in_main_groups" in row and not _true(row.get("in_main_groups"))
                 and not _true(row.get("in_relaxed_groups"))]
    if ungrouped:
        parts.extend(['<h2 id="ungrouped-individuals">Individuals absent from both lists</h2>',
                      '<p>These individuals remain in the audit. A relaxed group is only generated when its retained '
                      'subtrajectories pass every protected temporal rule and a group can be formed.</p>',
                      _rows_table(["Individual", "Study", "Why no generated group", "Observed year-months (descriptive)"],
                                  [[row.get("individual_id"), row.get("study"), row.get("group_membership_reason"),
                                    row.get("observed_months")] for row in ungrouped])])
    for name, key in (("Study cohort audit", "cohort_audit"), ("Individual eligibility audit", "individuals")):
        rows = result.get(key, [])
        if rows:
            fields = list(dict.fromkeys(k for row in rows for k in row))
            parts.extend([f"<details><summary>{escape(name)}</summary>",
                          _rows_table(fields, [[row.get(k) for k in fields] for row in rows]), "</details>"])
    sources = result.get("sources", [])
    if sources:
        parts.append("<h2>Sources</h2><ul>")
        for source in sources:
            url = str(source.get("url", ""))
            title = escape(str(source.get("title", url)))
            if url.startswith(("https://", "http://")):
                parts.append(f'<li><a href="{escape(url, quote=True)}">{title}</a></li>')
            else:
                parts.append(f"<li>{title}</li>")
        parts.append("</ul>")
    parts.extend(['<nav class="float-nav" aria-label="Page shortcuts">',
                  '<button type="button" aria-label="Toggle page shortcuts" aria-controls="floating-page-links" '
                  'aria-expanded="false">☰</button>',
                  '<div class="float-nav-links" id="floating-page-links">'
                  '<a href="#top">↑ Back to top</a>'
                  '<a href="#candidate-navigation">🗓️ Back to navigation</a>'
                  '<a href="#ranking-tables">🌎 Back to tables</a></div></nav>',
                  """<script>
(function(){
  const menu = document.querySelector('.float-nav');
  const button = menu.querySelector('button');
  const setOpen = function(open){menu.classList.toggle('is-open',open);button.setAttribute('aria-expanded',String(open));};
  button.addEventListener('click',function(){setOpen(!menu.classList.contains('is-open'));});
  menu.querySelectorAll('a').forEach(function(link){link.addEventListener('click',function(){setOpen(false);});});
  document.addEventListener('keydown',function(event){if(event.key==='Escape'){setOpen(false);if(menu.contains(document.activeElement)){button.focus();}}});
  document.addEventListener('click',function(event){if(!menu.contains(event.target)){setOpen(false);}});
})();
</script>""", CALENDAR_SCRIPT, "</body></html>"])
    path = out / "index.html"
    path.write_text("\n".join(parts), encoding="utf-8")
    return path
