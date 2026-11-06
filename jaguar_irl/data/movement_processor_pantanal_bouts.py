"""All qualifying seasonal bouts, with source-preserving seasonal export contracts.

python -m jaguar_irl.data.movement_processor_pantanal_bouts --help
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean

from .movement_processor_pantanal import ROOT, SOURCES, write_csv
from .movement_processor_pantanal_seasonal import (
    SeasonalConfig, SeasonalProcessor, write_backing, write_seasonal_checkpoint,
)
from .movement_temporal import _thin_window, interval_metrics, _hours
from .pantanal_temporal import TemporalConfig
from .pantanal_calendar import summarize_calendar
from .pantanal_checkpoint import file_hash, load_individual_sexes, json_text
from .pantanal_seasons import window_seasons, seasons_metadata
from .pantanal_seasonal_collections import build_collections
from .pantanal_spatial import build_full_study_mcps, export_geojson


POLICY = 'all_seasonal_bouts_two_hour_three_fix_four_hour_v1'
JITTER_POLICY = 'all_seasonal_bouts_two_hour_three_fix_four_hour_jitter15_v2'


@dataclass
class BoutConfig(SeasonalConfig):
    gap_jitter_minutes: int = 0
    output_dir: str = str(ROOT / 'analysis' / 'pantanal_seasonal_bouts')
    # Source: https://www.climatestotravel.com/climate/brazil/pantanal
    # Inherit DEFAULT_SEASONS: user-approved May15/Aug15/Nov15/Mar22 boundaries.
    # Fixed across years/sites; half-open intervals, no cross-season buffer.
    season_buffer_days: float = 0.0
    max_collections: int = 1
    seasonal_policy: str = POLICY
    temporal: TemporalConfig = field(default_factory=lambda: TemporalConfig(
        min_subtrajectory_points=3, max_affected_point_fraction=1,
        max_short_fragment_loss=1, min_week_coverage=0,
        min_week_observed_span_days=0))

    def __post_init__(self):
        if self.gap_jitter_minutes not in (0, 15):
            raise ValueError('Registered gap jitter must be 0 or 15 minutes')
        if self.gap_jitter_minutes:
            self.temporal = replace(self.temporal, max_gap_hours=4.25)
            self.seasonal_policy = JITTER_POLICY
        super().__post_init__()
        t = self.temporal
        if (t.target_interval_hours, t.regular_min_hours, t.regular_max_hours,
                t.max_gap_hours, t.min_subtrajectory_points,
                t.max_affected_point_fraction) != (2, 1.5, 2.5, 4 + self.gap_jitter_minutes / 60, 3, 1):
            raise ValueError('Main policy requires target 2 h, band 1.5–2.5 h, cap 4 h, minimum 3 and no affected-point budget')
        expected_policy = JITTER_POLICY if self.gap_jitter_minutes else POLICY
        if self.season_buffer_days != 0 or self.seasonal_policy != expected_policy:
            raise ValueError('Main policy requires zero season buffer and the registered policy identity')


def policy_metadata(config):
    return dict(policy=config.seasonal_policy, target_interval_hours=2, regular_min_hours=1.5,
        regular_max_hours=2.5, nominal_max_gap_hours=4,
        gap_jitter_minutes=config.gap_jitter_minutes,
        hard_gap_hours=config.temporal.max_gap_hours, min_selected_fixes=3,
        forgiveness_factor=2, season_buffer_days=0,
        all_years=True, all_qualifying_bouts=True, affected_point_budget_enabled=False,
        weekly_density_gate_enabled=False, weekly_span_gate_enabled=False,
        short_fragment_loss_gate_enabled=False,
        compatibility_note='TemporalConfig week-related fields are unused by this scanner.',
        timestamp_basis='Source timestamps as recorded; timezone unspecified, no conversion assumed.',
        source_preservation='Every native observation inside each accepted bout, including unselected trailing fixes.',
        sensitivity_policies=['minimum_five_selected_fixes', 'native_three_fixes_four_hour_cap',
                              'two_hour_three_fixes_eight_hour_cap'],
        ecological_status='Temporal eligibility only; residence, missingness mechanism and habitat fidelity are not established.',
        duration_status='Actual intervals retained; no duration-aware iSSA correction is implemented in MaxEnt.',
        spatial=asdict(config.spatial))


def source_runs(records, seasons, cap):
    """Partition before sampling; never join tags, season occurrences or hard gaps."""
    runs = []
    for p in sorted(records, key=lambda r: (r['individual_id'], r['timestamp'])):
        attr, = window_seasons(p['timestamp'], p['timestamp'], seasons, buffer_days=0)
        key = p['individual_id'], p.get('tag_id', ''), attr['season'], attr['season_year']
        prior = runs[-1] if runs else None
        if prior is None or prior['key'] != key or _hours(prior['raw'][-1]['timestamp'], p['timestamp']) > cap:
            runs.append(dict(key=key, attr=attr, raw=[]))
        runs[-1]['raw'].append(p)
    return runs


def sampled_parts(raw, temporal):
    times = [p['timestamp'] for p in raw]
    selected = _thin_window(raw, times, 0, len(raw), temporal)
    parts = []
    for p in selected:
        if not parts or _hours(parts[-1][-1]['timestamp'], p['timestamp']) > temporal.max_gap_hours:
            parts.append([])
        parts[-1].append(p)
    # Include native trailing observations, but never share one between bouts.
    indices = {p['source_row']: n for n, p in enumerate(raw)}
    for n, part in enumerate(parts):
        lo = indices[part[0]['source_row']]
        hi = indices[parts[n + 1][0]['source_row']] if n + 1 < len(parts) else len(raw)
        yield part, raw[lo:hi]


def make_window(part, raw, attr, temporal):
    first, last = part[0], part[-1]
    ident = first['individual_id']
    window_id = f"jaguar_{ident}_{first['timestamp']:%Y%m%dT%H%M%S}_bout"
    tid = window_id + '_s001'
    m = interval_metrics(part, temporal)
    duration = _hours(first['timestamp'], last['timestamp'])
    points = [dict(p, trajectory_id=tid, window_id=window_id, step_index=n,
                   dt_hours=None if n == 0 else m['gaps'][n-1],
                   source_dt_hours=None if n == 0 else m['gaps'][n-1],
                   elapsed_hours=_hours(first['timestamp'], p['timestamp']),
                   window_elapsed_hours=_hours(first['timestamp'], p['timestamp']),
                   affected_by_gap=n in m['affected_indices']) for n, p in enumerate(part)]
    moved = [(a['longitude'], a['latitude']) != (b['longitude'], b['latitude'])
             for a, b in zip(part, part[1:])]
    defined_turns = sum(a and b for a, b in zip(moved, moved[1:]))
    segment = dict(trajectory_id=tid, individual_id=ident, start=first['timestamp'],
        end=last['timestamp'], duration_hours=duration, n_points=len(part),
        affected_point_fraction=m['affected_point_fraction'], regular_fraction=m['regular_fraction'],
        max_gap_hours=m['max_gap_hours'], defined_turn_count=defined_turns,
        five_point_eligible=len(part) >= 5)
    return dict(individual_id=ident, window_id=window_id, year=first['timestamp'].year,
        month=first['timestamp'].month, study=first.get('study', ''), country=first.get('country', ''),
        start=raw[0]['timestamp'], end=raw[-1]['timestamp'], window_end_exclusive=False,
        observed_start=first['timestamp'], observed_end=last['timestamp'],
        duration_days=duration/24, window_duration_days=_hours(raw[0]['timestamp'], raw[-1]['timestamp'])/24,
        raw_fixes=len(raw), resampled_fixes=len(part), selected_fixes=len(part),
        expected_fixes=duration/temporal.target_interval_hours+1,
        coverage_fraction=len(part)/(duration/temporal.target_interval_hours+1),
        regular_fraction=m['regular_fraction'], affected_point_fraction=m['affected_point_fraction'],
        max_gap_hours=m['max_gap_hours'], max_within_segment_gap_hours=m['max_gap_hours'],
        max_source_gap_hours=interval_metrics(raw, temporal)['max_gap_hours'],
        n_subtrajectories=1, short_fragment_loss=0, dropped_short_fixes=0,
        mean_interval_error_hours=mean(abs(x-temporal.target_interval_hours) for x in m['gaps']),
        usable_duration_hours=duration, defined_turn_count=defined_turns,
        five_point_eligible=len(part) >= 5, requires_week_relaxation=False,
        protected_rules_pass=True, violation_codes=[], violation_text='',
        season_attributions=[attr], points=points, source_points=raw, segments=[segment])


def scan_bouts(records, config):
    main = []
    rejected = []
    audits = []
    sensitivity = []
    by_id = defaultdict(list)
    for p in records:
        by_id[p['individual_id']].append(p)
    t = config.temporal
    for ident in config.individual_ids:
        raw = by_id[ident]
        runs = source_runs(raw, config.seasons, t.max_gap_hours)
        windows = []
        for run in runs:
            for selected, source in sampled_parts(run['raw'], t):
                if len(selected) >= 3:
                    windows.append(make_window(selected, source, run['attr'], t))
                else:
                    rejected.append(dict(individual_id=ident, **run['attr'],
                        start=source[0]['timestamp'], end=source[-1]['timestamp'],
                        selected_fixes=len(selected), raw_fixes=len(source),
                        reason='fewer_than_three_selected_fixes',
                        source_rows=[p['source_row'] for p in source]))
        eight = []
        for run in source_runs(raw, config.seasons, 8):
            for part, source in sampled_parts(run['raw'], replace(t, max_gap_hours=8)):
                if len(part) >= 3:
                    eight.append(dict(attr=run['attr'], points=part, source_points=source))
        for definition in config.seasons:
            season = definition['name']
            ws = [w for w in windows if w['season_attributions'][0]['season'] == season]
            sr = [r for r in runs if r['attr']['season'] == season]
            er = [r for r in eight if r['attr']['season'] == season]
            main_events = {p['source_row'] for w in ws for p in w['points']}
            source_events = {p['source_row'] for w in ws for p in w['source_points']}
            eight_events = {p['source_row'] for w in er for p in w['points']}
            native_events = {p['source_row'] for r in sr if len(r['raw']) >= 3 for p in r['raw']}
            five = [w for w in ws if w['five_point_eligible']]
            sensitivity.append(dict(individual_id=ident, season=season,
                raw_fixes=sum(len(r['raw']) for r in sr), source_runs=len(sr),
                main_bouts=len(ws), main_selected_fixes=len(main_events),
                main_source_fixes=len(source_events), main_defined_turns=sum(w['defined_turn_count'] for w in ws),
                five_point_bouts=len(five), five_point_selected_fixes=sum(w['selected_fixes'] for w in five),
                native_three_point_bouts=sum(len(r['raw']) >= 3 for r in sr),
                native_three_point_fixes=len(native_events),
                native_eligible_fixes_outside_main=len(native_events-source_events),
                eight_hour_bouts=len(er), eight_hour_selected_fixes=len(eight_events),
                eight_hour_gained_selected_fixes=len(eight_events-main_events),
                eight_hour_lost_selected_fixes=len(main_events-eight_events),
                status='selected' if ws else 'no_fixes_in_season' if not sr else 'no_three_fix_two_hour_bout'))
        retained = {p['source_row'] for w in windows for p in w['source_points']}
        selected = {p['source_row'] for w in windows for p in w['points']}
        audits.append(dict(individual_id=ident, study=raw[0]['study'] if raw else '',
            n_raw_fixes=len(raw), first_fix=min((p['timestamp'] for p in raw), default=None),
            last_fix=max((p['timestamp'] for p in raw), default=None), n_bouts=len(windows),
            n_selected_fixes=len(selected), n_source_fixes_preserved=len(retained),
            n_unselected_source_fixes_preserved=len(retained-selected),
            n_source_fixes_outside_selected_bouts=len(raw)-len(retained),
            seasons=sorted({w['season_attributions'][0]['season'] for w in windows}),
            status='selected' if windows else 'no_three_fix_two_hour_bout'))
        main.extend(windows)
    summary = []
    for definition in config.seasons:
        name = definition['name']
        rows = [r for r in sensitivity if r['season'] == name]
        keys = [k for k, v in rows[0].items() if isinstance(v, int) and k != 'individual_id']
        summary.append(dict(season=name, n_individuals=sum(r['main_bouts'] > 0 for r in rows),
            five_point_individuals=sum(r['five_point_bouts'] > 0 for r in rows),
            native_individuals=sum(r['native_three_point_bouts'] > 0 for r in rows),
            eight_hour_individuals=sum(r['eight_hour_bouts'] > 0 for r in rows),
            **{k: sum(r[k] for r in rows) for k in keys}))
    return dict(candidates=main, relaxed_candidates=[], individuals=audits,
                rejected_bouts=rejected, sensitivity=sensitivity, season_summary=summary)


def aggregate_windows(windows):
    """One surrogate per animal for map grouping only; preserve every real bout."""
    by_id = defaultdict(list)
    for w in windows:
        by_id[w['individual_id']].append(w)
    result = {}
    for ident, ws in sorted(by_id.items()):
        ws.sort(key=lambda w: w['start'])
        points = [p for w in ws for p in w['points']]
        source = [p for w in ws for p in w['source_points']]
        attrs = { (a['season'], a['season_year']): a for w in ws for a in w['season_attributions'] }
        result[ident] = dict(ws[0], window_id=f"aggregate_{ident}_{ws[0]['season_attributions'][0]['season']}",
            start=ws[0]['start'], end=ws[-1]['end'], observed_start=ws[0]['observed_start'],
            observed_end=ws[-1]['observed_end'], selected_fixes=len(points), raw_fixes=len(source),
            coverage_fraction=sum(w['selected_fixes'] for w in ws)/sum(w['expected_fixes'] for w in ws),
            affected_point_fraction=sum(w['affected_point_fraction']*w['selected_fixes'] for w in ws)/len(points),
            n_subtrajectories=len(ws), source_points=source, points=points,
            segments=[s for w in ws for s in w['segments']], season_attributions=list(attrs.values()),
            bout_windows=ws)
    return result


def retention_row(raw_fixes, selected_fixes, preserved_native_fixes, **identity):
    """Percentages use all QC-passed native fixes in the animal's season."""
    if not 0 <= selected_fixes <= preserved_native_fixes <= raw_fixes:
        raise ValueError('Inconsistent seasonal retention counts')
    return dict(identity, raw_fixes=raw_fixes, selected_fixes=selected_fixes,
        preserved_native_fixes=preserved_native_fixes,
        selected_retention_pct=100*selected_fixes/raw_fixes if raw_fixes else None,
        native_preservation_pct=100*preserved_native_fixes/raw_fixes if raw_fixes else None)


