"""Selection/export invariants for all seasonal bouts, including boundary losses."""
import csv
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

from .movement_processor_pantanal_bouts import BoutConfig, BoutProcessor, scan_bouts, seasonal_retention
from .pantanal_checkpoint import load_selection_checkpoint, read_table
from .export_pantanal_bouts_irl import export_bout_collection
from .export_pantanal_irl import validate_export


def fixes(hours, start=datetime(2020,6,1), ident=1, offset=0, tag='A'):
    return [dict(individual_id=ident,timestamp=start+timedelta(hours=h),
        event_id=str(offset+n),source_row=offset+n+2,longitude=-56+(n%3)*.012,
        latitude=-18+(n%2)*.008,study='Pantanal',country='Brazil',tag_id=tag)
        for n,h in enumerate(hours)]


def scan(raw, ids=(1,)):
    return scan_bouts(raw, BoutConfig(individual_ids=ids))


def test_jitter15_inclusive_native_and_selected_gap_boundaries():
    config = BoutConfig(individual_ids=(1,), gap_jitter_minutes=15)
    result = scan_bouts(fixes([0, 4.25, 8.5]), config)
    w, = result['candidates']
    assert [p['dt_hours'] for p in w['points']] == [None, 4.25, 4.25]
    assert not scan_bouts(fixes([0, 4.25 + 1/3600, 8.5 + 2/3600]), config)['candidates']
    # Native gaps pass in both cases; the thinned gap alone crosses the cap.
    raw = fixes([0, 2, 4, 5, 8.25, 10.25, 12.25])
    assert len(scan_bouts(raw, config)['candidates']) == 1
    raw = fixes([0, 2, 4, 5, 8.25 + 1/3600, 10.25 + 1/3600, 12.25 + 1/3600])
    assert len(scan_bouts(raw, config)['candidates']) == 2
    assert config.temporal.max_gap_hours == 4.25
    assert BoutConfig().temporal.max_gap_hours == 4


def test_four_hour_cap_three_fix_floor_and_no_percentage_gate():
    raw=fixes([0,4,8,12.01,16.01,20.01,30,32])
    result=scan(raw)
    assert [w['selected_fixes'] for w in result['candidates']]==[3,3]
    assert all(w['affected_point_fraction']==1 for w in result['candidates'])
    assert sum(r['selected_fixes'] for r in result['rejected_bouts'])==2
    row=next(r for r in result['sensitivity'] if r['season']=='winter')
    assert row['five_point_selected_fixes']==0
    assert row['eight_hour_selected_fixes']==6


def test_exact_boundary_and_year_pooling_and_tag_changes():
    raw=fixes(range(0,12,2),datetime(2020,8,14,18))
    raw+=fixes([0,2,4],datetime(2021,6,1),offset=100)
    raw+=fixes([6,8,10],datetime(2021,6,1),offset=200,tag='B')
    raw+=fixes([0,2,4],datetime(2020,1,1),offset=300)
    ws=scan(raw)['candidates']
    assert len(ws)==5
    assert [(w['season_attributions'][0]['season'],w['season_attributions'][0]['season_year']) for w in ws]==[
        ('summer',2019),('winter',2020),('spring',2020),('winter',2021),('winter',2021)]
    assert all(len({p['tag_id'] for p in w['source_points']})==1 for w in ws)
    for w in ws:
        a=w['season_attributions'][0]
        assert all(a['core_start']<=p['timestamp']<a['core_end'] for p in w['source_points'])


def test_native_three_points_not_confused_with_selected_three_and_tails_preserved():
    result=scan(fixes([0,1,2,10,11,12,13,14,15]))
    w,=result['candidates']
    assert [p['timestamp'].hour for p in w['points']]==[10,12,14]
    assert len(w['source_points'])==6 and w['end'].hour==15
    r=next(r for r in result['sensitivity'] if r['season']=='winter')
    assert r['native_three_point_bouts']==2
    assert r['native_eligible_fixes_outside_main']==3
    assert result['individuals'][0]['n_source_fixes_outside_selected_bouts']==3


def test_selected_hard_gap_splits_even_when_native_gaps_pass():
    # The point at hour 5 is too soon after hour 4 to select; 4→9 is a hard cut.
    raw=fixes([0,2,4,5,9,11,13,14])
    ws=scan(raw)['candidates']
    assert len(ws)==2
    assert [len(w['source_points']) for w in ws]==[4,4]
    assert len({p['source_row'] for w in ws for p in w['source_points']})==8
    assert all(w['max_gap_hours']<=4 for w in ws)


def test_three_hour_native_schedule_and_zero_displacements_are_preserved():
    raw=fixes([0,3,6,9])
    for p in raw:p.update(longitude=-56,latitude=-18)
    w,=scan(raw)['candidates']
    assert w['selected_fixes']==4 and w['defined_turn_count']==0
    assert [p['dt_hours'] for p in w['points']]==[None,3,3,3]


def fixture_csv(tmp_path):
    raw=fixes(range(6)) + fixes([0,3,6],datetime(2021,6,1),offset=100)
    raw+=fixes([0,2,4],datetime(2020,8,15),offset=200)
    raw+=fixes([0,4,8],ident=2,offset=300)
    raw+=fixes([0,2,4,5,9,11,13,14],datetime(2021,6,2),ident=2,offset=400)
    path=tmp_path/'movement.csv'
    fields=['Event_ID','timestamp','location.long','location.lat','individual.local.identifier (ID)',
            'study.name','country','tag.local.identifier']
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in raw:
            w.writerow(dict(zip(fields,[r['event_id'],r['timestamp'].strftime('%m/%d/%y %H:%M'),
                r['longitude'],r['latitude'],r['individual_id'],'Pantanal','Brazil',r['tag_id']])))
    metadata=tmp_path/'collars.csv'
    metadata.write_text('ID,Sex,Planned Schedule (h)\n1,Male,1\n2,Female,4\n')
    return path,metadata,raw


