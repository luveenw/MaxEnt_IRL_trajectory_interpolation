"""Offline season → collection → group report for all retained seasonal bursts."""
from collections import defaultdict
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

from .movement_processor_pantanal import write_csv
from .movement_processor_pantanal_bouts import aggregate_windows
from .pantanal_seasonal_report import (
    CSS, SEASON_ICONS, _table, _svg, _save_svg as _save_figure, _image, _map, _counts,
    _weekly_density, _density_svg, _text,
)


def _save_svg(output, name, content):
    (output/'images').mkdir(exist_ok=True)
    return _save_figure(output, name+'.svg', content)


def _timeline(windows):
    rows = defaultdict(list)
    for w in windows:
        a = w['season_attributions'][0]
        rows[w['individual_id'], a['season_year']].append(w)
    width, height = 1080, 100+24*len(rows)
    body = '<text x="12" y="23">Selected bursts by individual and season-year · each bar is a separate burst</text>'
    for n, ((ident, year), ws) in enumerate(sorted(rows.items())):
        y = 65+n*24
        a = ws[0]['season_attributions'][0]
        start, end = a['core_start'], a['core_end']
        duration = (end-start).total_seconds()
        body += f'<text x="12" y="{y+4}">ID {ident} · {year}</text><path d="M135,{y} H1040" stroke="#dde7e3"/>'
        for w in ws:
            x = 135+905*(w['start']-start).total_seconds()/duration
            size = max(.9,905*(w['end']-w['start']).total_seconds()/duration)
            title = f"ID {w['individual_id']}: {w['start']} to {w['end']}; {w['selected_fixes']} selected fixes"
            body += f'<rect x="{x:.2f}" y="{y-5}" width="{size:.2f}" height="10" fill="#668c96"><title>{escape(title)}</title></rect>'
    if rows:
        a = next(iter(rows.values()))[0]['season_attributions'][0]
        body += f'<text x="135" y="{height-12}">{a["core_start"]:%b %d}</text>'
        body += f'<text x="1040" y="{height-12}" text-anchor="end">{a["core_end"]-timedelta(days=1):%b %d}</text>'
    return _svg(width,height,body,'All qualifying bursts within each season occurrence')


def _pct(value):
    return '—' if value is None else f'{value:.1f}%'


def _status(value):
    return value.replace('bout', 'burst').replace('_', ' ')


def _animal_table(windows, coverage):
    by_id = defaultdict(list)
    for w in windows:
        by_id[w['individual_id']].append(w)
    return _table(['ID','All native fixes in season','Bursts','Selected fixes','Selected / all native','Preserved native fixes','Preserved / all native','≥5-fix bursts','Defined turns','Season-years'],[
        [i,coverage[i]['raw_fixes'],len(ws),sum(w['selected_fixes'] for w in ws),
         _pct(100*sum(w['selected_fixes'] for w in ws)/coverage[i]['raw_fixes']),
         sum(w['raw_fixes'] for w in ws),_pct(100*sum(w['raw_fixes'] for w in ws)/coverage[i]['raw_fixes']),
         sum(w['five_point_eligible'] for w in ws),sum(w['defined_turn_count'] for w in ws),
         ', '.join(map(str,sorted({a['season_year'] for w in ws for a in w['season_attributions']})))]
        for i,ws in sorted(by_id.items())])


