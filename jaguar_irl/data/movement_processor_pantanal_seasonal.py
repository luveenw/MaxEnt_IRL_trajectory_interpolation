"""Seasonal Pantanal selection, collections and source-preserving checkpoints.

python -m jaguar_irl.data.movement_processor_pantanal_seasonal --help
"""
from __future__ import annotations
import argparse
from bisect import bisect_right
from collections import Counter,defaultdict
from dataclasses import asdict,dataclass,field
from datetime import datetime,timedelta,timezone
import json
import logging
import math
from pathlib import Path
import shutil
import tempfile

from .movement_processor_pantanal import (MovementProcessor,ProcessorConfig,ROOT,
    PANTANAL_IDS,SOURCES,write_csv,json_default)
from .pantanal_temporal import TemporalConfig,_candidate,_rank
from .pantanal_calendar import summarize_calendar
from .pantanal_spatial import SpatialConfig,build_full_study_mcps,export_geojson
from .pantanal_checkpoint import (write_selection_checkpoint,load_selection_checkpoint,
    load_individual_sexes,read_table,write_table,file_inventory,file_hash,json_text,digest,
    publish_directory,verify_inventory)
from .pantanal_seasons import DEFAULT_SEASONS,validate_seasons,window_seasons,seasons_metadata

LOG=logging.getLogger(__name__)

@dataclass
class SeasonalConfig(ProcessorConfig):
    output_dir: str = str(ROOT/'analysis'/'pantanal_seasonal_selection')
    seasons: tuple = field(default_factory=lambda:tuple(dict(s) for s in DEFAULT_SEASONS))
    season_buffer_days: float = 7.0
    max_collections: int = 7
    seasonal_policy: str = 'thinned_selection_source_preserved_seasonal_v1'
    seasonal_software: dict = field(default_factory=dict)

    def __post_init__(self):
        validate_seasons(self.seasons)
        if not math.isfinite(self.season_buffer_days) or self.season_buffer_days<0:
            raise ValueError('season_buffer_days must be finite and nonnegative')
        if self.max_collections<1:
            raise ValueError('max_collections must be positive')
        if not math.isfinite(self.temporal.week_days):
            raise ValueError('sampling duration must be finite')


