"""Season boundary and selection-regression tests using observed-fix fixtures."""
from datetime import datetime, timedelta

import pytest

from jaguar_irl.data.movement_processor_pantanal_seasonal import (
    SeasonalConfig, SeasonalProcessor, scan_seasonal_windows,
)
from jaguar_irl.data.pantanal_seasons import (
    DEFAULT_SEASONS, season_bounds, validate_seasons, window_seasons,
)
from jaguar_irl.data.pantanal_spatial import build_full_study_mcps
from jaguar_irl.data.pantanal_temporal import TemporalConfig, find_week_candidates


def names(at):
    return {r['season'] for r in window_seasons(at, at, buffer_days=0)}


def fixes(start, days=7, hours=2, individual=1, offset=0):
    count=round(days*24/hours)+1
    return [dict(individual_id=individual,timestamp=start+timedelta(hours=hours*n),
                 event_id=str(offset+n),source_row=offset+n+2,
                 longitude=-56.0+(n%7)*.001,latitude=-18.0+(n%5)*.001,
                 study='Pantanal',country='Brazil') for n in range(count)]


def test_precise_midmonth_and_march_boundaries_cover_every_date():
    validate_seasons(DEFAULT_SEASONS)
    assert names(datetime(2020,3,21,23,59,59))=={'summer'}
    assert names(datetime(2020,3,22))=={'autumn'}
    assert names(datetime(2020,5,14,23,59,59))=={'autumn'}
    assert names(datetime(2020,5,15))=={'winter'}
    assert names(datetime(2020,8,15))=={'spring'}
    assert names(datetime(2020,11,15))=={'summer'}
    assert names(datetime(2020,2,29))=={'summer'}
    january=window_seasons(datetime(2020,1,1),datetime(2020,1,8),buffer_days=0)
    assert [(a['season'],a['season_year']) for a in january]==[('summer',2019)]


def test_buffer_requires_entire_inclusive_window_inside_half_open_extent():
    def winters(start,end):
        return [a for a in window_seasons(start,end,buffer_days=7) if a['season']=='winter']
    assert winters(datetime(2020,5,8),datetime(2020,5,15))
    assert not winters(datetime(2020,5,7,23,59),datetime(2020,5,14,23,59))
    assert winters(datetime(2020,8,14),datetime(2020,8,21))
    assert not winters(datetime(2020,8,15),datetime(2020,8,22))
    assert not winters(datetime(2020,5,1),datetime(2020,5,8))
    with pytest.raises(ValueError,match='Invalid'):
        window_seasons(datetime(2020,5,1),datetime(2020,5,8),buffer_days=-1)


def test_custom_boundaries_validate_contiguous_partition():
    definitions=[dict(s) for s in DEFAULT_SEASONS]
    definitions[1]['start_day']=14
    with pytest.raises(ValueError,match='exactly once'):
        validate_seasons(definitions)
    summer=next(s for s in DEFAULT_SEASONS if s['name']=='summer')
    assert season_bounds(summer,2019)==(datetime(2019,11,15),datetime(2020,3,22))


def test_seasonal_scanner_does_not_lose_midmonth_window_to_monthly_winner():
    raw=fixes(datetime(2020,5,1))+fixes(datetime(2020,5,20),offset=1000)
    old=find_week_candidates(raw)
    assert len(old['candidates'])==1
    assert old['candidates'][0]['start']==datetime(2020,5,1)
    cfg=SeasonalConfig(individual_ids=(1,))
    current=scan_seasonal_windows(raw,cfg)
    winner=current['winners'][(1,'winter',2020,'main')]
    assert winner['start']==datetime(2020,5,20)
    assert current['winners'][(1,'autumn',2020,'main')]['start']==datetime(2020,5,1)
    assert current['individuals'][0]['scanned_windows']==len(raw)


def test_configurable_duration_and_unthinned_source_preservation():
    raw=fixes(datetime(2020,6,1),days=14,hours=.5)
    cfg=SeasonalConfig(individual_ids=(1,),temporal=TemporalConfig(
        week_days=14,min_week_observed_span_days=13))
    result=scan_seasonal_windows(raw,cfg)
    winner=result['winners'][(1,'winter',2020,'main')]
    assert winner['window_duration_days']==14
    assert winner['expected_fixes']==169
    assert winner['selected_fixes']==169
    assert len(winner['source_points'])==673
    assert winner['source_points'][1]['timestamp']-winner['source_points'][0]['timestamp']==timedelta(minutes=30)
    assert winner['points'][1]['timestamp']-winner['points'][0]['timestamp']==timedelta(hours=2)


def test_spatially_isolated_main_animal_receives_singleton_group():
    raw=fixes(datetime(2020,6,1))
    cfg=SeasonalConfig(individual_ids=(1,))
    temporal=scan_seasonal_windows(raw,cfg)
    processor=SeasonalProcessor(cfg)
    processor.individual_sexes={1:{'sex':'male'}}
    mcps=build_full_study_mcps(raw,cfg.individual_ids,cfg.spatial)
    groups=processor.generate_groups(temporal,mcps)
    assert len(groups)==1
    assert groups[0]['ids']=='1'
    assert groups[0]['generation_method']=='singleton'
    assert groups[0]['candidate_list']=='main'
    assert groups[0]['season_names']==['winter']
    assert groups[0]['grouping_calendar_season']=='winter'


