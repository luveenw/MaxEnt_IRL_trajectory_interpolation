"""Choose covariate query years from training evidence, without filtering it.

This local planner needs no rasters or Earth Engine connection. It pins the
existing grids and reports support for every observed season-year per group.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from jaguar_irl.data.export_pantanal_bouts_irl import POLICY, JITTER_POLICY
from jaguar_irl.data.export_pantanal_irl import validate_export
from jaguar_irl.data.pantanal_checkpoint import file_hash, load_selection_checkpoint, read_table
from .shared import (
    group_lookup, pin_trajectories, selected_groups, software, resolve_map_budget_exceptions,
)
from .shared_storage import locked, read, sync_dir, write

SCHEMA = 'pantanal_covariate_plan/1'
YEAR_RULE = ['most_distinct_individuals', 'most_distinct_animal_days', 'earliest_season_year']


def year_support(routes, windows, links, points):
    """Count individuals once per season-year and days once per individual.

    Season-year comes from the selection checkpoint, not the calendar year of
    each fix. Dates retain the source clock; no timezone conversion is implied.
    All admitted routes contribute, including routes outside the winning year.
    """
    years = {}
    for route in routes:
        window = windows[route['parent_window_id']]
        year = int(window['season_year'])
        dates = (window['core_start'], window['core_end'])
        entry = years.setdefault(year, dict(dates=dates, individuals=set(), days=set(),
                                           events=set(), trajectories=[]))
        if entry['dates'] != dates or window['season'] != route['season']:
            raise ValueError('Inconsistent season windows in group')
        individual = route['individual_id']
        entry['individuals'].add(individual)
        entry['trajectories'].append(route['trajectory_id'])
        events = links[route['trajectory_id']]
        if not events:
            raise ValueError('Missing source observations for year selection')
        for event in events:
            point = points[event]
            if point['individual_id'] != individual:
                raise ValueError('Source point individual differs from trajectory')
            date = datetime.fromisoformat(point['timestamp'])
            if not datetime.fromisoformat(dates[0]) <= date < datetime.fromisoformat(dates[1]):
                raise ValueError('Observation lies outside its recorded season window')
            entry['days'].add((individual, date.date().isoformat()))
            entry['events'].add(event)

    if not years:
        raise ValueError('Cannot choose a representative year without trajectories')
    candidates = []
    for year, entry in sorted(years.items()):
        start, end = (datetime.fromisoformat(date) for date in entry['dates'])
        candidates.append(dict(
            season_year=year, individual_count=len(entry['individuals']),
            individual_ids=sorted(entry['individuals']), animal_day_count=len(entry['days']),
            source_observation_count=len(entry['events']), trajectory_count=len(entry['trajectories']),
            trajectory_ids=sorted(entry['trajectories']),
            query_start=start.isoformat(), query_end_exclusive=end.isoformat(),
            display_start=start.date().isoformat(),
            display_end=(end - timedelta(days=1)).date().isoformat(),
        ))
    winner = min(candidates, key=lambda item: (
        -item['individual_count'], -item['animal_day_count'], item['season_year']))
    for candidate in candidates:
        candidate['selected_for_covariate_query'] = candidate is winner
    return winner, candidates


def plan_covariates(checkpoint, export, output, group_ids=None, collection=None,
                    split='train', exclude_groups=None, map_budget_exceptions=None):
    """Persist an auditable, repeatable map-query plan; never modify source inputs."""
    checkpoint, export, output = (Path(path).resolve() for path in (checkpoint, export, output))
    cp = load_selection_checkpoint(checkpoint)
    if cp['manifest']['selection_policy'] not in (POLICY, JITTER_POLICY):
        raise ValueError('Require a registered seasonal bout checkpoint')
    if split not in ('train', 'test', 'unassigned'):
        raise ValueError('Choose train, test, or explicitly exploratory unassigned evidence')
    excluded = sorted(set(exclude_groups or []))
    groups = selected_groups(checkpoint, group_ids, collection, excluded)
    exceptions = resolve_map_budget_exceptions(cp, groups, map_budget_exceptions or ())
    lookup = group_lookup(cp)
    export_manifest = validate_export(export)
    checkpoint_hash = file_hash(checkpoint / 'checkpoint.json')
    if export_manifest['checkpoint_sha256'] != checkpoint_hash:
        raise ValueError('Export belongs to a different checkpoint')
    if collection and export_manifest.get('collection_id') != collection:
        raise ValueError('Export belongs to a different collection')
    # Reuse exactly the trainer's route admission, identity and grid checks.
    grid_bindings = {'groups': {group: {'grid_key': lookup[group]['grid_key']} for group in groups}}
    pinned, exclusions = pin_trajectories(export, groups, split, grid_bindings, exceptions)
    manifest = {row['trajectory_id']: row for row in read_table(export / 'data/trajectory_manifest.csv')}
    routes = [manifest[route['trajectory_id']] for route in pinned]
    seasons = {row['season'] for row in routes}
    if len(seasons) != 1:
        raise ValueError('A covariate plan must contain exactly one season')
    windows = {row['window_key']: row for row in read_table(checkpoint / 'window_seasons.csv')}
    links = defaultdict(set)
    for row in read_table(export / 'data/point_links.csv'):
        links[row['trajectory_id']].add(row['source_event_key'])
    points = {row['source_event_key']: row for row in read_table(export / 'data/source_points.csv')}

    planned = {}
    for group in groups:
        group_routes = [row for row in routes if row['group_id'] == group]
        if not group_routes:
            continue
        winner, candidates = year_support(group_routes, windows, links, points)
        grid = cp['grids'][lookup[group]['grid_key']]
        xmin, _, _, ymax = grid['bounds']
        cell = grid['cell_size_m']
        planned[group] = dict(
            grid_key=lookup[group]['grid_key'], grid=grid,
            crs_transform=[cell, 0, xmin, 0, -cell, ymax],
            float32_bytes_per_feature=grid['rows'] * grid['cols'] * 4,
            representative_season_year=winner['season_year'],
            query_start=winner['query_start'], query_end_exclusive=winner['query_end_exclusive'],
            display_start=winner['display_start'], display_end=winner['display_end'],
            year_candidates=candidates,
            trajectory_count=len(group_routes),
            individual_ids=sorted({row['individual_id'] for row in group_routes}),
            trajectory_ids=sorted(row['trajectory_id'] for row in group_routes),
        )
    plan = dict(
        schema=SCHEMA, biome='Pantanal', season=next(iter(seasons)), collection=collection,
        checkpoint=str(checkpoint), checkpoint_sha256=checkpoint_hash,
        export=str(export), export_sha256=file_hash(export / 'export_manifest.json'),
        split=split, excluded_groups=excluded, map_budget_exceptions=exceptions,
        requested_groups=groups, groups_without_split_evidence=sorted(set(groups) - set(planned)),
        representative_year_rule=YEAR_RULE, trajectory_year_filter=None,
        temporal_scope='static_season_across_years', groups=planned,
        trajectories=pinned, exclusions=exclusions,
        trajectory_count=len(pinned), individual_count=len({row['individual_id'] for row in pinned}),
        source_product_availability='not_checked',
        software={**software(), Path(__file__).name: file_hash(__file__)},
    )
    with locked(output.parent):
        if output.exists():
            if read(output) != plan:
                raise ValueError('Covariate plan differs; choose a new output path')
        else:
            pending = output.with_name('.' + output.name + '.pending')
            write(pending, plan)
            pending.replace(output)
            sync_dir(output.parent)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--export', required=True)
    parser.add_argument('--output', required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--collection')
    selection.add_argument('--group', dest='group_ids', action='append')
    parser.add_argument('--split', choices=['train', 'test', 'unassigned'], default='train')
    parser.add_argument('--exclude-group', dest='exclude_groups', action='append')
    parser.add_argument('--allow-map-budget-exception', dest='map_budget_exceptions', action='append')
    print(plan_covariates(**vars(parser.parse_args())))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, FileNotFoundError, FileExistsError, KeyError) as error:
        raise SystemExit(f'Error: {error}') from None