def scan_seasonal_windows(records, config):
    """Evaluate every observed start once; retain best per animal/season occurrence.

    Main/relaxed alternatives are reduced only after exact seasonal membership.
    All QC source observations inside each retained period remain attached.
    """
    by_id=defaultdict(list)
    for p in records:by_id[p['individual_id']].append(p)
    winners={}; audits=[]
    for ident,raw in sorted(by_id.items()):
        raw=sorted(raw,key=lambda p:p['timestamp']); times=[p['timestamp'] for p in raw]
        audit=dict(individual_id=ident,study=raw[0]['study'],n_raw_fixes=len(raw),
            first_fix=times[0],last_fix=times[-1],tracking_span_days=(times[-1]-times[0]).total_seconds()/86400,
            scanned_windows=0,protected_rejections=Counter(),season_counts=Counter())
        audit['season_diagnostics']={season['name']:dict(
            scanned_windows=0,main_qualifying_windows=0,relaxed_qualifying_windows=0,
            protected_rejected_windows=0,protected_rejection_reasons=Counter(),
            strict_rejection_reasons=Counter(),window_quality_rejection_reasons=Counter(),
            best_protected_rejected_window={},best_relaxed_window={}) for season in config.seasons}
        diagnostic_best_keys={}
        for index,start in enumerate(times):
            end=start+timedelta(days=config.temporal.week_days)
            attrs=window_seasons(start,end,config.seasons,config.season_buffer_days)
            if not attrs:continue
            audit['scanned_windows']+=1
            diagnostic={}
            candidate,reason=_candidate(raw,times,index,config.temporal,
                relax_week_quality=True,diagnostics=diagnostic)
            # Diagnostic aggregation never changes candidate scores or winners.
            # A window is counted once per target season, even if a custom large
            # buffer attributes it to multiple occurrences of that same season.
            for season_name in sorted({a['season'] for a in attrs}):
                detail=audit['season_diagnostics'][season_name]
                detail['scanned_windows']+=1
                if diagnostic['strict_rejection_reason']!='accepted':
                    detail['strict_rejection_reasons'].update([diagnostic['strict_rejection_reason']])
                quality_codes=[]
                if diagnostic['retained_fixes']<diagnostic['required_fixes']:
                    quality_codes.append('insufficient_retained_fixes')
                if diagnostic['retained_span_days']<diagnostic['required_observed_span_days']:
                    quality_codes.append('insufficient_retained_span')
                detail['window_quality_rejection_reasons'].update(quality_codes)
                evidence=dict(diagnostic,individual_id=ident,season=season_name,
                    season_years=sorted({a['season_year'] for a in attrs if a['season']==season_name}),
                    expected_reference_fixes=int(round(config.temporal.week_days*24/config.temporal.target_interval_hours))+1,
                    min_subtrajectory_points=config.temporal.min_subtrajectory_points,
                    max_affected_point_fraction=config.temporal.max_affected_point_fraction,
                    regular_min_hours=config.temporal.regular_min_hours,
                    regular_max_hours=config.temporal.regular_max_hours,
                    max_gap_hours=config.temporal.max_gap_hours,
                    window_quality_violation_codes=quality_codes)
                if candidate is None:
                    detail['protected_rejected_windows']+=1
                    detail['protected_rejection_reasons'].update(diagnostic['protected_failure_codes'])
                    score=(diagnostic['retained_fixes'],-diagnostic['short_fragment_loss'],
                           diagnostic['resampled_fixes'],diagnostic['retained_span_days'])
                    key=season_name,'protected'
                    if key not in diagnostic_best_keys or score>diagnostic_best_keys[key]:
                        diagnostic_best_keys[key]=score
                        detail['best_protected_rejected_window']=evidence
                elif candidate['requires_week_relaxation']:
                    detail['relaxed_qualifying_windows']+=1
                    score=_rank(candidate);key=season_name,'relaxed'
                    if key not in diagnostic_best_keys or score>diagnostic_best_keys[key]:
                        diagnostic_best_keys[key]=score
                        detail['best_relaxed_window']=dict(evidence,
                            violation_codes=candidate['violation_codes'],violation_text=candidate['violation_text'])
                else:
                    detail['main_qualifying_windows']+=1
            if candidate is None:
                audit['protected_rejections'].update(diagnostic['protected_failure_codes'])
                continue
            candidate.update(support_warning=False,support_violation_codes=[],support_violation_text='',
                individual_first_fix=times[0],individual_last_fix=times[-1],
                individual_tracking_span_days=audit['tracking_span_days'],season_attributions=attrs)
            kind='relaxed' if candidate['requires_week_relaxation'] else 'main'
            # No monthly-winner prefilter: every qualifying start competes in its season-year.
            for a in attrs:
                key=(ident,a['season'],a['season_year'],kind)
                audit['season_counts'][a['season']+'_'+kind]+=1
                if key not in winners or _rank(candidate)>_rank(winners[key]):
                    candidate['source_points']=raw[index:bisect_right(times,end)]
                    winners[key]=candidate
        for season_name,detail in audit['season_diagnostics'].items():
            if detail['main_qualifying_windows']:
                detail['summary']=(f"{detail['main_qualifying_windows']} windows satisfy main temporal rules; "
                    f"{detail['relaxed_qualifying_windows']} additional windows satisfy protected rules with density/span exceptions.")
            elif detail['relaxed_qualifying_windows']:
                evidence=detail['best_relaxed_window']
                detail['summary']=(f"Only relaxed temporal windows qualify. Best relaxed window: "
                    f"{evidence['retained_fixes']}/{evidence['expected_reference_fixes']} reference fixes "
                    f"(minimum {evidence['required_fixes']}); retained span {evidence['retained_span_days']:.2f} days "
                    f"(minimum {evidence['required_observed_span_days']:g}). {evidence['violation_text']}")
            elif detail['protected_rejected_windows']:
                evidence=detail['best_protected_rejected_window']
                detail['summary']=(f"No scanned window satisfies protected temporal rules. Best rejected window: "
                    f"{evidence['retained_fixes']}/{evidence['resampled_fixes']} thinned observations retained; "
                    f"{evidence['short_fragment_loss']:.1%} fragment loss (ceiling {evidence['required_max_short_fragment_loss']:.0%}); "
                    f"{evidence['hard_gaps']} gaps exceed {evidence['max_gap_hours']:g} hours "
                    f"(largest {evidence['max_source_gap_hours']:.2f} hours). "
                    f"Retained fragments require at least {evidence['min_subtrajectory_points']} observations; "
                    f"irregular-edge endpoints must fit the period-wide {evidence['max_affected_point_fraction']:.0%} budget.")
            else:
                detail['summary']='No observed start supplies a configured-duration window within this buffered season.'
        audits.append(audit)
        LOG.info('Scanned ID %s (%s starts)',ident,audit['scanned_windows'])
    # A main window supersedes relaxed choices for the same animal/season-year.
    winners={key:w for key,w in winners.items() if key[-1]=='main' or (*key[:3],'main') not in winners}
    by_window={w['window_id']:w for w in winners.values()}
    for w in by_window.values():w.update(summarize_calendar(w['points']))
    return dict(candidates=[w for w in by_window.values() if not w['requires_week_relaxation']],
        relaxed_candidates=[w for w in by_window.values() if w['requires_week_relaxation']],
        individuals=audits,winners=winners)