def write_report(output, result):
    output = Path(output)
    groups = {g['group_id']: g for g in result['groups']}
    windows = {w['window_id']: w for g in groups.values() for w in g['windows']}
    sexes = {r['individual_id']: r.get('sex','unknown') for r in result['individuals']}
    mcps = {int(f['properties']['individual_id']): f['geometry'] for f in result['mcps_geojson']['features']}
    coverage = {(r['season'],r['individual_id']):r for r in result['season_individual_coverage']}
    group_coverage = {r['group_id']:r for r in result['group_season_coverage']}
    cap = result['policy']['hard_gap_hours']
    h = [f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Pantanal seasonal bursts</title><style>{CSS}</style><body>',
         '<h1>Pantanal seasonal trajectory selection</h1>',
         '<p>Every qualifying local burst, pooled across years within one season. Start with the seasonal totals below; open a collection for its animals, maps and temporal coverage. A collection contains computational map groups, each retaining every qualifying burst for its animals.</p>',
         f'<p><strong>Main policy:</strong> observed fixes selected near a two-hour target (regular band 1.5–2.5 h), ≥3 selected fixes per burst, native and selected gaps ≤{cap:g} h (four hours plus {result["policy"]["gap_jitter_minutes"]} minutes jitter). Tag changes and season boundaries are cuts. Actual durations and all native observations within admitted bursts are preserved. There is no weekly density, weekly span, or affected-point percentage gate.</p>',
         '<p><strong>Interpretation:</strong> these are temporally eligible observations. Residence, habitat fidelity, random missingness and reward-model validity have not been established. A defined turn requires two nonzero observed displacements; it is not an effective independent sample count. Grid collapse and optimizer suitability are evaluated separately at export.</p>',
         '<p>Season dates: <strong>Winter: May 15–August 14</strong> — dry with rare showers. <strong>Spring: August 15–November 14</strong> — hottest season of the year. <strong>Summer: November 15–March 21</strong> — hot, humid, and rainy, with intense downpours or thunderstorms. <strong>Autumn: March 22–May 14</strong> — gradual decrease in temperature and rain; rivers return to their banks. Summer’s season-year is its November start year. No season buffer. Source and user-approved operational dates: <a href="https://www.climatestotravel.com/climate/brazil/pantanal">Climates to Travel</a>.</p>',
         '<p><a href="cutoffs.json">Active cutoff values</a> · <a href="data/season_summary.csv">Season totals</a> · <a href="data/sensitivity.csv">Individual × season comparisons</a> · <a href="data/windows.csv">Unique retained bursts</a> · <a href="data/rejected_bouts.csv">Rejected short bursts</a> · <a href="data/individual_audit.csv">All-individual audit</a> · <a href="data/collection_members.csv">Canonical ownership</a></p>',
         '<p>Counts below are unique within each season. Group tables may repeat an animal’s evidence across alternative map contexts; use collection membership status <code>selected</code> to count or export it once. “Native fixes” includes both selected fixes and finer observations preserved between them and at burst tails.</p>']
    h.append('<p><strong>Retention denominator:</strong> all QC-passed native fixes recorded in that season across all study years, including fixes outside accepted bursts. Selected retention measures the two-hour sampled subset; native preservation includes finer fixes and burst tails. These percentages measure fix retention, not the fraction of calendar time monitored or nominal scheduled fixes acquired. Season totals include all 56 animals; group percentages use only member animals. A dash means no native fixes, whereas 0% means fixes existed but none were retained. Pooled percentages are ratios of summed counts, not averages of animal percentages.</p>')
    h.append('<p><a href="data/season_individual_coverage.csv">All 56 individuals × four seasons</a> · <a href="data/group_individual_coverage.csv">Per-group individual retention</a> · <a href="data/group_season_coverage.csv">Group retention totals</a></p>')
    h.append(_table(['Season','Individuals','All native fixes','Bursts','Selected fixes','Selected / all native','Native fixes preserved','Preserved / all native','≥5-fix alternative: individuals / bursts / fixes','8-hour sensitivity: individuals / bursts / fixes'],[
        [f'<a href="#season-{r["season"]}">{r["season"].title()}</a>',r['n_individuals'],r['raw_fixes'],r['main_bouts'],r['main_selected_fixes'],_pct(r['selected_retention_pct']),r['main_source_fixes'],_pct(r['native_preservation_pct']),
         f'{r["five_point_individuals"]} / {r["five_point_bouts"]} / {r["five_point_selected_fixes"]}',
         f'{r["eight_hour_individuals"]} / {r["eight_hour_bouts"]} / {r["eight_hour_selected_fixes"]}'] for r in result['season_summary']]))
    h.append(f'<p>The five-fix alternative filters the same main bursts by length. The native alternative tests ≥3 original fixes in runs with ≤{cap:g}-hour native intervals, without two-hour thinning. The eight-hour sensitivity reruns selection with a larger gap cap; its sampling phase can change, so the CSV reports both gained and lost selected events. Sensitivities do not enter the main checkpoint.</p>')
    all_density = []
    for definition in result['seasons']:
        name = definition['name']
        season_coverage = {i:r for (s,i),r in coverage.items() if s == name}
        h.append(f'<section class="season-panel" data-season="{name}" id="season-{name}"><h3>{SEASON_ICONS[name]} {name.title()}</h3>')
        h.append('<details><summary>Retention for all 56 individuals in this season, including excluded individuals</summary>')
        h.append(_table(['ID','All native fixes','Bursts','Selected fixes','Selected retention','Native preserved','Native preservation','Status'],[
            [i,r['raw_fixes'],r['bouts'],r['selected_fixes'],_pct(r['selected_retention_pct']),r['preserved_native_fixes'],_pct(r['native_preservation_pct']),_status(r['status'])]
            for i,r in sorted(season_coverage.items())]))
        h.append('</details>')
        for c in [c for c in result['collections'] if c['season']==name]:
            cid = c['collection_id']
            gs = [groups[gid] for gid in c['group_ids']]
            members = [m for m in result['collection_members'] if m['collection_id']==cid]
            owned = [windows[m['window_id']] for m in members if m['selection_status']=='selected']
            views = [dict(g, windows=list(aggregate_windows(g['windows']).values())) for g in gs]
            h.append(f'<section class="collection" id="{cid}"><h2>{cid}: {c["n_individuals"]} individuals · {len(owned):,} bursts</h2>')
            h.append(f'<p>{c["n_selected_fixes"]:,} selected fixes; {c["n_source_fixes"]:,} native fixes preserved. All qualifying bursts for this season are present. Groups: '+', '.join(f'<a href="#'+g['group_id']+'">'+g['group_id']+'</a>' for g in gs)+'.</p>')
            flagged = [g['group_id'] for g in gs if g['spatial_violation_codes']]
            if flagged:
                h.append('<p class="flag-note">Map-budget exceptions: '+', '.join(flagged)+'. Evidence is preserved; the current exporter excludes these map contexts from optimizer-candidate lists.</p>')
            h.append(_image(_save_svg(output,cid+'-map',_map(views,mcps,collection=True,sexes=sexes)),cid+' geographic groups','map'))
            h.append('<p class="detail">Colors identify map groups. Solid envelopes enclose the member MCP95 hulls; dashed outlines are individual full-study MCP95 hulls in that group’s color. Individual track colors appear in the group plots below.</p>')
            h.append(_image(_save_svg(output,cid+'-timeline',_timeline(owned)),cid+' separate seasonal bursts'))
            h.append(_animal_table(owned, season_coverage))
            density = _weekly_density(c,gs,members)
            all_density.extend(density)
            h.append('<details><summary>Weekly selected-fix coverage by season-year</summary>')
            h.append(_image(_save_svg(output,cid+'-density',_density_svg(density,c)),cid+' weekly coverage'))
            h.append('<p>Weekly bins are descriptive only; zero counts do not distinguish absent monitoring from failed fixes.</p></details></section>')
        h.append('</section>')
    h.append('<h2 id="groups">Computational map groups</h2><p>These are alternative map contexts, not additional independent animals or trajectories. Full-study MCP95 is a map-planning proxy and does not establish seasonal residence.</p>')
    for g in groups.values():
        gid = g['group_id']
        view = dict(g,windows=list(aggregate_windows(g['windows']).values()))
        h.append(f'<section class="group" id="{gid}"><h3>{gid} · {g["season"].title()} · {g["n_individuals"]} individuals · {g["n_bouts"]:,} bursts</h3>')
        h.append(f'<p>Grid: {g["grid_rows"]} × {g["grid_cols"]} cells; {g["width_km"]:.1f} × {g["height_km"]:.1f} km. {escape(g["spatial_violation_text"])}</p>')
        r = group_coverage[gid]
        h.append(f'<p>Member animals have {r["raw_fixes"]:,} native fixes in this season across years: {r["selected_fixes"]:,} selected ({_pct(r["selected_retention_pct"])}); {r["preserved_native_fixes"]:,} native fixes preserved ({_pct(r["native_preservation_pct"])}).</p>')
        h.append(_image(_save_svg(output,gid+'-map',_map([view],mcps,sexes=sexes)),gid+' trajectories and full-study MCP95','map'))
        h.append('<p class="detail">Dashed colored outlines are each individual’s full-study MCP95 hulls; matching solid lines connect its selected fixes within separate bursts. Colors identify individuals. MCP95 uses full-study observations, not just this season, and is not a habitat boundary.</p>')
        h.append(_image(_save_svg(output,gid+'-counts',_counts(view)),gid+' fixes per individual'))
        h.append(_animal_table(g['windows'], {i:r for (s,i),r in coverage.items() if s == g['season']}))
        h.append('</section>')
    h.append('<h2 id="individual-audit">All-individual audit</h2>')
    h.append(_table(['ID','Sex','Raw fixes','Bursts','Selected fixes','Native fixes preserved','Native fixes outside bursts','Seasons'],[
        [a['individual_id'],a.get('sex','unknown'),a['n_raw_fixes'],a['n_bouts'],a['n_selected_fixes'],a['n_source_fixes_preserved'],a['n_source_fixes_outside_selected_bouts'],', '.join(a['seasons']) or _status(a['status'])]
        for a in result['individuals']]))
    h.append('<p>Checkpoint: <code>'+escape(result['checkpoint_dir'])+'</code>. Export the checkpoint with the seasonal trajectory exporter, choosing the required collection and output folder. Use SPR-C01, SUM-C01 or AUT-C01 for other seasons. The matching exporter retains the three-fix rule. Arrays retain the established [row, col, spatial-move-index] convention; timestamps remain in sidecars. No feature maps or model fits are supplied by this selection.</p></body></html>')
    write_csv(output/'data'/'collection_weekly_density.csv', all_density)
    (output/'index.html').write_text('\n'.join(h))
