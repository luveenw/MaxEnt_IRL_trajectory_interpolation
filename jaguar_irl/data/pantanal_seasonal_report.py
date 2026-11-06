"""Offline season/collection report for the separate Pantanal seasonal pipeline.

The renderer writes external SVG figures under images/ and one canonical section
per group and collection. It does not select evidence or alter checkpoint data.
"""
from __future__ import annotations

import calendar
import csv
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from html import escape
import json
from pathlib import Path
import re

from pyproj import Transformer

from .pantanal_spatial import convex_hull
from .pantanal_metric_notes import METRIC_NOTES_HTML

# Muted Set2-inspired categories for identities; color is unnecessary for counts.
# Extra hues extend the eight-color family for larger seasonal collections.
COLORS = ('#579f8b','#cc805c','#7d8db3','#bf78a3','#8da94b','#b49b43',
          '#b39365','#858585','#6093ac','#a77a63','#927baa','#64935c','#b5767f')
CHART_COLOR = '#668c96'
# Nine samples from the standard viridis map, interpolated in SVG and cells.
VIRIDIS = ('#440154','#472d7b','#3b528b','#2c728e','#21918c',
           '#28ae80','#5ec962','#addc30','#fde725')


def _density_color(ratio):
    position=max(0, min(1, ratio))*(len(VIRIDIS)-1)
    index=min(int(position),len(VIRIDIS)-2)
    fraction=position-index
    first,last=VIRIDIS[index],VIRIDIS[index+1]
    rgb=[round(int(first[i:i+2],16)*(1-fraction)+int(last[i:i+2],16)*fraction)
         for i in (1,3,5)]
    linear=[v/255/12.92 if v/255<=.04045 else ((v/255+.055)/1.055)**2.4 for v in rgb]
    luminance=sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
    return '#%02x%02x%02x'%tuple(rgb), 'white' if luminance<.22 else '#152029'


CSS = '''
body{font:15px/1.5 system-ui,sans-serif;color:#26343b;margin:0 auto;padding:28px;max-width:1400px;background:white}h1{font-size:28px}h2{font-size:22px}h3{font-size:17px}a{color:#176575;text-decoration:none}a:hover{text-decoration:underline}section,nav{scroll-margin-top:18px}p{max-width:1200px}.muted,.detail{color:#566970;font-size:12px}.facts{display:flex;flex-wrap:wrap;gap:8px 26px;align-items:baseline;margin:12px 0}.facts p{margin:0}.outside{font-weight:700;font-style:italic;color:#b71924}.duplicate{font-weight:700;color:#95637e}.season-nav{display:grid;gap:20px}.season-panel{border:1px solid #c5d8d5;border-radius:9px;padding:16px}.season-panel h3{margin-top:0}.collection-nav-list{list-style:none;margin:0;padding:0;display:grid;gap:10px}.nav-card{border:1px solid #91beb6;border-radius:6px;padding:12px;background:transparent;font-weight:400}.nav-card.flagged{border-color:#d3a2b5}.nav-card[aria-current="location"]{background:#e7f3ef;font-weight:700}.nav-card.flagged[aria-current="location"]{background:#faedf2}.nav-card a{font-weight:400}.nav-card a[aria-current="location"]{font-weight:700;background:#e7f3ef}.nav-card[aria-current="location"]>a{font-weight:700}.nav-card .facts{gap:5px 16px}.spark{width:100%;max-width:900px}.chart-wrap{overflow-x:auto}.chart-wrap img{display:block;max-width:100%;height:auto}.spark-wrap img{min-width:360px}.density-chart img{max-width:none;min-width:850px}.group,.collection{border-top:1px solid #b7c8cd;margin-top:38px;padding-top:12px}.group-title{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.rank-pill,.season-chip{display:inline-block;background:#e5f2ef;color:#205a50;padding:3px 8px;border-radius:4px;font-size:13px}.rank-pill.flagged{background:#f7e4ed;color:#7d3656}.season-chip{font-size:12px}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;background:#eff4f4}th,td{padding:8px;border-bottom:1px solid #dce5e4;vertical-align:top}td ul{padding-left:18px;margin:0}.flag-note{border-left:4px solid #c894ab;background:#fff3f7;padding:12px}.metrics-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}details{margin:12px 0}summary{cursor:pointer;color:#176575}code{font-size:12px;overflow-wrap:anywhere}.subtrajectory-list{columns:2;column-gap:30px}.subtrajectory-list li{break-inside:avoid;padding-bottom:6px}.figures{display:grid;grid-template-columns:1fr 1fr;gap:18px}.figure{margin:14px 0}.figure img{width:100%;height:auto}.figure figcaption{font-size:12px;color:#566970}.map{max-width:950px}.float-nav{position:fixed;right:22px;bottom:22px;z-index:20;display:flex;flex-direction:column-reverse;align-items:flex-end;gap:8px}.float-nav button{border:1px solid #85ada6;border-radius:50%;width:48px;height:48px;background:#e5f2ef;font-size:22px;cursor:pointer}.float-links{display:flex;flex-direction:column;align-items:flex-end;gap:7px;opacity:0;visibility:hidden;transform:translateY(12px);transition:.16s}.float-nav:hover .float-links,.float-nav:focus-within .float-links,.float-nav.open .float-links{opacity:1;visibility:visible;transform:translateY(0)}.float-links a{background:#f1f8f6;border:1px solid #b9d2cc;border-radius:7px;padding:8px 12px;font-size:13px}:focus-visible{outline:2px solid #668c96;outline-offset:3px}@media(max-width:800px){body{padding:14px}.figures{grid-template-columns:1fr}.subtrajectory-list{columns:1}}@media(prefers-reduced-motion:reduce){.float-links{transition:none}}@media print{.float-nav{display:none}.group,.collection{break-before:page}}
'''
# Visual waypoints and metric hierarchy; system fonts keep the report offline.
CSS += """
body{background:#f7faf9;color:#24383e}h1,h2,h3{font-family:Georgia,"Times New Roman",serif;letter-spacing:-.025em}h1{font-size:38px;line-height:1.15;margin-bottom:18px}h2{font-size:29px}h3{font-size:24px}.season-nav{gap:34px}.season-panel{--accent:#438878;--wash:#e7f2ed;border:1px solid #cededa;border-top:6px solid var(--accent);background:white;padding:0 20px 20px;box-shadow:0 5px 18px #214a3b08}.season-panel>h3{background:var(--wash);padding:20px;margin:0 -20px 12px;border-radius:4px 4px 0 0;display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;font-size:30px}.season-panel[data-season="winter"]{--accent:#5684a3;--wash:#e9f1f8}.season-panel[data-season="spring"]{--accent:#9b7840;--wash:#faf0df}.season-panel[data-season="summer"]{--accent:#b56860;--wash:#f9eae5}.season-panel[data-season="autumn"]{--accent:#89739b;--wash:#f0eaf5}.collection,.group{background:white;padding:24px;border:1px solid #d0dfdd;border-top:6px solid #4f8f86;border-radius:10px;box-shadow:0 5px 20px #214a3b08;margin-top:48px}.group{border-top-color:#7189a3}.group-title{margin:-24px -24px 20px;padding:22px 24px;background:#edf5f2;border-radius:4px 4px 0 0;line-height:1.3}.group>.group-title{background:#eef2f7}.rank-pill{font-family:system-ui,sans-serif;font-size:16px;letter-spacing:0;padding:5px 10px}.season-chip{font-family:system-ui,sans-serif;letter-spacing:0}.facts{gap:12px 28px;margin:18px 0}.facts p{font-size:12px;color:#536970}.facts strong{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:21px;letter-spacing:-.04em;color:#233e44;font-variant-numeric:tabular-nums}.nav-card{background:transparent;padding:16px}.nav-card .facts strong{font-size:19px;font-weight:400}.nav-card[aria-current="location"] .facts strong{font-weight:700}.nav-card>a{font-size:16px}.nav-card .duplicate{font-size:12px}.group-title .section-icon{font-family:system-ui,sans-serif;font-size:23px}#ranking-tables>h2,#collections>h2,#individual-audit>h2{border-left:6px solid #608e85;background:#e8f1ee;padding:16px 20px;margin-top:48px;border-radius:0 7px 7px 0}.figure figcaption{padding:8px 0}.facts .detail{font-size:11px}.float-links a{box-shadow:0 2px 7px #214a3b0c}@media(max-width:800px){h1{font-size:30px}.group,.collection{padding:16px}.group-title{margin:-16px -16px 16px;padding:18px 16px}.facts strong{font-size:19px}}
"""
SEASON_ICONS={'winter':'❄️','spring':'🌼','summer':'☀️','autumn':'🍂'}
SCRIPT = '''<script>(()=>{const cards=[...document.querySelectorAll('.nav-card')],sections=[...document.querySelectorAll('section.collection,section.group')];function select(id){cards.forEach(c=>{const active=c.dataset.target===id;c.toggleAttribute('data-active',active);if(active)c.setAttribute('aria-current','location');else c.removeAttribute('aria-current')});document.querySelectorAll('.group-link').forEach(a=>{if(a.hash==='#'+id){a.setAttribute('aria-current','location')}else{a.removeAttribute('aria-current')}})}let pending=false;function update(){pending=false;const marker=Math.min(150,innerHeight/3),s=sections.find(s=>{const r=s.getBoundingClientRect();return r.top<=marker&&r.bottom>marker});select(s?s.id:'')}addEventListener('scroll',()=>{if(!pending){pending=true;requestAnimationFrame(update)}},{passive:true});addEventListener('hashchange',()=>select(location.hash.slice(1)));document.querySelectorAll('a[href^="#"]').forEach(a=>a.addEventListener('click',()=>select(a.hash.slice(1))));select(location.hash.slice(1));const nav=document.querySelector('.float-nav'),button=nav.querySelector('button');function opened(v){nav.classList.toggle('open',v);button.setAttribute('aria-expanded',String(v))}button.addEventListener('click',()=>opened(!nav.classList.contains('open')));nav.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>opened(false)));document.addEventListener('keydown',e=>{if(e.key==='Escape'){opened(false);if(nav.contains(document.activeElement))button.focus()}});document.addEventListener('click',e=>{if(!nav.contains(e.target))opened(false)})})();</script>'''