class SeasonalProcessor(MovementProcessor):
    def __init__(self,config=None):
        super().__init__(config or SeasonalConfig())
        self.active_season=None

    def candidate_pools(self,candidates):
        rows=[w for w in candidates if any(a['season']==self.active_season for a in w['season_attributions'])]
        years=sorted({a['season_year'] for w in rows for a in w['season_attributions'] if a['season']==self.active_season})
        seen=set()
        for year in [None,*years]:
            best={}
            for w in rows:
                if year is not None and not any(a['season']==self.active_season and a['season_year']==year for a in w['season_attributions']):continue
                i=w['individual_id']; priority=(not w['requires_week_relaxation'],self.window_rank(w))
                if i not in best or priority>(not best[i]['requires_week_relaxation'],self.window_rank(best[i])):best[i]=w
            sig=tuple(sorted((i,w['window_id']) for i,w in best.items()))
            if best and sig not in seen:
                seen.add(sig)
                yield min(w['month'] for w in best.values()),best

    def candidate_extent(self,mcps,ids,windows,allow_over_budget=False):
        # Include fine excursions as well as the full-study MCP95 in the map.
        expanded=[dict(w,points=w['source_points']) for w in windows]
        return super().candidate_extent(mcps,ids,expanded,allow_over_budget)

    def build_group(self,*args,**kwargs):
        g=super().build_group(*args,**kwargs)
        g.update(season=self.active_season,season_names=[self.active_season],
            grouping_calendar_season=self.active_season,
            calendar_seasons=sorted({a['season'] for w in g['windows'] for p in w['source_points']
                for a in window_seasons(p['timestamp'],p['timestamp'],self.config.seasons,buffer_days=0)}))
        return g

    def add_singletons(self,groups,windows,mcps,relaxed=False):
        represented={int(i) for g in groups for i in g['ids'].split(';')}
        best={}
        for _,pool in self.candidate_pools(windows):
            for i,w in pool.items():
                if i in represented:continue
                if i not in best or (not w['requires_week_relaxation'],self.window_rank(w))>(not best[i]['requires_week_relaxation'],self.window_rank(best[i])):best[i]=w
        added=[]
        for i,w in sorted(best.items()):
            extent=self.candidate_extent(mcps,[i],[w],allow_over_budget=relaxed)
            if extent is None:continue
            codes,text=self.spatial_exceptions(extent,0) if relaxed else ([],[])
            g=self.build_group(w['month'],[i],{i:w},mcps,extent,codes,' '.join(text) if isinstance(text,list) else text,
                new_ids=[i],method='singleton')
            g['candidate_list']='relaxed' if relaxed else 'main'
            added.append(g)
        return added

    def generate_groups(self,temporal,mcps):
        groups=[]
        for season in self.config.seasons:
            self.active_season=season['name']
            _,main=self.rank_groups(temporal['candidates'],mcps)
            main+=self.add_singletons(main,temporal['candidates'],mcps)
            ids={int(i) for g in main for i in g['ids'].split(';')}
            _,relaxed=self.rank_groups([*temporal['candidates'],*temporal['relaxed_candidates']],mcps,
                secondary_for_ids=set(self.config.individual_ids)-ids)
            relaxed+=self.add_singletons(main+relaxed,[*temporal['candidates'],*temporal['relaxed_candidates']],mcps,relaxed=True)
            groups.extend(main+relaxed)
        # Canonical sections/grids for identical windows across neighboring seasons.
        unique={}
        for g in groups:
            sig=(tuple(sorted(w['window_id'] for w in g['windows'])),tuple(g['bounds']))
            if sig in unique:
                old=unique[sig];old['season_names']=sorted(set(old['season_names']+g['season_names']))
                old['grouping_calendar_season']=';'.join(old['season_names'])
                if g['candidate_list']=='main':old['candidate_list']='main'
            else:unique[sig]=g
        groups=sorted(unique.values(),key=lambda g:(g['candidate_list']!='main',-g['balanced_fixes_score'],
            -g['median_density'],g['median_affected_fraction'],g['area_km2'],g['ids'],str(g['selected_start'])))
        for rank,g in enumerate(groups,1):
            g.update(group_id=f'G{rank:03d}',rank=rank,overall_rank=rank,is_shortlisted=rank<=7,is_reported=True)
        return groups

    def run_pipeline(self,*,collar_metadata_path=None,render=True):
        from .pantanal_seasonal_collections import build_collections
        output=Path(self.config.output_dir).resolve()
        protected=(ROOT/'analysis'/'pantanal_selection').resolve()
        if output==protected or protected in output.parents:
            raise ValueError('Seasonal output cannot overwrite the locked selection folder')
        self.config.seasonal_software={p.name:file_hash(p) for p in Path(__file__).parent.glob('*season*.py') if not p.name.startswith('test_')}
        self.parse()
        collar_metadata_path=collar_metadata_path or ROOT/'data'/'Jaguar_additional_information_fixed.csv'
        self.individual_sexes=load_individual_sexes(collar_metadata_path,self.config.individual_ids)
        temporal=scan_seasonal_windows(self.records,self.config)
        for a in temporal['individuals']:a.update(self.individual_sexes[a['individual_id']])
        mcps=build_full_study_mcps(self.records,self.config.individual_ids,self.config.spatial)
        groups=self.generate_groups(temporal,mcps)
        collections,members=build_collections(groups,max_collections=self.config.max_collections,cohort_ids=self.config.individual_ids)
        group_lookup={g['group_id']:g for g in groups}
        for c in collections:
            coverage=summarize_calendar(p for gid in c['group_ids'] for w in group_lookup[gid]['windows'] for p in w['source_points'])
            c.update(coverage)
            c['months']=coverage['observed_months'];c['years']=coverage['observed_years']
        output.mkdir(parents=True,exist_ok=True);(output/'data').mkdir(exist_ok=True)
        checkpoint=write_seasonal_checkpoint(self.config,self.records,temporal,groups,mcps,self.parse_audit,
            collections,members,collar_metadata_path)
        export_geojson(mcps,output/'mcp95_full_study.geojson')
        result=dict(config=asdict(self.config),seasons=list(self.config.seasons),collections=collections,
            collection_members=members,groups=groups,individuals=temporal['individuals'],
            mcps_geojson=json.loads((output/'mcp95_full_study.geojson').read_text()),
            checkpoint_dir=str(checkpoint),sources=SOURCES,
            provenance=dict(generated_utc=datetime.now(timezone.utc).isoformat(),source_sha256=file_hash(self.config.csv_path)),
            season_metadata=seasons_metadata(self.config.seasons,self.config.season_buffer_days,self.config.temporal.week_days))
        write_backing(output,result,temporal)
        if render:
            from .pantanal_seasonal_report import write_report
            write_report(output,result)
        return result