def test_complete_collection_checkpoint_report_and_standalone_export(tmp_path):
    path,metadata,raw=fixture_csv(tmp_path)
    out=tmp_path/'out'
    result=BoutProcessor(BoutConfig(csv_path=str(path),output_dir=str(out),individual_ids=(1,2))).run_pipeline(
        collar_metadata_path=metadata)
    cp=load_selection_checkpoint(result['checkpoint_dir'])
    assert len(cp['source'])==len(raw)
    assert len(cp['windows'])==6
    assert json.loads((Path(result['checkpoint_dir'])/'seasons.json').read_text())['sampling_duration_days'] is None
    for c in result['collections']:
        members=[r for r in result['collection_members'] if r['collection_id']==c['collection_id'] and r['selection_status']=='selected']
        assert len(members)==(5 if c['season']=='winter' else 1)
        assert c['all_qualifying_bouts_preserved']
    report=(out/'index.html').read_text()
    assert 'three-fix rule' in report and 'no weekly density' in report
    from html.parser import HTMLParser
    import re
    class ReportText(HTMLParser):
        def __init__(self):
            super().__init__()
            self.text = []
        def handle_data(self, data):
            self.text.append(data)
    visible = ReportText()
    visible.feed(report)
    assert not re.search(r'(?i)bout', ' '.join(visible.text))
    assert 'Bursts' in report
    for figure in (out/'images').glob('*.svg'):
        assert not re.search(r'(?i)bout', figure.read_text())
    assert list((out/'images').glob('*.svg'))
    density=list(read_table(out/'data'/'collection_weekly_density.csv'))
    assert sum(int(r['retained_fix_count']) for r in density)==18
    path.unlink();metadata.unlink()
    exported=export_bout_collection(result['checkpoint_dir'],'WIN-C01',tmp_path/'exports')
    validated=validate_export(exported)
    assert validated['counts']['source_events']==len(raw)-3
    rows=list(read_table(exported/'data'/'trajectory_manifest.csv'))
    two=[r for r in rows if r['variant']=='two_hour' and r['collection']=='independent']
    assert len(two)==5
    assert all(r['data_eligible']=='True' and r['source_event_count']=='3' for r in two)
    assert all(r['training_ready']=='False' for r in rows)
    # The new adapter must never reapply the old 20% affected-fix budget.
    assert max(float(r['max_observation_gap_hours']) for r in two)==4
    assert sum(int(r['source_event_count']) for r in two)==15


def test_refuse_nonzero_season_buffer():
    with pytest.raises(ValueError,match='zero season buffer'):
        BoutConfig(season_buffer_days=7)


def test_retention_denominator_includes_rejected_fixes_and_zero_coverage():
    # Three of nine native fixes selected; six preserved. Rejected short run
    # must remain in the denominator. ID2 has fixes but no accepted bout.
    raw = fixes([0,1,2,10,11,12,13,14,15]) + fixes([0,1],ident=2,offset=100)
    temporal = scan(raw, ids=(1,2,3))
    group = dict(group_id='G001',season='winter',windows=temporal['candidates'])
    result = seasonal_retention(temporal,[group,dict(group,group_id='G002')])
    rows = {(r['individual_id'],r['season']):r for r in result['season_individual_coverage']}
    assert len(rows) == 12
    assert rows[1,'winter']['selected_retention_pct'] == pytest.approx(100/3)
    assert rows[1,'winter']['native_preservation_pct'] == pytest.approx(200/3)
    assert rows[2,'winter']['selected_retention_pct'] == 0
    assert rows[3,'winter']['selected_retention_pct'] is None
    assert rows[1,'summer']['selected_retention_pct'] is None
    assert all(r['raw_fixes']==9 for r in result['group_season_coverage'])
    winter = next(r for r in temporal['season_summary'] if r['season']=='winter')
    assert winter['selected_retention_pct'] == pytest.approx(300/11)


def test_jitter_checkpoint_exports_without_reapplying_strict_four_hour_cap(tmp_path):
    path,metadata,_ = fixture_csv(tmp_path)
    with path.open(newline='') as f:
        reader=csv.DictReader(f); fields=reader.fieldnames; rows=list(reader)
    for r in rows:
        if r['individual.local.identifier (ID)']=='2' and r['timestamp'].startswith('06/01/20'):
            t=datetime.strptime(r['timestamp'],'%m/%d/%y %H:%M')
            r['timestamp']=(t+timedelta(minutes=15*(t.hour//4))).strftime('%m/%d/%y %H:%M')
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    result=BoutProcessor(BoutConfig(csv_path=str(path),output_dir=str(tmp_path/'out'),
        individual_ids=(1,2),gap_jitter_minutes=15)).run_pipeline(collar_metadata_path=metadata)
    exported=export_bout_collection(result['checkpoint_dir'],'WIN-C01',tmp_path/'exports')
    validate_export(exported)
    rows=list(read_table(exported/'data'/'trajectory_manifest.csv'))
    two=[r for r in rows if r['variant']=='two_hour' and r['collection']=='independent']
    assert max(float(r['max_observation_gap_hours']) for r in two)==4.25
    assert all(r['data_eligible']=='True' for r in two)
    assert 'four hours plus 15 minutes' in (tmp_path/'out'/'index.html').read_text()
