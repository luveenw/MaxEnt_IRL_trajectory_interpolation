"""Report contract tests: canonical links, boundary labels and evidence ownership."""
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
import xml.etree.ElementTree as ET

from .pantanal_seasonal_report import write_report,_month_markup,_spark,_timeline,_month_order


def fixtures():
    def window(ident,start):
        times=[datetime.fromisoformat(start),datetime.fromisoformat(start).replace(day=16)]
        points=[dict(timestamp=t,individual_id=ident,longitude=-57+.01*j,latitude=-17,trajectory_id=f'{ident}-s01') for j,t in enumerate(times)]
        return dict(individual_id=ident,window_id=f'w{ident}',points=points,source_points=points,
                    observed_start=times[0],observed_end=times[-1],start=times[0],end=times[-1],
                    selected_fixes=2,n_subtrajectories=1,duration_days=2,
                    season_attributions=[dict(season='winter',core_start='2020-05-15T00:00:00',core_end='2020-08-15T00:00:00')])
    one=window(12,'2020-05-14T00:00:00');two=window(13,'2020-05-15T00:00:00');three=window(14,'2020-05-15T00:00:00')
    groups=[dict(group_id='G01',rank=1,season='winter',candidate_list='main',windows=[one,two],n_individuals=2,ids='12;13'),
            dict(group_id='G02',rank=2,season='winter',candidate_list='relaxed',windows=[one,three],n_individuals=2,ids='12;14',has_violations=True,violation_codes=['span','density'])]
    collections=[dict(collection_id='WIN-C01',season='winter',rank=1,group_ids=['G01','G02']),dict(collection_id='WIN-C02',season='winter',rank=2,group_ids=['G01'])]
    members=[dict(collection_id='WIN-C01',group_id='G01',window_id='w12',individual_id=12,selection_status='selected',selector_subtrajectory_ids=['12-s01']),dict(collection_id='WIN-C01',group_id='G02',window_id='w12',individual_id=12,selection_status='duplicate_window',selector_subtrajectory_ids=['12-s01'])]
    geometry={'type':'Polygon','coordinates':[[[-57.1,-17.1],[-56.9,-17.1],[-56.9,-16.9],[-57.1,-17.1]]]}
    return dict(groups=groups,collections=collections,collection_members=members,seasons=[dict(name='winter',start_month=5,start_day=15,end_month=8,end_day=15,description='Dry')],mcps_geojson={'features':[{'properties':{'individual_id':i},'geometry':geometry} for i in [12,13,14]]},individuals=[{'individual_id':12,'sex':'male'},{'individual_id':13,'sex':'female'}])


class Links(HTMLParser):
    def __init__(self):super().__init__();self.ids=[];self.links=[];self.images=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='a' and a.get('href','').startswith('#'):self.links.append(a['href'][1:])
        if tag=='img':self.images.append(a['src'])


def test_report_has_canonical_sections_complete_links_and_external_valid_svg(tmp_path):
    path=write_report(tmp_path,fixtures());html=path.read_text();parser=Links();parser.feed(html)
    assert len(parser.ids)==len(set(parser.ids))
    assert set(parser.links)<=set(parser.ids)
    assert parser.ids.count('group-G01')==1
    assert 'duplicate_window' in html and '12-s01' in html
    assert '1 repeated IDs · 1 extra memberships (12×2)' in html
    assert '(buffer dates)' not in html and 'Seasonal collections' in html
    assert 'data:image' not in html and parser.images
    for relative in parser.images:
        assert relative.startswith('images/')
        ET.parse(tmp_path/relative)
    assert 'aria-controls="float-links"' in html
    assert 'Observed first → last' in html and 'Window start' in html
    assert '2020-05-14 00:00' in html


def test_partial_month_preserves_core_month_and_marks_buffer_dates():
    result=fixtures();label=_month_markup(result['groups'],'winter')
    assert '<span class="outside">May</span>' in label
    assert '(buffer dates)' not in label


def test_spark_ids_on_top_and_unambiguous_month_abbreviations_down_left():
    result=fixtures();svg=_spark(result['groups'],'winter',{12:2,13:1,14:1})
    root=ET.fromstring(svg);ns={'s':'http://www.w3.org/2000/svg'}
    texts=root.findall('.//s:text',ns)
    assert any(t.text=='12' and t.get('y')=='14' for t in texts)
    assert '×2' in svg
    assert '<title>May</title>May</text>' in svg
    assert 'width="3" height="12"' in svg


def test_custom_season_and_buffer_define_month_order_for_summary_and_spark():
    # Rename the season and move the buffer into the previous month: no fixed
    # summer/winter dictionary may determine either summary's ordering.
    times=[datetime(2020,10,30),datetime(2020,11,20),datetime(2021,1,5)]
    w=dict(individual_id=12,window_id='custom',source_points=[dict(timestamp=t) for t in times],
           season_attributions=[dict(season='custom',core_start='2020-11-15',core_end='2021-03-22',buffer_start='2020-10-20')])
    groups=[dict(group_id='G1',windows=[w])]
    assert _month_order(groups,'custom')[:4]==[10,11,12,1]
    label=_month_markup(groups,'custom')
    assert label.index('Oct')<label.index('Nov')<label.index('Jan')
    assert '<span class="outside">Oct</span>' in label
    spark=_spark(groups,'custom',{12:1})
    assert spark.index('<title>October</title>Oct')<spark.index('<title>November</title>Nov')<spark.index('<title>January</title>Jan')