def write_seasonal_checkpoint(config,records,temporal,groups,mcps,parse_audit,collections,members,collar_path,*,season_metadata=None):
    root=Path(config.output_dir)/'checkpoints';root.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix='.seasonal-',dir=root))
    try:
        # This private construction is extended before its immutable publication.
        compact=dict(temporal)
        compact['candidates']=[{k:v for k,v in w.items() if k!='source_points'} for w in temporal['candidates']]
        compact['relaxed_candidates']=[{k:v for k,v in w.items() if k!='source_points'} for w in temporal['relaxed_candidates']]
        base=write_selection_checkpoint(config,records,compact,groups,mcps,parse_audit,checkpoint_root=temporary,collar_metadata_path=collar_path)
        loaded=load_selection_checkpoint(base)
        windows={w['window_id']:key for key,w in loaded['windows'].items()}
        groupkeys={g['group_id']:key for key,g in loaded['groups'].items()}
        eventkeys={p['source_row']:key for key,p in loaded['source'].items()}
        # loaded source_row is a CSV string.
        eventkeys={int(k):v for k,v in eventkeys.items()}
        cr=[dict(c,group_ids_json=c['group_ids']) for c in collections]
        write_table(base/'collections.csv',cr,list(dict.fromkeys(k for r in cr for k in r)) or ['collection_id','season','group_ids_json'])
        cm=[dict(m,group_key=groupkeys[m['group_id']],window_key=windows[m['window_id']],
             selector_subtrajectory_ids_json=m['selector_subtrajectory_ids']) for m in members]
        write_table(base/'collection_members.csv',cm,list(dict.fromkeys(k for r in cm for k in r)) or ['collection_id','group_id','window_key','individual_id','selection_status'])
        selector_points=[];selector_segments=[]
        for g in groups:
            for w in g['windows']:
                for p in w['points']:
                    selector_points.append(dict(group_id=g['group_id'],window_key=windows[w['window_id']],individual_id=w['individual_id'],
                        selector_subtrajectory_id=p['trajectory_id'],source_event_key=eventkeys[p['source_row']]))
                for s in w['segments']:
                    selector_segments.append(dict(s,group_id=g['group_id'],window_key=windows[w['window_id']],individual_id=w['individual_id']))
        write_table(base/'selector_points.csv',selector_points,['group_id','window_key','individual_id','selector_subtrajectory_id','source_event_key'])
        write_table(base/'selector_subtrajectories.csv',selector_segments,list(dict.fromkeys(k for s in selector_segments for k in s)) or ['trajectory_id'])
        attrs=[dict(window_key=windows[w['window_id']],**a) for w in [*temporal['candidates'],*temporal['relaxed_candidates']] for a in w['season_attributions']]
        write_table(base/'window_seasons.csv',attrs,['window_key','season','season_year','core_start','core_end','buffer_start','buffer_end'])
        (base/'seasons.json').write_text(json_text(season_metadata if season_metadata is not None else
            seasons_metadata(config.seasons,config.season_buffer_days,config.temporal.week_days))+'\n')
        manifest=json.loads((base/'checkpoint.json').read_text())
        manifest.update(seasonal_schema='pantanal_seasonal_checkpoint/1',selection_policy=config.seasonal_policy,
            collection_count=len(collections),seasonal_software_sha256=config.seasonal_software)
        manifest['files']={k:v for k,v in file_inventory(base).items() if k!='checkpoint.json'}
        (base/'checkpoint.json').write_text(json_text(manifest)+'\n')
        load_selection_checkpoint(base)
        return publish_directory(base,root/base.name,'checkpoint.json')
    finally:shutil.rmtree(temporary,ignore_errors=True)