def seasonal_retention(temporal, groups):
    """All animals (including zero retention), plus each map-group membership.

    Group denominators include ALL seasonal observations of their member animals,
    including observations outside accepted bouts. Alternative groups overlap.
    """
    individuals = [retention_row(r['raw_fixes'], r['main_selected_fixes'], r['main_source_fixes'],
        individual_id=r['individual_id'], season=r['season'], bouts=r['main_bouts'],
        status=r['status']) for r in temporal['sensitivity']]
    lookup = {(r['season'], r['individual_id']): r for r in individuals}
    members, summaries = [], []
    for group in groups:
        by_id = defaultdict(dict)
        for w in group['windows']:
            by_id[w['individual_id']][w['window_id']] = w
        rows = []
        for ident, unique in sorted(by_id.items()):
            ws = list(unique.values())
            selected = {p['source_row'] for w in ws for p in w['points']}
            source = {p['source_row'] for w in ws for p in w['source_points']}
            row = retention_row(lookup[group['season'], ident]['raw_fixes'], len(selected), len(source),
                group_id=group['group_id'], season=group['season'], individual_id=ident,
                bouts=len(ws), season_years=sorted({w['season_attributions'][0]['season_year'] for w in ws}))
            rows.append(row)
        members.extend(rows)
        summaries.append(retention_row(sum(r['raw_fixes'] for r in rows),
            sum(r['selected_fixes'] for r in rows), sum(r['preserved_native_fixes'] for r in rows),
            group_id=group['group_id'], season=group['season'], individuals=len(rows),
            bouts=sum(r['bouts'] for r in rows)))
    for r in temporal['season_summary']:
        r.update(retention_row(r['raw_fixes'], r['main_selected_fixes'], r['main_source_fixes']))
    return dict(season_individual_coverage=individuals, group_individual_coverage=members,
                group_season_coverage=summaries)