def test_timeline_separates_year_headers_and_visually_marks_suppressed_windows():
    from copy import deepcopy
    r=fixtures();groups=deepcopy(r['groups'])
    # Put a separate contribution in another year to exercise panel spacing.
    w=groups[1]['windows'][1]
    for p in w['source_points']:p['timestamp']=p['timestamp'].replace(year=2021)
    svg=_timeline(groups,'winter',{12:2,13:1,14:1},r['collection_members'])
    root=ET.fromstring(svg);ns={'s':'http://www.w3.org/2000/svg'}
    spans=root.findall('.//s:rect[@class="window-span"]',ns)
    selected=[r for r in spans if r.get('data-selection-status')=='selected']
    suppressed=[r for r in spans if r.get('data-selection-status')=='duplicate_window']
    assert selected and suppressed
    assert all(r.get('stroke-dasharray') is None for r in selected)
    assert all(r.get('stroke-dasharray')=='4 2' for r in suppressed)
    headers=sorted({float(t.get('y')) for t in root.findall('.//s:text[@class="year-axis-label"]',ns)})
    labels=[float(t.get('y')) for t in root.findall('.//s:text[@class="timeline-row-label"]',ns)]
    assert len(headers)==2
    prior_rows=[y for y in labels if y<headers[1]]
    assert headers[1]-max(prior_rows)>=30
    assert 'Each year panel has its own date range' in svg
    assert 'Suppressed duplicate/overlapping window' in svg


def test_weekly_density_uses_canonical_selected_points_and_deduplicates_events_across_year():
    from .pantanal_seasonal_report import _weekly_density,_density_svg
    attr=dict(season='summer',season_year=2023,core_start='2023-11-15',core_end='2024-03-22',buffer_start='2023-11-08',buffer_end='2024-03-29')
    def point(day,key):return dict(timestamp=datetime.fromisoformat(day),source_row=key,individual_id=12)
    a=point('2023-12-31T22:00:00',1);b=point('2024-01-01T00:00:00',2);c=point('2024-01-02T00:00:00',3);buffer=point('2023-11-14T12:00:00',4)
    def w(key,points):return dict(window_id=key,individual_id=12,points=points,source_points=points+[point('2024-01-01T00:30:00',100)],start=min(p['timestamp'] for p in points),end=max(p['timestamp'] for p in points),season_attributions=[attr])
    groups=[dict(group_id='G1',windows=[w('A',[a,b])]),dict(group_id='G2',windows=[w('B',[b,c,buffer])]),dict(group_id='G3',windows=[w('C',[point('2024-02-01T00:00:00',999)])])]
    members=[dict(group_id='G1',window_id='A',individual_id=12,selection_status='selected'),dict(group_id='G2',window_id='B',individual_id=12,selection_status='selected'),dict(group_id='G3',window_id='C',individual_id=12,selection_status='duplicate_window')]
    collection=dict(collection_id='SUM-C1',season='summer')
    rows=_weekly_density(collection,groups,members)
    assert {r['season_year'] for r in rows}=={2023}
    assert sum(r['retained_fix_count'] for r in rows)==4
    assert all(datetime.fromisoformat(r['week_start']).weekday()==0 for r in rows)
    by_week={r['week_start'][:10]:r for r in rows}
    assert by_week['2023-12-25']['retained_fix_count']==1
    assert by_week['2024-01-01']['retained_fix_count']==2
    assert by_week['2023-11-13']['season_support']=='buffer_only'
    assert by_week['2023-11-13']['partial_selected_week']
    assert by_week['2024-01-29']['retained_fix_count']==0
    svg=_density_svg(rows,collection)
    ET.fromstring(svg)
    assert '0–2 across all panels' in svg
    assert '2023-12-25' in svg and '2024-01-01' in svg
    assert 'counts are not coverage percentages' in svg
    assert 'ID 12 ×3' in svg


def test_report_writes_density_backing_data_and_reports_multiple_seasons_and_audit(tmp_path):
    import csv
    r=fixtures();r['groups'][0]['season_names']=['autumn','winter']
    r['individuals'][0]['season_diagnostics']={'winter':dict(scanned_windows=10,main_qualifying_windows=0,relaxed_qualifying_windows=0,protected_rejected_windows=10,summary='Fragment loss 30% exceeds the 5% limit.')}
    path=write_report(tmp_path,r);html=path.read_text()
    assert 'Autumn / Winter' in html
    assert 'Fragment loss 30% exceeds the 5% limit.' in html
    assert '<details class="density-view">' in html
    assert 'Exact week dates, counts and exposure diagnostics' in html
    rows=list(csv.DictReader((tmp_path/'data/collection_weekly_density.csv').open()))
    assert sum(int(row['retained_fix_count']) for row in rows)==2
    assert {row['collection_id'] for row in rows}=={'WIN-C01'}
    assert all(row['individual_id']=='12' for row in rows)
