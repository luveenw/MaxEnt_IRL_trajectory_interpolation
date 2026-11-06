"""Build a comparison page from independently generated seasonal report folders.

python -m jaguar_irl.data.compare_pantanal_sampling_windows
"""
import argparse
import csv
from html import escape
import json
import os
from pathlib import Path

from .movement_processor_pantanal import ROOT
from .pantanal_seasonal_report import CSS


def build_comparison(report_dirs, output_dir):
    output=Path(output_dir).resolve();output.mkdir(parents=True,exist_ok=True)
    (output/'data').mkdir(exist_ok=True)
    reports=[];rows=[];ledger=[];reference=None
    for directory in report_dirs:
        directory=Path(directory).resolve()
        r=json.loads((directory/'selection_manifest.json').read_text())
        config=r['config'];days=config['temporal']['week_days']
        contract=(r['provenance']['source_sha256'],r['seasons'],config['season_buffer_days'],config['spatial'])
        if reference is None:reference=contract
        if contract!=reference:raise ValueError('Comparison requires matching source, season, buffer and spatial settings')
        href=Path(os.path.relpath(directory/'index.html',output)).as_posix()
        reports.append((days,href))
        all_ids=set()
        for definition in r['seasons']:
            season=definition['name']
            gs=[g for g in r['groups'] if season in g['season_names']]
            ids={w['individual_id'] for g in gs for w in g['windows']};all_ids.update(ids)
            main_ids={w['individual_id'] for g in gs if g['candidate_list']=='main' for w in g['windows']}
            cs=[c for c in r['collections'] if c['season']==season]
            covered=max((c['n_individuals'] for c in cs),default=0)
            assert covered==len(ids)
            rows.append(dict(sampling_days=days,season=season,main_individuals=len(main_ids),covered_individuals=covered,
                relaxed_added_individuals=len(ids-main_ids),groups=len(gs),collections=len(cs),
                individual_ids=';'.join(map(str,sorted(ids))),report=href,
                min_observed_span_days=config['temporal']['min_week_observed_span_days']))
            for animal in r['individuals']:
                ident=animal['individual_id'];d=animal['season_diagnostics'][season]
                ledger.append(dict(sampling_days=days,season=season,individual_id=ident,
                    represented=ident in ids,main_group_member=ident in main_ids,
                    main_qualifying_windows=d['main_qualifying_windows'],
                    relaxed_qualifying_windows=d['relaxed_qualifying_windows'],
                    scanned_windows=d['scanned_windows'],summary=d['summary']))
    reports.sort()
    for name,data in [('window_coverage_comparison',rows),('individual_window_eligibility',ledger)]:
        with (output/'data'/f'{name}.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    options=''.join(f'<option value="{escape(h,quote=True)}">{d:g} days</option>' for d,h in reports)
    cards=''.join(f'<a class="report-link" href="{escape(h,quote=True)}" target="_blank">🗓️ {d:g}-day report ↗</a>' for d,h in reports)
    body='<h1>Pantanal sampling-window comparison</h1><p>Each report searches the entire season plus seven-day buffers for individual windows of the stated duration. Cadence, segmentation, short-fragment loss, spatial rules and ranking are held fixed. Main schedule counts scale with duration; the main observed-span requirement scales as duration × 6.5/7. Relaxed groups retain their measured exceptions.</p><p>Longer windows can rescue fragmented evidence through pooled budgets or add irregular observations that prevent eligibility. Covered animals are unique group members, including relaxed additions. Counts precede export-specific route exclusions.</p><div class="report-links">'+cards+'</div>'
    body+='<h2>🐆 Individuals covered per season</h2><div class="table-wrap"><table><thead><tr><th>Window</th><th>Winter</th><th>Spring</th><th>Summer</th><th>Autumn</th><th>Union across seasons</th></tr></thead><tbody>'
    for days,href in reports:
        rs=[r for r in rows if r['sampling_days']==days];by_season={r['season']:r for r in rs}
        union={i for r in rs for i in r['individual_ids'].split(';') if i}
        body+=f'<tr><td><a href="{escape(href,quote=True)}">{days:g} days</a></td>'+''.join(f'<td><strong>{by_season[s]["covered_individuals"]}</strong> <span class="detail">({by_season[s]["main_individuals"]} main + {by_season[s]["relaxed_added_individuals"]} relaxed additions)</span></td>' for s in ('winter','spring','summer','autumn'))+f'<td>{len(union)}</td></tr>'
    body+='</tbody></table></div><p><a href="data/window_coverage_comparison.csv">Coverage details CSV</a> · <a href="data/individual_window_eligibility.csv">Per-individual eligibility CSV</a></p><h2>🔎 View reports side by side</h2><p>Choose independently in each pane. Each report has its own navigation, checkpoints, grids and collection IDs; interpret those IDs within that report.</p><div class="panes">'
    for i in range(2):
        chosen=reports[min(i,len(reports)-1)][1]
        body+=f'<div><label for="report-{i}">Report {i+1}</label> <select id="report-{i}">{options}</select><iframe id="pane-{i}" title="Sampling report {i+1}" src="{escape(chosen,quote=True)}" loading="lazy"></iframe></div>'
    body+='</div><script>'+''.join(f'const s{i}=document.getElementById("report-{i}");s{i}.value={json.dumps(reports[min(i,len(reports)-1)][1])};s{i}.addEventListener("change",()=>document.getElementById("pane-{i}").src=s{i}.value);' for i in range(2))+'</script>'
    extra='.report-links{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}.report-link{padding:16px 20px;background:#e5f2ef;border:1px solid #9bbfb6;border-radius:8px;font-size:19px}.panes{display:grid;grid-template-columns:1fr 1fr;gap:16px}iframe{display:block;width:100%;height:80vh;border:2px solid #a4bdb7;border-radius:8px;margin-top:10px}select{padding:8px;font:inherit}@media(max-width:900px){.panes{grid-template-columns:1fr}}'
    (output/'index.html').write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pantanal window comparison</title><style>'+CSS+extra+'</style></head><body>'+body+'</body></html>')
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reports',nargs='+',type=Path,default=[ROOT/'analysis/pantanal_seasonal_selection',*(ROOT/f'analysis/pantanal_window_comparison/{d}d' for d in (10,15,20))])
    p.add_argument('--output',type=Path,default=ROOT/'analysis/pantanal_window_comparison')
    a=p.parse_args();build_comparison(a.reports,a.output);print(a.output/'index.html')

if __name__=='__main__':main()