class BoutProcessor(SeasonalProcessor):
    def __init__(self, config=None):
        super().__init__(config or BoutConfig())

    def candidate_pools(self, candidates):
        pool = aggregate_windows([w for w in candidates
            if w['season_attributions'][0]['season'] == self.active_season])
        if pool:
            yield min(w['month'] for w in pool.values()), pool

    def build_group(self, *args, **kwargs):
        group = super().build_group(*args, **kwargs)
        group['windows'] = [w for aggregate in group['windows'] for w in aggregate['bout_windows']]
        group['n_bouts'] = len(group['windows'])
        group['shared_week_overlap_days'] = None  # Envelope overlap is not simultaneous bout support.
        group['coverage_unit'] = 'all_bouts_for_each_individual_in_this_season'
        return group

    def run_pipeline(self, *, collar_metadata_path=None, render=True):
        output = Path(self.config.output_dir).resolve()
        for name in ('pantanal_selection',):
            protected = (ROOT/'analysis'/name).resolve()
            if output == protected or protected in output.parents:
                raise ValueError('Bout output must not overwrite existing selection folders')
        self.config.seasonal_software = {p.name: file_hash(p) for p in Path(__file__).parent.glob('*.py')
            if not p.name.startswith('test_') and ('season' in p.name or 'bout' in p.name)}
        self.parse()
        by_row = {p['source_row']: p for p in self.records}
        with Path(self.config.csv_path).open(newline='', encoding='utf-8-sig') as handle:
            for n, original in enumerate(csv.DictReader(handle), 2):
                if n in by_row:
                    by_row[n]['tag_id'] = original.get('tag.local.identifier', '')
        collar_metadata_path = collar_metadata_path or ROOT/'data'/'Jaguar_additional_information_fixed.csv'
        self.individual_sexes = load_individual_sexes(collar_metadata_path, self.config.individual_ids)
        temporal = scan_bouts(self.records, self.config)
        for a in temporal['individuals']:
            a.update(self.individual_sexes[a['individual_id']])
        mcps = build_full_study_mcps(self.records, self.config.individual_ids, self.config.spatial)
        groups = self.generate_groups(temporal, mcps)
        coverage = seasonal_retention(temporal, groups)
        collections, members = build_collections(groups, max_collections=self.config.max_collections,
                                                 cohort_ids=self.config.individual_ids)
        windows = {w['window_id']: w for w in temporal['candidates']}
        for c in collections:
            owned = [m for m in members if m['collection_id'] == c['collection_id'] and m['selection_status'] == 'selected']
            expected = {k for k,w in windows.items() if w['season_attributions'][0]['season'] == c['season']}
            if {m['window_id'] for m in owned} != expected:
                raise ValueError('Collection dropped qualifying bouts')
            points = [p for m in owned for p in windows[m['window_id']]['source_points']]
            if len({p['source_row'] for p in points}) != len(points):
                raise ValueError('Collection repeats source evidence')
            c.update(summarize_calendar(points), all_qualifying_bouts_preserved=True,
                n_source_fixes=len(points), n_selected_fixes=sum(windows[m['window_id']]['selected_fixes'] for m in owned))
            c['months'], c['years'] = c['observed_months'], c['observed_years']
        output.mkdir(parents=True, exist_ok=True)
        (output/'data').mkdir(exist_ok=True)
        metadata = seasons_metadata(self.config.seasons, 0, None)
        metadata.update(source_status='Source URL supplied and dates explicitly confirmed by user on 2026-11-02; no fresh verification claimed.',
            membership_rule='Split at every half-open core season boundary; all years pooled; no buffer.')
        checkpoint = write_seasonal_checkpoint(self.config, self.records, temporal, groups, mcps,
            self.parse_audit, collections, members, collar_metadata_path, season_metadata=metadata)
        export_geojson(mcps, output/'mcp95_full_study.geojson')
        result = dict(config=asdict(self.config), policy=policy_metadata(self.config),
            seasons=list(self.config.seasons), season_metadata=metadata, collections=collections,
            collection_members=members, groups=groups, individuals=temporal['individuals'],
            season_summary=temporal['season_summary'], checkpoint_dir=str(checkpoint), sources=SOURCES,
            mcps_geojson=json.loads((output/'mcp95_full_study.geojson').read_text()),
            provenance=dict(generated_utc=datetime.now(timezone.utc).isoformat(), source_sha256=file_hash(self.config.csv_path)),
            **coverage)
        write_backing(output, result, temporal)
        for name in ('rejected_bouts', 'sensitivity', 'season_summary'):
            write_csv(output/'data'/f'{name}.csv', temporal[name])
        for name, rows in coverage.items():
            write_csv(output/'data'/f'{name}.csv', rows)
        (output/'cutoffs.json').write_text(json_text(result['policy'])+'\n')
        if render:
            from .pantanal_bout_report import write_report
            write_report(output, result)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', default=str(ROOT/'data'/'jaguar_movement_data.csv'))
    parser.add_argument('--output', default=str(ROOT/'analysis'/'pantanal_seasonal_bouts'))
    parser.add_argument('--collar-metadata')
    parser.add_argument('--max-collections', type=int, default=1)
    parser.add_argument('--gap-jitter-minutes', type=int, choices=(0, 15), default=15)
    parser.add_argument('--no-report', action='store_true')
    args = parser.parse_args()
    result = BoutProcessor(BoutConfig(csv_path=args.csv, output_dir=args.output,
        max_collections=args.max_collections, gap_jitter_minutes=args.gap_jitter_minutes)).run_pipeline(collar_metadata_path=args.collar_metadata,
                                                           render=not args.no_report)
    print(json_text(dict(checkpoint_dir=result['checkpoint_dir'], season_summary=result['season_summary'])))


if __name__ == '__main__':
    main()