def test_end_to_end_seasonal_checkpoint_and_collection_export(tmp_path):
    import csv
    import json
    from pathlib import Path

    import numpy as np

    from jaguar_irl.data.pantanal_checkpoint import load_selection_checkpoint, read_table
    from jaguar_irl.data.export_pantanal_seasonal_irl import export_collection
    from jaguar_irl.data.export_pantanal_irl import validate_export

    raw=fixes(datetime(2020,6,1),hours=1,individual=1)
    raw+=fixes(datetime(2020,6,1),hours=1,individual=2,offset=1000)
    csv_path=tmp_path/'movement.csv'
    columns=['Event_ID','timestamp','location.long','location.lat',
             'individual.local.identifier (ID)','study.name','country','tag.local.identifier']
    with csv_path.open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=columns)
        writer.writeheader()
        for row in raw:
            writer.writerow({'Event_ID':row['event_id'],
                'timestamp':row['timestamp'].strftime('%m/%d/%y %H:%M'),
                'location.long':row['longitude'],'location.lat':row['latitude'],
                'individual.local.identifier (ID)':row['individual_id'],
                'study.name':'Pantanal','country':'Brazil',
                'tag.local.identifier':f"tag-{row['individual_id']}"})
    metadata=tmp_path/'collars.csv'
    metadata.write_text('ID,Sex,Planned Schedule (h)\n1,Male,1\n2,Female,1\n')
    output=tmp_path/'selection'
    config=SeasonalConfig(csv_path=str(csv_path),output_dir=str(output),individual_ids=(1,2))
    result=SeasonalProcessor(config).run_pipeline(collar_metadata_path=metadata,render=False)
    checkpoint=load_selection_checkpoint(result['checkpoint_dir'])
    assert checkpoint['manifest']['seasonal_schema']=='pantanal_seasonal_checkpoint/1'
    assert len(checkpoint['source'])==338
    assert len(checkpoint['windows'])==2
    assert all(len(w['events'])==169 for w in checkpoint['windows'].values())
    assert (output/'data'/'trajectory_manifest.csv').is_file()
    assert (output/'selection_manifest.json').is_file()
    collection=next(c for c in result['collections'] if c['season']=='winter')
    assert collection['n_individuals']==2
    memberships=list(read_table(Path(result['checkpoint_dir'])/'collection_members.csv'))
    selected=[r for r in memberships if r['collection_id']==collection['collection_id'] and r['selection_status']=='selected']
    assert {r['individual_id'] for r in selected}=={'1','2'}
    assert all(json.loads(r['selector_subtrajectory_ids_json']) for r in selected)
    # The exporter must work from the completed checkpoint without source CSVs.
    csv_path.unlink()
    metadata.unlink()
    exported=export_collection(result['checkpoint_dir'],collection['collection_id'],tmp_path/'tracking')
    validated=validate_export(exported)
    assert validated['counts']['source_events']==338
    assert validated['split_status']=='unassigned'
    manifest=list(read_table(exported/'data'/'trajectory_manifest.csv'))
    assert {r['variant'] for r in manifest}=={'fine','two_hour'}
    assert {r['individual_id'] for r in manifest}=={'1','2'}
    assert all(r['split']=='unassigned' and r['training_ready']=='False' for r in manifest)
    crosswalk=list(read_table(exported/'data'/'selector_export_crosswalk.csv'))
    assert crosswalk
    source_segment_ids={s for row in selected for s in json.loads(row['selector_subtrajectory_ids_json'])}
    assert {r['selector_subtrajectory_id'] for r in crosswalk}<=source_segment_ids
    assert {r['trajectory_id'] for r in crosswalk}=={r['trajectory_id'] for r in manifest}
    arrays=[r for r in manifest if r['array_path']]
    assert arrays
    for row in arrays:
        array=np.load(exported/row['array_path'])
        assert array.ndim==2 and array.shape[1]==3
        assert np.array_equal(array[:,2],np.arange(len(array)))
        assert Path(row['array_path']).name.startswith(f"jaguar_{row['individual_id']}_")


def test_rejection_diagnostics_preserve_numeric_evidence_per_season():
    raw=fixes(datetime(2020,6,1),days=1,hours=2)
    # Eight isolated observations cannot make a five-observation fragment.
    isolated=[dict(raw[0],event_id=f'gap{n}',source_row=100+n,
                   individual_id=2,timestamp=datetime(2020,6,1)+timedelta(hours=10*n))
              for n in range(8)]
    result=scan_seasonal_windows(raw+isolated,SeasonalConfig(individual_ids=(1,2)))
    audits={a['individual_id']:a for a in result['individuals']}
    relaxed=audits[1]['season_diagnostics']['winter']
    assert relaxed['main_qualifying_windows']==0
    assert relaxed['relaxed_qualifying_windows']>0
    best=relaxed['best_relaxed_window']
    assert (best['retained_fixes'],best['resampled_fixes'],best['expected_reference_fixes'])==(13,13,85)
    assert best['retained_span_days']==1
    assert best['required_fixes']==68
    assert best['required_observed_span_days']==6.5
    assert set(best['window_quality_violation_codes'])=={'insufficient_retained_fixes','insufficient_retained_span'}
    assert '13/85' in relaxed['summary']
    rejected=audits[2]['season_diagnostics']['winter']
    assert rejected['main_qualifying_windows']==rejected['relaxed_qualifying_windows']==0
    assert rejected['protected_rejected_windows']==8
    best=rejected['best_protected_rejected_window']
    assert (best['retained_fixes'],best['resampled_fixes'],best['hard_gaps'])==(0,8,7)
    assert best['short_fragment_loss']==1 and best['required_max_short_fragment_loss']==.05
    assert best['max_source_gap_hours']==10 and best['max_gap_hours']==4
    assert best['min_subtrajectory_points']==5
    assert best['season_years']==[2020]
    assert '0/8' in rejected['summary']
    assert 'No observed start' in audits[2]['season_diagnostics']['summer']['summary']
    assert set(result['winners'])=={(1,'winter',2020,'relaxed')}
    assert audits[2]['protected_rejections']['excess_short_fragment_loss']==8