def write_backing(output,result,temporal):
    scalar=lambda w:{k:v for k,v in w.items() if k not in ('windows','points','segments','source_points')}
    tables=dict(groups=[scalar(g) for g in result['groups']],collections=result['collections'],
        collection_members=result['collection_members'],individual_audit=result['individuals'],
        windows=[scalar(w) for w in [*temporal['candidates'],*temporal['relaxed_candidates']]],
        group_members=[dict(scalar(w),group_id=g['group_id'],
            grouping_calendar_season=g['grouping_calendar_season']) for g in result['groups'] for w in g['windows']],
        trajectory_manifest=[dict(s,group_id=g['group_id'],window_id=w['window_id'],grouping_calendar_season=g['grouping_calendar_season'])
            for g in result['groups'] for w in g['windows'] for s in w['segments']],
        selected_points=[dict(p,group_id=g['group_id'],window_id=w['window_id']) for g in result['groups'] for w in g['windows'] for p in w['points']])
    for name,rows in tables.items():write_csv(output/'data'/f'{name}.csv',rows)
    (output/'seasons.json').write_text(json_text(result['season_metadata'])+'\n')
    # Machine-readable renderer input; unthinned source is authoritative in checkpoint.
    (output/'selection_manifest.json').write_text(json.dumps(result,default=json_default,separators=(',',':'))+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv',default=str(ROOT/'data'/'jaguar_movement_data.csv'))
    parser.add_argument('--output',default=str(ROOT/'analysis'/'pantanal_seasonal_selection'))
    parser.add_argument('--sampling-days',type=float,help='Legacy weekly selector only')
    parser.add_argument('--season-buffer-days',type=float,help='Legacy weekly selector only')
    parser.add_argument('--max-collections',type=int)
    parser.add_argument('--legacy-weekly',action='store_true',help='Use the superseded weekly-window selection; default uses all qualifying bouts with 15-minute jitter')
    parser.add_argument('--seasons-json',help='JSON list of season definitions, or object containing seasons')
    parser.add_argument('--min-observed-span-days',type=float,help='Default sampling-days * 6.5/7')
    parser.add_argument('--growth-buffer-km',type=float,default=5)
    parser.add_argument('--map-padding-km',type=float,default=5)
    parser.add_argument('--max-side-km',type=float,default=40)
    parser.add_argument('--max-area-km2',type=float,default=1600)
    parser.add_argument('--collar-metadata')
    parser.add_argument('--no-report',action='store_true')
    args=parser.parse_args()
    definitions=json.loads(Path(args.seasons_json).read_text()) if args.seasons_json else DEFAULT_SEASONS
    if isinstance(definitions,dict):definitions=definitions['seasons']
    if not args.legacy_weekly:
        if any(x is not None for x in (args.sampling_days,args.season_buffer_days,args.min_observed_span_days)):
            parser.error('Weekly window/span/buffer options require --legacy-weekly; current bouts use no window or season buffer')
        from .movement_processor_pantanal_bouts import BoutConfig, BoutProcessor
        cfg = BoutConfig(csv_path=args.csv, output_dir=args.output, seasons=tuple(definitions),
            gap_jitter_minutes=15, max_collections=1 if args.max_collections is None else args.max_collections,
            spatial=SpatialConfig(growth_buffer_km=args.growth_buffer_km, export_padding_km=args.map_padding_km,
                max_extent_side_km=args.max_side_km, max_extent_area_km2=args.max_area_km2))
        logging.basicConfig(level=logging.INFO,format='%(message)s')
        result=BoutProcessor(cfg).run_pipeline(collar_metadata_path=args.collar_metadata, render=not args.no_report)
        print(result['checkpoint_dir'])
        return
    args.sampling_days = 7 if args.sampling_days is None else args.sampling_days
    args.season_buffer_days = 7 if args.season_buffer_days is None else args.season_buffer_days
    cfg=SeasonalConfig(csv_path=args.csv,output_dir=args.output,seasons=tuple(definitions),
        season_buffer_days=args.season_buffer_days,max_collections=7 if args.max_collections is None else args.max_collections,
        temporal=TemporalConfig(week_days=args.sampling_days,min_week_observed_span_days=(args.min_observed_span_days
            if args.min_observed_span_days is not None else args.sampling_days*6.5/7)),
        spatial=SpatialConfig(growth_buffer_km=args.growth_buffer_km,export_padding_km=args.map_padding_km,
            max_extent_side_km=args.max_side_km,max_extent_area_km2=args.max_area_km2))
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    result=SeasonalProcessor(cfg).run_pipeline(collar_metadata_path=args.collar_metadata,render=not args.no_report)
    print(result['checkpoint_dir'])

if __name__=='__main__':main()