def _dt(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _slug(value):
    return re.sub(r'[^a-zA-Z0-9_-]+','-',str(value)).strip('-')


def _text(value):
    return escape(str(value if value is not None else '—'))


def _num(value, places=1):
    try: return f'{float(value):,.{places}f}'
    except (ValueError, TypeError): return '—'


def _date(value):
    return _dt(value).strftime('%Y-%m-%d %H:%M') if value else '—'


def _as_list(value):
    if value is None:return []
    if isinstance(value,str):
        if value.startswith('['):return json.loads(value)
        return [v for v in value.split(';') if v]
    return list(value)


def _windows(group):return list(group.get('windows',[]))

def _points(window):return window.get('source_points') or window.get('points') or []

def _season_name(value):return str(value).lower().replace('austral ','')


def _attribution(window, season):
    return [a for a in window.get('season_attributions',[]) if _season_name(a.get('season'))==_season_name(season)]


def _inside(when, window, season):
    attrs=_attribution(window,season)
    return any(_dt(a['core_start'])<=when<_dt(a['core_end']) for a in attrs)


def _coverage(groups, season):
    months=defaultdict(lambda:{'inside':False,'outside':False,'years':set()})
    years=set()
    for group in groups:
        for w in _windows(group):
            for point in _points(w):
                t=_dt(point['timestamp']);m=months[t.month];m['years'].add(t.year);years.add(t.year)
                m['inside' if _inside(t,w,season) else 'outside']=True
    return months,sorted(years)


def _month_order(groups, season):
    """Order month summaries from the configured season's buffered beginning.

    Attribution dates are authoritative, allowing renamed seasons, mid-month
    boundaries and buffers spanning arbitrary calendar months. Month summaries
    pool years, so each calendar month appears once in this cyclic order.
    """
    attrs=[a for g in groups for w in _windows(g) for a in _attribution(w,season)]
    if attrs:
        first=min(attrs,key=lambda a:_dt(a['core_start']))
        start=_dt(first.get('buffer_start',first['core_start'])).month
    else:
        dates=[_dt(p['timestamp']) for g in groups for w in _windows(g) for p in _points(w)]
        start=min(dates).month if dates else 1
    return [((start-1+offset)%12)+1 for offset in range(12)]


def _month_markup(groups,season):
    months,years=_coverage(groups,season)
    labels=[]
    for m in _month_order(groups,season):
        if m not in months:continue
        info=months[m]
        label=calendar.month_abbr[m]
        if info['outside']:label=f'<span class="outside">{label}</span>'
        labels.append(label)
    return ', '.join(labels)+(' ('+', '.join(map(str,years))+')' if years else '')


def _periods(group,season):
    entries=defaultdict(list)
    for w in _windows(group):
        for p in _points(w):
            t=_dt(p['timestamp']);entries[t.year,t.month].append(_inside(t,w,season))
    labels=[]
    for (year,month),inside in sorted(entries.items()):
        label=calendar.month_abbr[month]
        if not all(inside):label=f'<span class="outside">{label}</span>'
        label+=f' {year}'
        labels.append(label)
    return ', '.join(labels)


def _flags(row):
    text=row.get('violation_text') or row.get('weekly_violation_text') or ''
    codes=_as_list(row.get('violation_codes'))
    items=[str(x) for x in codes] if not text else [x.strip() for x in re.split(r'(?<=[.;])\s+(?=ID\s|Spatial|Density|Observed)',str(text)) if x.strip()]
    if not items:return ''
    if len(items)==1:return _text(items[0])
    return '<ul>'+''.join('<li>'+_text(x)+'</li>' for x in items)+'</ul>'


def _flagged(group):return bool(group.get('has_violations') or group.get('violation_codes') or group.get('candidate_list')=='relaxed')


def _table(headers,rows):
    return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+_text(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def _svg(width,height,body,title):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img"><title>{_text(title)}</title><rect width="100%" height="100%" fill="white"/><g font-family="system-ui,sans-serif" font-size="11" fill="#26343b">'+body+'</g></svg>'


def _save_svg(out,name,content):
    path=out/'images'/name;path.write_text(content,encoding='utf-8');return 'images/'+name


def _image(src,alt,css=''):
    return f'<div class="chart-wrap {css}"><img src="{escape(src,quote=True)}" alt="{escape(alt,quote=True)}" loading="lazy" decoding="async"/></div>'


def _collection_groups(collection,groups):return [groups[str(g)] for g in _as_list(collection.get('group_ids')) if str(g) in groups]


def _members(collection,groups):
    counts=Counter()
    for group in groups:
        counts.update({int(w['individual_id']) for w in _windows(group)})
    return counts


def _spark(groups,season,counts):
    ids=sorted(counts);cells=defaultdict(lambda:{'inside':False,'outside':False,'windows':set()})
    for g in groups:
        for w in _windows(g):
            i=int(w['individual_id'])
            for p in _points(w):
                t=_dt(p['timestamp']);item=cells[t.month,i];item['inside' if _inside(t,w,season) else 'outside']=True;item['windows'].add(w['window_id'])
    present={m for m,_ in cells};order=[m for m in _month_order(groups,season) if m in present]
    width=max(380,65+len(ids)*24);height=55+len(order)*20;body=''
    for col,i in enumerate(ids):
        x=55+col*24
        if counts[i]>1:body+=f'<rect x="{x-10}" y="3" width="20" height="{height-10}" fill="#fff7fa" stroke="#c894ab" stroke-width="1.2"/>'
        body+=f'<text x="{x}" y="14" text-anchor="middle" font-size="9">{i}</text>'
        if counts[i]>1:body+=f'<text x="{x}" y="25" text-anchor="middle" font-size="8" fill="#95637e">×{counts[i]}</text>'
    for row,m in enumerate(order):
        y=40+row*20;body+=f'<text x="20" y="{y+4}"><title>{calendar.month_name[m]}</title>{calendar.month_abbr[m]}</text>'
        for col,i in enumerate(ids):
            item=cells.get((m,i));x=55+col*24
            if not item:continue
            color='#668c96' if item['inside'] else '#b71924'
            body+=f'<rect x="{x-1.5}" y="{y-6}" width="3" height="12" rx="1" fill="{color}"><title>ID {i}, {calendar.month_name[m]}: {len(item["windows"])} distinct window(s); {counts[i]} group membership(s)</title></rect>'
            if item['outside'] and item['inside']:body+=f'<path d="M{x+3},{y-6} h2 v12 h-2" fill="#b71924"/>'
    return _svg(width,height,body,'Monthly observation coverage by individual; pink columns indicate duplicate group membership; red marks indicate observations outside the season core')


def _timeline(groups,season,counts,members=()):
    rows=[]
    ownership={(str(r.get('group_id')),str(r.get('window_id'))):r.get('selection_status',r.get('status','unspecified')) for r in members}
    for g in groups:
        for w in _windows(g):
            points=_points(w)
            if not points:continue
            times=sorted(_dt(p['timestamp']) for p in points)
            rows.append((times[0].year,int(w['individual_id']),str(g['group_id']),w,times))
    rows.sort(key=lambda r:(r[0],r[1],r[4][0],r[2]))
    width=1100;left=270;right=1060;body='';by_year=defaultdict(list)
    for row in rows:by_year[row[0]].append(row)
    cursor=70
    # Explicit legend remains visible when the SVG is embedded as an image;
    # nested SVG titles are supplementary, not required to recover metadata.
    body+='<rect x="5" y="10" width="30" height="10" fill="#668c96" fill-opacity=".28" stroke="#668c96"/><text x="43" y="19">Selected window</text>'
    body+='<rect x="195" y="10" width="30" height="10" fill="white" stroke="#95637e" stroke-dasharray="4 2"/><text x="233" y="19">Suppressed duplicate/overlapping window</text>'
    body+='<text x="5" y="38" font-size="10">Red observation marks: outside season core. Each year panel has its own date range.</text>'
    for year,items in by_year.items():
        lo=min(r[4][0] for r in items);hi=max(r[4][-1] for r in items);total=max(1,(hi-lo).total_seconds())
        def x(t):return left+(t-lo).total_seconds()/total*(right-left)
        # A complete header band precedes each panel, then row bands, then a gap.
        header_y=cursor;row_y=cursor+25
        body+=f'<text class="year-axis-label" x="{left}" y="{header_y}" font-size="10">{lo:%d %b %Y}</text><text class="year-axis-label" x="{right}" y="{header_y}" text-anchor="end" font-size="10">{hi:%d %b %Y}</text>'
        for index,(_,ident,gid,w,times) in enumerate(items):
            y=row_y+index*34;duplicate=counts[ident]>1;color='#95637e' if duplicate else '#26343b'
            status=ownership.get((gid,str(w['window_id'])),'unspecified')
            suppressed=status in ('duplicate_window','overlapping_window')
            label='suppressed duplicate' if status=='duplicate_window' else 'suppressed overlap' if status=='overlapping_window' else status
            body+=f'<text class="timeline-row-label" x="5" y="{y-1}" fill="{color}">ID {ident} · {_text(gid)}'+(' · repeated' if duplicate else '')+'</text>'
            body+=f'<text x="5" y="{y+11}" font-size="9" fill="#566970">{_text(label)}</text>'
            body+=f'<line x1="{left}" x2="{right}" y1="{y}" y2="{y}" stroke="#e1e7e8"/>'
            a,b=x(times[0]),x(times[-1]);style='fill="white" stroke="#95637e" stroke-dasharray="4 2"' if suppressed else 'fill="#668c96" fill-opacity=".28" stroke="#668c96"'
            body+=f'<rect class="window-span" data-selection-status="{escape(str(status),quote=True)}" x="{a:.2f}" y="{y-6}" width="{max(2,b-a):.2f}" height="12" {style}><title>{_text(w["window_id"])}: {times[0].isoformat()} to {times[-1].isoformat()}</title></rect>'
            for t in times:
                color='#668c96' if _inside(t,w,season) else '#b71924'
                body+=f'<line x1="{x(t):.2f}" x2="{x(t):.2f}" y1="{y-5}" y2="{y+5}" stroke="{color}" stroke-opacity="{.35 if suppressed else 1}" stroke-width="1"/>'
        cursor=row_y+len(items)*34+24
    return _svg(width,max(145,cursor),body,'Source-observation periods by individual, group and year; solid intervals are selected and dashed intervals are suppressed in export ownership')


def _rings(geometry):
    if geometry.get('type')=='Polygon':return geometry['coordinates'][:1]
    if geometry.get('type')=='MultiPolygon':return [p[0] for p in geometry['coordinates']]
    return []


def _map(groups,mcps,collection=False,sexes=None):
    sexes=sexes or {}
    project=Transformer.from_crs('EPSG:4326','EPSG:32721',always_xy=True)
    geoms={};all_xy=[]
    ids=sorted({int(w['individual_id']) for g in groups for w in _windows(g)})
    individual_colors={ident:COLORS[i%len(COLORS)] for i,ident in enumerate(ids)}
    for gi,g in enumerate(groups):
        paths=[];seen=set()
        for w in _windows(g):
            ident=int(w['individual_id'])
            if ident in seen:continue
            seen.add(ident)
            for ring in _rings(mcps.get(ident,{})):
                xy=[project.transform(*p[:2]) for p in ring];paths.append((ident,xy));all_xy.extend(xy)
        geoms[str(g['group_id'])]=paths
        if not collection:
            for w in _windows(g):
                all_xy.extend(project.transform(float(p['longitude']),float(p['latitude'])) for p in w.get('points',[]))
    if not all_xy:return _svg(800,150,'<text x="20" y="70">No MCP95 geometry available.</text>','MCP95 map unavailable')
    xmin=min(p[0] for p in all_xy);xmax=max(p[0] for p in all_xy);ymin=min(p[1] for p in all_xy);ymax=max(p[1] for p in all_xy)
    span=max(xmax-xmin,ymax-ymin,1000);pad=.06*span;xmin-=pad;xmax+=pad;ymin-=pad;ymax+=pad
    width=880;height=640;scale=min(720/(xmax-xmin),480/(ymax-ymin))
    def xy(p):return 65+(p[0]-xmin)*scale,535-(p[1]-ymin)*scale
    body='<text x="65" y="24" font-size="14">Full-study MCP95 geometry · EPSG:32721</text>'
    explanation=('Colors identify groups; solid envelopes enclose member MCP95s; dashed lines show individual MCP95s.'
                 if collection else 'Dashed: individual full-study MCP95 hulls. Solid: selected tracks. Matching colors identify animals.')
    body+=f'<text x="65" y="43" font-size="11">{explanation}</text>'
    for gi,g in enumerate(groups):
        gid=str(g['group_id']);color=COLORS[gi%len(COLORS)];paths=geoms[gid]
        if collection:
            points=[p for _,ring in paths for p in ring]
            if len(points)>=3:
                hull=convex_hull(points);path=' '.join(f'{x:.2f},{y:.2f}' for x,y in map(xy,hull))
                body+=f'<polygon points="{path}" fill="{color}" fill-opacity=".10" stroke="{color}" stroke-width="2"><title>{_text(gid)}: envelope of member full-study MCP95 polygons</title></polygon>'
        for ident,ring in paths:
            hull_color=color if collection else individual_colors[ident]
            points=' '.join(f'{x:.2f},{y:.2f}' for x,y in map(xy,ring));body+=f'<polygon points="{points}" fill="none" stroke="{hull_color}" stroke-dasharray="6 4" stroke-width="2"><title>ID {ident} MCP95 · {_text(gid)}</title></polygon>'
        if not collection:
            for wi,w in enumerate(_windows(g)):
                trajectories=defaultdict(list)
                for p in w.get('points',[]):trajectories[str(p.get('trajectory_id',''))].append(p)
                color=individual_colors[int(w['individual_id'])]
                for points in trajectories.values():
                    points.sort(key=lambda p:_dt(p['timestamp']));pairs=[xy(project.transform(float(p['longitude']),float(p['latitude']))) for p in points]
                    if not pairs:continue
                    sex=str(sexes.get(int(w['individual_id']),'unknown')).lower()
                    for px,py in pairs:
                        if sex in ('male','m'):
                            body+=f'<path d="M{px:.2f},{py-2:.2f} l-2,4 h4 z" fill="{color}"/>'
                        elif sex in ('female','f'):
                            body+=f'<circle cx="{px:.2f}" cy="{py:.2f}" r="1.8" fill="{color}"/>'
                        else:
                            body+=f'<path d="M{px-2:.2f},{py-2:.2f} l4,4 m0,-4 l-4,4" stroke="{color}"/>'
                    body+='<polyline points="'+' '.join(f'{x:.2f},{y:.2f}' for x,y in pairs)+f'" fill="none" stroke="{color}" stroke-width="1.6"/>'
                body+=f'<text x="{65+(wi%7)*110}" y="{584+(wi//7)*15}" fill="{color}" font-weight="700" font-size="12">ID {w["individual_id"]}</text>'
        else:body+=f'<text x="{65+(gi%6)*125}" y="{584+(gi//6)*15}" fill="{color}" font-weight="700" font-size="12">{_text(gid)}</text>'
    for k in range(5):
        x=65+(xmax-xmin)*scale*k/4;y=535-(ymax-ymin)*scale*k/4
        body+=f'<text x="{x:.2f}" y="552" text-anchor="middle">{(xmin+(xmax-xmin)*k/4)/1000:.1f}</text>'
        body+=f'<text x="57" y="{y+4:.2f}" text-anchor="end">{(ymin+(ymax-ymin)*k/4)/1000:.1f}</text>'
    body+='<text x="350" y="572">Easting (km)</text><text x="15" y="290" transform="rotate(-90 15 290)">Northing (km)</text>'
    return _svg(width,max(height,610+max(len(groups),max((len(_windows(g)) for g in groups),default=0))//6*15),body,'Group locations and full-study MCP95 polygons')


def _counts(group):
    windows=sorted(_windows(group),key=lambda w:int(w['individual_id']))
    values=[int(w.get('selected_fixes',len(w.get('points',[])))) for w in windows]
    width=max(900,len(windows)*34+380);height=270;chart_width=width-360
    max_count=max(values+[1]);body=''
    for i,(w,n) in enumerate(zip(windows,values)):
        x=50+i*(chart_width-70)/max(1,len(windows));h=150*n/max_count
        bw=min(26,(chart_width-70)/max(1,len(windows))-5)
        body+=f'<rect x="{x:.2f}" y="{190-h:.2f}" width="{bw:.2f}" height="{h:.2f}" fill="{CHART_COLOR}"/><text x="{x:.2f}" y="{184-h:.2f}">{n}</text><text x="{x:.2f}" y="210">{w["individual_id"]}</text>'
    body+=f'<text x="20" y="20">Retained fixes by individual</text><text x="{chart_width/2}" y="237" text-anchor="middle">Jaguar ID</text>'
    if values:
        low,high=min(values),max(values);bins=min(5,len(set(values)));step=(high-low)/bins if high>low else 1
        freq=[0]*bins
        for n in values:freq[min(bins-1,int((n-low)/step))]+=1
        maximum=max(freq);origin=chart_width+35;bw=230/bins
        body+=f'<text x="{origin}" y="20">Distribution across individuals</text>'
        for i,n in enumerate(freq):
            x=origin+i*bw;h=150*n/maximum
            body+=f'<rect x="{x:.2f}" y="{190-h:.2f}" width="{bw-3:.2f}" height="{h:.2f}" fill="#668c96"/><text x="{x+bw/2:.2f}" y="{184-h:.2f}" text-anchor="middle">{n}</text>'
            label=str(low) if bins==1 else f'{low+i*step:.0f}–{low+(i+1)*step:.0f}'
            body+=f'<text x="{x+bw/2:.2f}" y="210" text-anchor="middle" font-size="9">{label}</text>'
        body+=f'<text x="{origin+115}" y="237" text-anchor="middle">Retained fixes per jaguar</text>'
    return _svg(width,height,body,'Retained selected-point counts and histogram across individuals')


def _facts(collection,groups):
    counts=_members(collection,groups);duplicates={i:n for i,n in counts.items() if n>1};extra=sum(n-1 for n in duplicates.values());season=collection['season']
    duplicate_parts=[]
    if duplicates:duplicate_parts.append(f'{len(duplicates)} repeated IDs')
    if extra:duplicate_parts.append(f'{extra} extra memberships')
    duplicate_html=''
    if duplicate_parts:
        dup=' · '.join(duplicate_parts)+' ('+', '.join(f'{i}×{n}' for i,n in sorted(duplicates.items()))+')'
        duplicate_html='<p class="duplicate">'+_text(dup)+'</p>'
    periods=_month_markup(groups,season)
    return '<div class="facts"><p><strong>'+str(len(groups))+'</strong> 🗂️ groups</p><p><strong>'+str(len(counts))+'</strong> 🐆 unique individuals</p>'+duplicate_html+('<p>'+periods+'</p>' if periods else '')+'</div>'


def _group_links(groups,season):
    return ' · '.join(f'<a class="group-link" href="#group-{_slug(g["group_id"])}">{_text(g["group_id"])}</a> <span class="detail">({_periods(g,season)})</span>' for g in groups)


def _group_seasons(group):
    names=_as_list(group.get('season_names'))
    return ' / '.join(str(s).title() for s in names) if names else str(group.get('grouping_calendar_season') or group.get('season','')).title()


def _monday(when):
    return when.replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=when.weekday())


def _union_hours(intervals):
    total=0.;stop=None
    for start,end in sorted(intervals):
        if end<=start:continue
        if stop is None or start>stop:total+=(end-start).total_seconds()/3600
        elif end>stop:total+=(end-stop).total_seconds()/3600
        stop=max(stop,end) if stop is not None else end
    return total


def _weekly_density(collection,groups,members):
    """Selector retained-point counts over canonical windows; never raw fixes.

    Monday bins are half-open. Event identity is deduplicated per individual
    across selected memberships before assigning one season-year panel.
    """
    season=collection['season'];cid=collection['collection_id']
    lookup={(str(g['group_id']),str(w['window_id'])):w for g in groups for w in _windows(g)}
    bins=defaultdict(lambda:{'points':{},'windows':set(),'groups':set()})
    panels={};exposures=defaultdict(list);seen=set();memberships=_members(collection,groups)
    for row in members:
        if row.get('selection_status',row.get('status'))!='selected':continue
        key=str(row['group_id']),str(row['window_id']);w=lookup[key];ident=int(row['individual_id'])
        attrs=_attribution(w,season)
        if not attrs:raise ValueError(f'Missing season attribution for density window {key}')
        for attr in attrs:
            sy=int(attr.get('season_year',_dt(attr['core_start']).year))
            bstart=_dt(attr.get('buffer_start',attr['core_start']));bend=_dt(attr.get('buffer_end',attr['core_end']))
            if sy in panels:
                panels[sy]['start']=min(panels[sy]['start'],bstart);panels[sy]['end']=max(panels[sy]['end'],bend)
            else:panels[sy]={'start':bstart,'end':bend,'core_start':_dt(attr['core_start']),'core_end':_dt(attr['core_end'])}
            exposures[sy,ident].append((_dt(w['start']),_dt(w['end'])))
        for point in w.get('points',[]):
            when=_dt(point['timestamp'])
            identity=next(((field,str(point[field])) for field in ('source_event_key','source_row','event_id') if point.get(field) is not None),('timestamp',when.isoformat()))
            event_key=(ident,identity)
            if event_key in seen:continue
            seen.add(event_key)
            def distance(attr):
                start,end=_dt(attr['core_start']),_dt(attr['core_end'])
                bstart,bend=_dt(attr.get('buffer_start',attr['core_start'])),_dt(attr.get('buffer_end',attr['core_end']))
                return (not start<=when<end,not bstart<=when<bend,min(abs((when-start).total_seconds()),abs((when-end).total_seconds())),start)
            attr=min(attrs,key=distance);sy=int(attr.get('season_year',_dt(attr['core_start']).year));week=_monday(when)
            item=bins[sy,ident,week];item['points'][identity]=(when,_dt(attr['core_start'])<=when<_dt(attr['core_end']));item['windows'].add(str(w['window_id']));item['groups'].add(str(row['group_id']))
            # Preserve endpoint observations even for a configured boundary case.
            panels[sy]['start']=min(panels[sy]['start'],when);panels[sy]['end']=max(panels[sy]['end'],when+timedelta(microseconds=1))
    rows=[]
    for sy,panel in sorted(panels.items()):
        ids=sorted(ident for year,ident in exposures if year==sy)
        week=_monday(panel['start'])
        while week<panel['end']:
            end=week+timedelta(days=7)
            for ident in ids:
                item=bins.get((sy,ident,week),{'points':{},'windows':set(),'groups':set()});values=list(item['points'].values());core=sum(inside for _,inside in values);buffer=len(values)-core
                overlap=_union_hours((max(a,week),min(b,end)) for a,b in exposures[sy,ident]);partial=overlap<168-1e-9
                rows.append(dict(collection_id=cid,season=season,season_year=sy,individual_id=ident,week_start=week.isoformat(),week_end_exclusive=end.isoformat(),retained_fix_count=len(values),core_fix_count=core,buffer_fix_count=buffer,season_support='mixed' if core and buffer else 'buffer_only' if buffer else 'core_only' if core else 'none',selected_window_overlap_hours=round(overlap,6),partial_selected_week=partial,first_retained_fix=min((t for t,_ in values),default=None).isoformat() if values else '',last_retained_fix=max((t for t,_ in values),default=None).isoformat() if values else '',group_ids=sorted(item['groups']),window_ids=sorted(item['windows']),group_membership_count=memberships[ident]))
            week=end
    assert sum(r['retained_fix_count'] for r in rows)==len(seen)
    return rows


def _density_svg(rows,collection):
    panels=defaultdict(list)
    for row in rows:panels[row['season_year']].append(row)
    peak=max((r['retained_fix_count'] for r in rows),default=0)
    max_columns=max((len({r['week_start'] for r in rs}) for rs in panels.values()),default=1)
    width=max(850,160+46*max_columns);left=125;body='';cursor=150
    body+=f'<text x="8" y="20" font-size="13">Retained selector fixes · count scale 0–{peak} across all panels</text>'
    body+='<text x="8" y="40" font-size="10">Dashed border: partial selected-window exposure. Red underline: buffer-only observations; split underline: mixed core/buffer.</text>'
    body+='<text x="8" y="57" font-size="10">Blank cell: no retained selected observations. Monday-start bins are half-open; counts are not coverage percentages.</text>'
    stops=''.join(f'<stop offset="{i/(len(VIRIDIS)-1)*100:g}%" stop-color="{color}"/>' for i,color in enumerate(VIRIDIS))
    body+=f'<defs><linearGradient id="fix-count-scale">{stops}</linearGradient></defs>'
    body+='<text x="8" y="82" font-size="11">Retained fixes per individual per calendar week</text><rect x="300" y="70" width="200" height="12" fill="url(#fix-count-scale)"/>'
    for fraction in (0,.25,.5,.75,1):
        x=300+200*fraction
        body+=f'<line x1="{x}" x2="{x}" y1="82" y2="86" stroke="#566970"/><text x="{x}" y="100" text-anchor="middle" font-size="10">{peak*fraction:.0f}</text>'
    body+='<text x="8" y="120" font-size="10">Viridis: purple = fewer fixes; teal = intermediate; yellow = more fixes. One scale per collection; cell numbers give exact counts.</text>'
    for sy,rs in sorted(panels.items()):
        weeks=sorted({r['week_start'] for r in rs});ids=sorted({r['individual_id'] for r in rs});lookup={(r['individual_id'],r['week_start']):r for r in rs}
        body+=f'<text x="8" y="{cursor}" font-size="13">{_text(str(collection["season"]).title())} {sy} · season starting year</text>'
        header=cursor+15;top=header+90
        for j,week in enumerate(weeks):
            x=left+j*46+23
            body+=f'<text x="{x}" y="{header}" text-anchor="end" transform="rotate(-60 {x} {header})" font-size="9">{week[:10]}</text>'
        for i,ident in enumerate(ids):
            y=top+i*29;n=lookup[ident,weeks[0]]['group_membership_count'];label=f'ID {ident}'+(f' ×{n}' if n>1 else '')
            body+=f'<text x="8" y="{y+18}" fill="{"#95637e" if n>1 else "#26343b"}">{label}</text>'
            for j,week in enumerate(weeks):
                r=lookup[ident,week];n=r['retained_fix_count'];x=left+j*46
                body+=f'<rect x="{x}" y="{y}" width="44" height="26" fill="#fafcfc" stroke="#e0e8e8"/>'
                if not n:continue
                ratio=n/max(1,peak);fill,ink=_density_color(ratio)
                dash=' stroke-dasharray="3 2"' if r['partial_selected_week'] else ''
                body+=f'<rect x="{x}" y="{y}" width="44" height="26" fill="{fill}" stroke="#4b6870"{dash}/><text x="{x+22}" y="{y+18}" text-anchor="middle" fill="{ink}">{n}</text>'
                if r['buffer_fix_count']:
                    start=x if not r['core_fix_count'] else x+22
                    body+=f'<line x1="{start}" x2="{x+44}" y1="{y+25}" y2="{y+25}" stroke="#b71924" stroke-width="3"/>'
        cursor=top+len(ids)*29+40
    if not rows:body+='<text x="8" y="100">No canonically selected observations.</text>'
    return _svg(width,max(145,cursor),body,'Individual-by-calendar-week retained selector fix counts, deduplicated over canonically selected collection windows')


def _group_table(groups):
    rows=[]
    for g in groups:
        gid=str(g['group_id']);style=' flagged' if _flagged(g) else ''
        rows.append([f'<a class="rank-pill{style}" href="#group-{_slug(gid)}">#{_text(g.get("rank"))}</a>',f'<a href="#group-{_slug(gid)}">{_text(gid)}</a>',_text(_group_seasons(g)),_text(g.get('n_individuals',len(_windows(g)))),_text(g.get('ids','')),_num(g.get('total_fixes'),0),_num(g.get('point_count_cv'),3),_num(g.get('length_evenness'),3),f'{_num(g.get("area_km2"),0)} km² ({_num(g.get("width_km"))} × {_num(g.get("height_km"))} km)',_flags(g)])
    headers=['Rank','Group','Season','Individuals','IDs','Fixes','CV ↓','Jain ↑','Map rectangle','Flags']
    first=_table(headers,rows[:7]);tail=''
    if len(rows)>7:tail=f'<details><summary>Show remaining {len(rows)-7} groups</summary>'+_table(headers,rows[7:])+'</details>'
    return first+tail


def write_report(output_dir,result):
    out=Path(output_dir).resolve();(out/'images').mkdir(parents=True,exist_ok=True)
    groups={str(g['group_id']):g for g in result.get('groups',[])}
    collections=sorted(result.get('collections',[]),key=lambda c:(_season_name(c['season']),int(c.get('rank',0)),str(c['collection_id'])))
    by_season=defaultdict(list)
    for c in collections:by_season[_season_name(c['season'])].append(c)
    mcps={int(f['properties'].get('individual_id',f['properties'].get('id'))):f['geometry'] for f in result.get('mcps_geojson',{}).get('features',[])}
    sexes={int(r['individual_id']):r.get('sex','unknown') for r in result.get('individuals',[])}
    members=defaultdict(list)
    for row in result.get('collection_members',[]):members[str(row['collection_id'])].append(row)
    assets={};density_rows=[];density_by_collection={}
    for c in collections:
        cid=str(c['collection_id']);gs=_collection_groups(c,groups);counts=_members(c,gs)
        density_by_collection[cid]=_weekly_density(c,gs,members[cid]);density_rows.extend(density_by_collection[cid])
        assets[cid]={'spark':_save_svg(out,f'collection_{_slug(cid)}_spark.svg',_spark(gs,c['season'],counts)), 'timeline':_save_svg(out,f'collection_{_slug(cid)}_timeline.svg',_timeline(gs,c['season'],counts,members[cid])), 'map':_save_svg(out,f'collection_{_slug(cid)}_map.svg',_map(gs,mcps,True)), 'density':_save_svg(out,f'collection_{_slug(cid)}_weekly_density.svg',_density_svg(density_by_collection[cid],c))}
    (out/'data').mkdir(exist_ok=True)
    density_fields=['collection_id','season','season_year','individual_id','week_start','week_end_exclusive','retained_fix_count','core_fix_count','buffer_fix_count','season_support','selected_window_overlap_hours','partial_selected_week','first_retained_fix','last_retained_fix','group_ids','window_ids','group_membership_count']
    with (out/'data'/'collection_weekly_density.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=density_fields);writer.writeheader()
        for row in density_rows:writer.writerow({k:json.dumps(v) if isinstance(v,list) else v for k,v in row.items()})
    parts=['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pantanal seasonal group collections</title><style>'+CSS+'</style></head><body id="top">','<h1>Pantanal seasonal group collections</h1>','<p><a href="#season-navigation">🗓️ Seasons</a> · <a href="#collections">📋 Collections</a> · <a href="#ranking-tables">🌎 Group rankings</a> · <a href="#individual-audit">Individual audit</a></p>',
           '<p>Collections combine spatially bounded groups to maximize the number of represented jaguars within each seasonal sampling period. Groups retain their quality and spatial rankings. Membership counts describe selected evidence; informative plain-MaxEnt route counts are determined by export diagnostics.</p>',
           '<details><summary>Selection, seasons and interpretation</summary><p>Observed fixes are selected near a two-hour interval, with a 1.5–2.5-hour regular band. Gaps greater than four hours split trajectories. Retained endpoints of tolerated longer intervals share a period-wide 20% budget; subtrajectories contain at least five selected observations, and short-fragment loss is limited to 5% during selection. Main windows meet the configured schedule-density and observed-span thresholds. Measured temporal or spatial relaxations remain flagged.</p><p>Season intervals use exact date boundaries; eligible windows may use adjoining buffer dates. Red bold italic month names indicate that some included observations fall outside the season core; other observations in the same month may fall within it. Pink chart columns and repeated-ID labels identify animals belonging to several groups. An extra membership is each occurrence after an animal’s first group membership.</p><p>Source timestamps identify actual observation coverage. A shaded first-to-last span does not imply uninterrupted telemetry. MCP95 polygons use full-study observations; collection envelopes outline member polygons and are spatial summaries. Export ownership records identify which group/window evidence is included when memberships overlap. All versions of one animal must retain the same training/validation/test assignment.</p></details>',
           '<nav id="season-navigation" aria-label="Seasonal collection navigation"><h2>🗓️ Seasonal collections</h2><div class="season-nav">']
    seasons=result.get('seasons') or [{'name':s} for s in ('autumn','winter','spring','summer')]
    for definition in seasons:
        season=_season_name(definition['name']);items=by_season.get(season,[])
        bounds=''
        if 'start_month' in definition:
            last_day=datetime(2000,int(definition['end_month']),int(definition['end_day']))-timedelta(days=1)
            bounds=f'{calendar.month_abbr[int(definition["start_month"])]} {definition["start_day"]} → {calendar.month_abbr[last_day.month]} {last_day.day}'
        parts.append(f'<section class="season-panel" data-season="{_text(season)}" id="season-{_slug(season)}"><h3>{SEASON_ICONS.get(season,"🗓️")} {_text(season.title())} <span class="detail">{_text(bounds)}</span></h3><p class="detail">{_text(definition.get("description",""))}</p><ol class="collection-nav-list">')
        for c in items:
            cid=str(c['collection_id']);gs=_collection_groups(c,groups);flag=' flagged' if any(_flagged(g) for g in gs) else ''
            parts.append(f'<li class="nav-card{flag}" data-target="collection-{_slug(cid)}"><a href="#collection-{_slug(cid)}">Collection {_text(c.get("rank"))} · {_text(cid)}</a>'+_facts(c,gs)+_image(assets[cid]['spark'],'Compact monthly coverage for '+cid,'spark-wrap')+'<p>'+_group_links(gs,season)+'</p></li>')
        if not items:parts.append('<li>No eligible collection.</li>')
        parts.append('</ol></section>')
    parts.append('</div></nav><section id="ranking-tables"><h2>🌎 Group rankings</h2><p><strong>Reading the ranks:</strong> group ranks are unique across the report. Main groups precede relaxed groups; within each category, ranking prioritizes total retained fixes multiplied by Jain’s index, followed by schedule density, irregular-endpoint fraction and map area. Collection ranks restart within each season and prioritize unique-animal coverage, fewer repeated memberships, fewer groups and constituent group ranks. Every retained collection covers the generated eligible animal union; the bounded greedy search does not establish a minimum-group optimum.</p>')
    for kind,label in [('main','Main groups'),('relaxed','Relaxed groups')]:
        subset=sorted([g for g in groups.values() if g.get('candidate_list','main')==kind],key=lambda g:(int(g.get('rank',0)),str(g['group_id'])))
        parts.append('<h3>'+label+'</h3>'+(_group_table(subset) if subset else '<p>No groups.</p>'))
    parts.append('</section><div id="collections"><h2>📋 Collection details</h2></div>')
    for c in collections:
        cid=str(c['collection_id']);season=c['season'];gs=_collection_groups(c,groups)
        parts.append(f'<section class="collection" id="collection-{_slug(cid)}"><h2 class="group-title"><span class="section-icon" aria-hidden="true">📋</span><span class="rank-pill">#{_text(c.get("rank"))}</span>{_text(cid)} <span class="season-chip">{_text(str(season).title())}</span></h2>'+_facts(c,gs)+'<p>'+_group_links(gs,season)+'</p>')
        parts.append('<figure class="figure map">'+_image(assets[cid]['map'],'Full-study MCP95 envelopes of groups in '+cid)+'<figcaption>Solid envelopes enclose each group’s member MCP95 polygons; dashed outlines show individual full-study MCP95s.</figcaption></figure>')
        parts.append('<figure class="figure">'+_image(assets[cid]['timeline'],'Detailed observation windows for '+cid)+'<figcaption>Each row represents one individual’s group window. Solid intervals identify selected export windows; dashed outlines identify suppressed duplicate or overlapping windows. Observation marks outside the season core are red. Year panels have separate date ranges. Exact dates, years and ownership appear in the table below.</figcaption></figure>')
        parts.append('<details class="density-view"><summary>Optional weekly density view · retained selector counts</summary><p>Only canonically selected collection memberships contribute. Repeated source events are counted once per animal. Cell numbers and viridis shading encode the retained fix count for one individual in one calendar week: purple means fewer fixes and yellow means more. The labeled color bar spans zero to the largest count in this collection, with the same scale across all its season-year panels. Different collections can have different maxima; counts may exceed the 85-fix seven-day reference under the interval tolerance. Dashed cells indicate less than 168 hours of selected-window envelope within the calendar week. This envelope is not continuous telemetry coverage. Red underlines indicate buffer-only observations; half-width red underlines indicate mixed core/buffer observations. Blank cells mean no retained selected observations.</p>'+_image(assets[cid]['density'],'Weekly retained selector point counts for '+cid,'density-chart')+'<p><a href="data/collection_weekly_density.csv">Exact week dates, counts and exposure diagnostics (CSV; all collections)</a></p></details>')
        window_lookup={(str(g['group_id']),str(w['window_id'])):w for g in gs for w in _windows(g)}
        period_rows=[]
        for row in sorted(members[cid],key=lambda r:(int(r['individual_id']),str(r.get('window_start',r.get('window_id',''))),str(r.get('group_id','')))):
            w=window_lookup.get((str(row.get('group_id')),str(row.get('window_id'))),{})
            points=_points(w);times=sorted(_dt(p['timestamp']) for p in points)
            start=row.get('window_start') or w.get('start');end=row.get('window_end') or w.get('end')
            observed=f'{_date(times[0])} → {_date(times[-1])}' if times else '—'
            period_rows.append([_text(row['individual_id']),_text(row.get('group_id')),_text(row.get('window_id')),_date(start),_date(end),observed,_text(row.get('selection_status',row.get('status','unspecified')))])
        parts.append(_table(['ID','Group','Window','Window start','Window end','Observed first → last','Export ownership'],period_rows))
        parts.append('<h3>Subtrajectory membership and export ownership</h3><p class="detail">IDs below refer to selector subtrajectories. The exporter manifest links these selections to fine and two-hour export fragments and grid arrays; the fragment boundaries can differ between representations.</p><ul class="subtrajectory-list">')
        for row in sorted(members[cid],key=lambda r:(int(r['individual_id']),str(r.get('window_id','')),str(r.get('group_id','')))):
            status=row.get('selection_status',row.get('status','unspecified'));ids=_as_list(row.get('selector_subtrajectory_ids'))
            parts.append(f'<li>ID <strong>{_text(row["individual_id"])}</strong> · <a href="#group-{_slug(row.get("group_id",""))}">{_text(row.get("group_id"))}</a> · {_text(status)}<br><code>{_text(row.get("window_id"))}</code><ul>'+''.join('<li><code>'+_text(i)+'</code></li>' for i in ids)+'</ul></li>')
        if not members[cid]:parts.append('<li>No collection-member manifest rows were supplied.</li>')
        parts.append('</ul><p><a href="#season-navigation">Back to seasons</a></p></section>')
    for gid,g in sorted(groups.items(),key=lambda item:(item[1].get('candidate_list','main'),int(item[1].get('rank',0)),item[0])):
        style=' flagged' if _flagged(g) else '';map_path=_save_svg(out,f'group_{_slug(gid)}_map.svg',_map([g],mcps,sexes=sexes));count_path=_save_svg(out,f'group_{_slug(gid)}_counts.svg',_counts(g))
        parts.append(f'<section class="group" id="group-{_slug(gid)}"><h2 class="group-title"><span class="section-icon" aria-hidden="true">📍</span><span class="rank-pill{style}">#{_text(g.get("rank"))}</span>{_text(gid)} <span class="season-chip">{_text(_group_seasons(g))}</span></h2><div class="facts"><p><strong>{len(_windows(g))}</strong> 🐆 individuals</p><p><strong>{_num(g.get("area_km2"),0)} km² · {_num(g.get("n_grid_cells"),0)} cells</strong> 🗺️ <span class="detail">({_num(g.get("width_km"))} × {_num(g.get("height_km"))} km)</span></p><p><strong>{_num(g.get("selected_span_days"))} days</strong> <span class="detail">({_date(g.get("selected_start"))} → {_date(g.get("selected_end"))})</span></p><p>CV {_num(g.get("point_count_cv"),3)} · Jain {_num(g.get("length_evenness"),3)}</p></div>')
        parts.append('<div class="facts"><p>'+_text(g.get('n_males','—'))+' males · '+_text(g.get('n_females','—'))+' females</p><p><strong>'+_num(g.get('full_span_days'))+' full-study days</strong> <span class="detail">('+_date(g.get('full_start'))+' → '+_date(g.get('full_end'))+')</span></p><p><strong>'+_num(g.get('shared_week_overlap_days'),2)+' days</strong> <span class="detail">intersection of individual selected spans</span></p></div>')
        if _flagged(g):parts.append('<div class="flag-note"><strong>Selection flags</strong>'+_flags(g)+'</div>')
        parts.append('<div class="figures"><figure class="figure">'+_image(map_path,'MCP95 polygons and selected trajectories for '+gid)+'</figure><figure class="figure">'+_image(count_path,'Retained fixes per individual for '+gid)+'</figure></div>')
        rows=[]
        for w in sorted(_windows(g),key=lambda w:int(w['individual_id'])):
            rows.append([_text(w['individual_id']),_text(w.get('window_id')),_date(w.get('observed_start',w.get('start'))),_date(w.get('observed_end',w.get('end'))),_num(w.get('duration_days'),2),_text(w.get('selected_fixes')),_text(w.get('n_subtrajectories')),_flags(w)])
        parts.append(_table(['ID','Window','First selected fix','Last selected fix','Span (days)','Fixes','Subtrajectories','Flags'],rows)+'<p><a href="#season-navigation">Back to seasons</a> · <a href="#ranking-tables">Back to rankings</a></p></section>')
    parts.append('<section id="individual-audit"><h2>Individual coverage audit</h2>')
    audits=result.get('individuals',[])
    if audits:
        fields=[f for f in ('individual_id','study','tracking_span_days','qualifying_windows','group_membership_reason','protected_exclusion_text') if any(f in r for r in audits)]
        parts.append(_table(fields,[[_text(r.get(f)) for f in fields] for r in audits]))
        for audit in audits:
            diagnostics=audit.get('season_diagnostics',{})
            if not diagnostics:continue
            seasonal_rows=[]
            for season,detail in diagnostics.items():
                seasonal_rows.append([_text(str(season).title()),_text(detail.get('scanned_windows')),_text(detail.get('main_qualifying_windows')),_text(detail.get('relaxed_qualifying_windows')),_text(detail.get('protected_rejected_windows')),_text(detail.get('summary',''))])
            parts.append('<details><summary>ID '+_text(audit.get('individual_id'))+' · seasonal eligibility and exclusion evidence</summary>'+_table(['Season','Scanned windows','Main qualifying','Relaxed qualifying','Protected-rule rejections','Evidence'],seasonal_rows)+'</details>')
    parts.append('</section>'+METRIC_NOTES_HTML+'<details><summary>Run configuration and checkpoint</summary><p><code>'+_text(result.get('checkpoint_dir',''))+'</code></p><pre>'+_text(json.dumps(result.get('config',{}),indent=2,default=str))+'</pre></details><p class="detail">Season source: <a href="https://www.climatestotravel.com/climate/brazil/pantanal">Climates to Travel: Pantanal</a>. Exact computational boundaries and buffer lengths are recorded in the run configuration and checkpoint.</p>')
    season_shortcuts=''.join(f'<a href="#season-{_slug(_season_name(d["name"]))}">{_text(str(d["name"]).title())}</a>' for d in seasons)
    parts.append('<nav class="float-nav" aria-label="Page shortcuts"><button aria-expanded="false" aria-controls="float-links" aria-label="Toggle page shortcuts">☰</button><div class="float-links" id="float-links"><a href="#top">↑ Top</a><a href="#season-navigation">🗓️ Seasons</a>'+season_shortcuts+'<a href="#collections">📋 Collections</a><a href="#ranking-tables">🌎 Tables</a></div></nav>'+SCRIPT+'</body></html>')
    path=out/'index.html';path.write_text('\n'.join(parts),encoding='utf-8');return path
