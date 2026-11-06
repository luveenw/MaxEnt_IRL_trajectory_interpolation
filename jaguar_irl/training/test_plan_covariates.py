"""Representative map years never restrict the training cohort to those years."""
from collections import defaultdict

import pytest

from jaguar_irl.data.pantanal_checkpoint import file_hash
from .plan_covariates import plan_covariates, year_support
from .shared_storage import read
from .test_shared import checkpoint_with_maps


def test_year_counts_individuals_then_animal_days_then_earliest_year():
    routes, windows, points = [], {}, {}
    links = defaultdict(set)

    def add(year, individual, dates):
        route_id = f'route{len(routes)}'
        windows[str(year)] = dict(season='summer', season_year=str(year),
                                  core_start=f'{year}-11-15', core_end=f'{year+1}-03-22')
        routes.append(dict(trajectory_id=route_id, individual_id=individual,
                           parent_window_id=str(year), season='summer'))
        for index, date in enumerate(dates):
            event = f'{route_id}_{index}'
            links[route_id].add(event)
            points[event] = dict(individual_id=individual, timestamp=date)

    # Many fixes from one animal must not outvote two different animals.
    add(2019, 'A', ['2020-01-01'] * 20)
    add(2020, 'A', ['2021-01-01', '2021-01-01'])
    add(2020, 'B', ['2021-01-01'])
    winner, candidates = year_support(routes, windows, links, points)
    assert winner['season_year'] == 2020
    assert winner['animal_day_count'] == 2
    assert winner['display_end'] == '2021-03-21'
    assert winner['query_end_exclusive'] == '2021-03-22T00:00:00'
    # Same individual count, but more distinct observed animal-days wins.
    add(2021, 'A', ['2022-01-01', '2022-01-02'])
    add(2021, 'B', ['2022-01-01'])
    winner, _ = year_support(routes, windows, links, points)
    assert winner['season_year'] == 2021
    # More fragments on the same animal-day do not add another vote/day.
    add(2020, 'B', ['2021-01-01'])
    add(2020, 'A', ['2021-01-02'])
    winner, candidates = year_support(list(reversed(routes)), windows, links, points)
    assert winner['season_year'] == 2020
    assert winner['individual_count'] == 2 and winner['animal_day_count'] == 3
    assert sum(row['trajectory_count'] for row in candidates) == len(routes)
    assert len([row for row in candidates if row['selected_for_covariate_query']]) == 1


def test_planner_keeps_all_years_and_matches_training_admission(tmp_path):
    checkpoint, groups, _, _, export = checkpoint_with_maps(tmp_path)
    original = file_hash(checkpoint / 'checkpoint.json')
    output = tmp_path / 'plans' / 'covariates.json'
    options = dict(collection='WIN-C01', split='unassigned', map_budget_exceptions=groups)
    plan_covariates(checkpoint, export, output, **options)
    plan = read(output)
    assert plan['trajectory_year_filter'] is None
    assert len(plan['groups']) == len(groups)
    assert any(len(group['year_candidates']) > 1 for group in plan['groups'].values())
    assert plan['trajectory_count'] == sum(
        candidate['trajectory_count'] for group in plan['groups'].values()
        for candidate in group['year_candidates'])
    assert {row['admission'] for row in plan['trajectories']} == {'optimizer_candidate'}
    assert file_hash(checkpoint / 'checkpoint.json') == original
    content = output.read_bytes()
    assert plan_covariates(checkpoint, export, output, **options) == output
    assert output.read_bytes() == content
    with pytest.raises(ValueError, match='plan differs'):
        plan_covariates(checkpoint, export, output, **{
            **options, 'exclude_groups': groups[1:], 'map_budget_exceptions': groups[:1]})
    assert output.read_bytes() == content
    other = tmp_path / 'plans' / 'subset.json'
    plan_covariates(checkpoint, export, other, **{
        **options, 'exclude_groups': groups[1:], 'map_budget_exceptions': groups[:1]})
    assert list(read(other)['groups']) == groups[:1]

    # A formal training plan must not use test animals to choose a map year.
    from jaguar_irl.data.export_pantanal_bouts_irl import export_bout_collection
    from .shared_storage import write
    split_path = tmp_path / 'splits.json'
    write(split_path, {'1': 'train', '2': 'test'})
    split_export = export_bout_collection(checkpoint, 'WIN-C01', tmp_path / 'split-export',
                                          split_path=split_path)
    train_group = next(group for group, item in plan['groups'].items()
                       if item['individual_ids'] == ['1'])
    training_path = tmp_path / 'plans' / 'training.json'
    plan_covariates(checkpoint, split_export, training_path, group_ids=[train_group])
    training = read(training_path)
    assert training['split'] == 'train'
    assert {row['individual_id'] for row in training['trajectories']} == {'1'}
    assert all(candidate['individual_ids'] == ['1']
               for candidate in training['groups'][train_group]['year_candidates'])
    full = tmp_path / 'plans' / 'full-training.json'
    plan_covariates(checkpoint, split_export, full, collection='WIN-C01')
    assert set(read(full)['groups']) == {train_group}
    assert read(full)['groups_without_split_evidence']
    testing = tmp_path / 'plans' / 'testing.json'
    plan_covariates(checkpoint, split_export, testing, collection='WIN-C01', split='test')
    assert {r['individual_id'] for r in read(testing)['trajectories']} == {'2'}
    assert read(testing)['split'] == 'test'
    from .shared import prepare, objective, resolve_plan_paths
    import numpy as np
    run = tmp_path / 'run-training'
    prepare(checkpoint, run, collection='WIN-C01', export=split_export)
    fit = read(run / 'plan.json')
    assert fit['training_empty_groups'] == read(full)['groups_without_split_evidence']
    assert fit['training_active_groups'] == [train_group]
    assert {r['individual_id'] for r in fit['trajectories']} == {'1'}
    assert np.isfinite(objective(resolve_plan_paths(fit, run), np.zeros(1))[0])
