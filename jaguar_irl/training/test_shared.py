"""Numerical and end-to-end contracts for joint static reward training."""
import csv
import gzip
import itertools
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from jaguar_irl.core.shared_reward import MOVES, statistics
from jaguar_irl.data.pantanal_checkpoint import file_hash
from jaguar_irl.training import shared, shared_storage, transfer
from jaguar_irl.training.shared import (
    SCHEMA, bind, objective, prepare, software, template, train,
)
from jaguar_irl.training.shared_storage import locked, publish, read, write


def test_exact_likelihood_gradient_against_enumeration():
    rng = np.random.default_rng(42)
    features = rng.normal(size=(3, 3, 4))
    weights = np.array([0.4, -0.7, 0.2])
    route = np.array([[0, 0], [1, 1], [1, 2], [2, 3]])
    counts = []
    for actions in itertools.product(MOVES, repeat=3):
        path = [route[0]]
        for move in actions:
            path.append(path[-1] + move)
        path = np.array(path)
        if (np.any(path < 0) or np.any(path >= [3, 4])
                or not np.array_equal(path[-1], route[-1])):
            continue
        counts.append(features[:, path[:-1, 0], path[:-1, 1]].sum(axis=1))
    counts = np.array(counts)
    score = counts @ weights
    logz = np.logaddexp.reduce(score)
    empirical = features[:, route[:-1, 0], route[:-1, 1]].sum(axis=1)
    value, gradient = statistics(features, weights, route)
    assert value == pytest.approx(empirical @ weights - logz)
    assert np.allclose(gradient, empirical - np.exp(score - logz) @ counts)
    numeric = []
    for index in range(3):
        delta = np.eye(3)[index] * 1e-5
        numeric.append((statistics(features, weights + delta, route)[0]
                        - statistics(features, weights - delta, route)[0]) / 2e-5)
    assert np.allclose(gradient, numeric, atol=1e-8)
    with pytest.raises(ValueError, match='memory budget'):
        statistics(features, weights, route, max_state_cells=1)


def tiny_plan(tmp_path):
    """Three distinct extent sizes and two animals, including a shared animal ID."""
    checkpoint = tmp_path / 'cp'
    checkpoint.mkdir()
    write(checkpoint / 'checkpoint.json', {'files': {}})
    export = tmp_path / 'export'
    export.mkdir()
    write(export / 'export_manifest.json', {'files': {}})
    bindings = {
        'biome': 'Pantanal',
        'features': [dict(name='a', offset=0.0, scale=1.0),
                     dict(name='b', offset=0.0, scale=2.0)],
        'groups': {},
    }
    rows = []
    rng = np.random.default_rng(91)
    for index, shape in enumerate([(3, 4), (4, 5), (5, 6)], 1):
        group_id = f'G{index}'
        files = {}
        for name in ['a', 'b']:
            path = tmp_path / f'{group_id}_{name}.npy'
            np.save(path, rng.normal(size=shape))
            files[name] = dict(path=str(path), sha256=file_hash(path))
        bindings['groups'][group_id] = dict(
            files=files, season='winter', grid_key='grid_' + group_id,
        )
        path = tmp_path / f'{group_id}_route.npy'
        np.save(path, [[0, 0, 0], [1, 1, 1], [1, 2, 2], [2, 3, 3]])
        rows.append(dict(group_id=group_id, individual_id=str(1 if index < 3 else 2),
                         path=str(path), sha256=file_hash(path)))
    binding_path = tmp_path / 'binding.json'
    write(binding_path, bindings)
    return dict(
        schema=SCHEMA, weighting='equal_individual_mean_trajectory',
        checkpoint=str(checkpoint), checkpoint_sha256=file_hash(checkpoint / 'checkpoint.json'),
        export=str(export), export_sha256=file_hash(export / 'export_manifest.json'),
        binding_path=str(binding_path), binding_sha256=file_hash(binding_path),
        bindings=bindings, groups=['G1', 'G2', 'G3'], trajectories=rows, software=software(),
        optimizer=dict(l2=0.02, iterations=3, learning_rate=0.2,
                       tolerance=1e-12, max_state_cells=10000),
    )


def make_run(tmp_path, name, plan):
    run = tmp_path / name
    run.mkdir()
    write(run / 'plan.json', plan)
    return run


def current(run):
    return read(run / 'current/state.json')


def test_joint_resume_idempotency_and_input_mutation(tmp_path, monkeypatch):
    plan = tiny_plan(tmp_path)
    full = make_run(tmp_path, 'full', plan)
    train(full)
    expected = current(full)
    assert expected['groups'] == plan['groups']
    assert expected['iteration'] == 3  # Total budget, not three updates per group.
    assert all(a['objective'] <= b['objective']
               for a, b in zip(expected['history'], expected['history'][1:]))

    resumed = make_run(tmp_path, 'resumed', plan)
    train(resumed, max_updates=0)
    assert current(resumed)['iteration'] == 0
    assert current(resumed)['groups'] == plan['groups']
    train(resumed, max_updates=1)
    assert current(resumed)['iteration'] == 1
    train(resumed)
    assert current(resumed) == expected
    assert (resumed / 'current').readlink() == (full / 'current').readlink()
    assert not (resumed / 'current/stages').exists()

    def unexpected_evaluation(*args):
        pytest.fail('Completed resume must not re-evaluate the objective')

    monkeypatch.setattr(shared, 'objective', unexpected_evaluation)
    pointer = (resumed / 'current').readlink()
    train(resumed)
    assert (resumed / 'current').readlink() == pointer
    np.save(Path(plan['trajectories'][0]['path']), [[0, 0, 0]])
    with pytest.raises(ValueError, match='changed'):
        train(resumed)


def test_each_evaluation_uses_all_groups_at_the_same_weights(tmp_path, monkeypatch):
    plan = tiny_plan(tmp_path)
    run = make_run(tmp_path, 'run', plan)
    calls = []

    def record(features, weights, *args):
        calls.append((features.shape[1:], weights.copy()))
        return statistics(features, weights, *args)

    monkeypatch.setattr(shared, 'statistics', record)
    train(run, max_updates=1)
    assert len(calls) >= 6  # Initial evaluation plus one accepted update.
    assert len(calls) % 3 == 0
    for offset in range(0, len(calls), 3):
        group_calls = calls[offset:offset + 3]
        assert [shape for shape, _ in group_calls] == [(3, 4), (4, 5), (5, 6)]
        assert all(np.array_equal(weights, group_calls[0][1]) for _, weights in group_calls)
    assert current(run)['iteration'] == 1


def test_progress_tracks_evaluations_checkpoints_and_resume(tmp_path):
    plan = tiny_plan(tmp_path)
    run = make_run(tmp_path, 'logged', plan)
    train(run, max_updates=1)
    rows = [json.loads(line) for line in (run / 'progress.jsonl').read_text().splitlines()]
    assert [r['event'] for r in rows] == ['checkpoint_published', 'training_paused']
    assert rows[0]['iteration'] == 1 and rows[0]['route_completed'] == 3
    last = read(run / 'progress.json')
    assert last['event'] == 'training_paused' and last['iteration'] == 1
    assert last['elapsed_s'] >= 0 and last['peak_rss_mib'] > 0
    prior = last['total_elapsed_s']
    train(run, trace_routes=True)
    rows = [json.loads(line) for line in (run / 'progress.jsonl').read_text().splitlines()]
    assert any(r['event'] == 'route_started' and r['function'] == 'statistics' for r in rows)
    last = read(run / 'progress.json')
    assert last['event'] == 'training_complete' and last['total_elapsed_s'] >= prior
    assert last['invocation'] != rows[0]['invocation']
    assert current(run)['iteration'] == 3


def test_log_rotation_recovers_interrupted_archive_and_audits_expiry(tmp_path):
    path = tmp_path / 'progress.jsonl'
    closed = tmp_path / 'progress.jsonl.20000101T000000.000000Z.01234567'
    pending = closed.with_name(closed.name + '.gz.pending')
    closed.write_bytes(b'old\n')
    pending.write_bytes(b'partial archive')
    events = []

    def audit(event, **fields):
        events.append((event, fields))

    with shared.SplitLog(path, limit=8, keep_archives=1, audit=audit) as log:
        recovered = closed.with_name(closed.name + '.gz')
        assert gzip.decompress(recovered.read_bytes()) == b'old\n'
        assert not pending.exists() and not closed.exists()
        log.write('first')
        log.write('second')

    archive, = tmp_path.glob('progress.jsonl.*.gz')
    assert gzip.decompress(archive.read_bytes()) == b'first\n'
    assert path.read_bytes() == b'second\n'
    assert [event for event, _ in events] == [
        'log_compressed', 'log_rotated', 'log_compressed', 'log_archive_reaped',
    ]
    assert events[-1][1]['archive'] == recovered.name
    assert events[-1][1]['bytes_reclaimed'] > 0


def test_rolling_retention_preserves_cross_directory_continuation(tmp_path):
    plan = tiny_plan(tmp_path)
    plan['optimizer']['iterations'] = 8
    source = make_run(tmp_path, 'source', plan)
    train(source, max_updates=1)
    pinned = (source / 'current').resolve()
    child = tmp_path / 'other-root' / 'child'
    shared.continue_run(source, child)

    train(source, max_updates=6)
    assert {read(path / 'state.json')['iteration'] for path in (source / 'versions').iterdir()} == {
        1, 3, 4, 5, 6, 7,
    }
    train(source)
    assert set((source / 'versions').iterdir()) == {pinned, (source / 'current').resolve()}
    assert current(source)['iteration'] == 8
    audit = [json.loads(line) for line in (source / 'housekeeping.jsonl').read_text().splitlines()]
    reaps = [row for row in audit if row['event'] == 'checkpoints_reaped']
    assert any(not row['complete'] for row in reaps)
    assert reaps[-1]['complete']
    assert len({key for row in reaps for key in row['removed']}) == 7
    assert all(pinned.name not in row['removed'] and row['bytes_reclaimed'] > 0 for row in reaps)
    train(child, max_updates=1)
    assert current(child)['iteration'] == 2


def test_uncapped_continuation_preserves_source_and_warm_starts(tmp_path, monkeypatch):
    plan = tiny_plan(tmp_path)
    plan['optimizer']['iterations'] = 1
    source = make_run(tmp_path, 'source', plan)
    train(source)
    original = current(source)
    original_plan = (source / 'plan.json').read_bytes()
    assert original['stop_reason'] == 'iteration_limit'
    target = tmp_path / 'continuation'
    # A crash after plan publication must not make recovery start from zeros.
    with monkeypatch.context() as patch:
        patch.setattr(shared, 'publish', lambda *args: (_ for _ in ()).throw(OSError('publication interrupted')))
        with pytest.raises(OSError):shared.continue_run(source, target)
    shared.continue_run(source, target)
    seeded = current(target)
    assert seeded['iteration'] == 1 and seeded['weights'] == original['weights']
    assert seeded['history'] == original['history'] and not seeded['complete']
    assert read(target / 'plan.json')['optimizer']['iterations'] is None
    shared.continue_run(source, target)  # Idempotent.
    train(target, max_updates=1)
    assert current(target)['iteration'] == 2 and not current(target)['complete']
    assert current(target)['objective'] >= original['objective']
    assert current(source) == original and (source / 'plan.json').read_bytes() == original_plan
    with pytest.raises(ValueError, match='exceed source iteration'):
        shared.continue_run(source, tmp_path / 'bad', iterations=1)


def test_continuation_rejects_numerical_core_change(tmp_path):
    plan = tiny_plan(tmp_path)
    plan['optimizer']['iterations'] = 1
    source = make_run(tmp_path, 'source', plan)
    train(source)
    plan['software']['shared_reward.py'] = 'different-core'
    write(source / 'plan.json', plan)
    with pytest.raises(ValueError, match='Numerical core/storage changed'):
        shared.continue_run(source, tmp_path / 'new')


def test_equal_individuals_across_groups(tmp_path):
    plan = tiny_plan(tmp_path)
    weights = np.array([0.2, -0.3])
    plan['optimizer']['l2'] = 0
    singles = []
    for group in plan['groups']:
        subset = {**plan, 'groups': [group], 'trajectories': [
            row for row in plan['trajectories'] if row['group_id'] == group
        ]}
        singles.append(objective(subset, weights))
    expected_value = sum(factor * item[0] for factor, item in zip([0.25, 0.25, 0.5], singles))
    expected_gradient = sum(factor * item[1] for factor, item in zip([0.25, 0.25, 0.5], singles))
    value, gradient = objective(plan, weights)
    assert value == pytest.approx(expected_value)
    assert np.allclose(gradient, expected_gradient)
    plan['optimizer']['l2'] = 0.02
    value, gradient = objective(plan, weights)
    assert value == pytest.approx(expected_value - 0.01 * (weights @ weights))
    assert np.allclose(gradient, expected_gradient - 0.02 * weights)


def test_atomic_publication_failure_and_lock(tmp_path, monkeypatch):
    prior_state = dict(kind='shared_reward_iteration', weights=[1.0, 2.0])
    next_state = dict(kind='shared_reward_iteration', weights=[2.0, 3.0])
    publish(tmp_path, prior_state)
    prior = (tmp_path / 'current').resolve()

    def fail(*args):
        raise OSError('injected interruption before swap')

    with monkeypatch.context() as patch:
        patch.setattr(shared_storage.os, 'replace', fail)
        with pytest.raises(OSError, match='interruption'):
            publish(tmp_path, next_state)
    assert (tmp_path / 'current').resolve() == prior
    assert read(tmp_path / 'current/state.json') == prior_state
    assert np.array_equal(np.load(tmp_path / 'current/weights.npy'), prior_state['weights'])
    # The unactivated complete version can be reused safely on retry.
    publish(tmp_path, next_state)
    assert read(tmp_path / 'current/state.json') == next_state
    assert np.array_equal(np.load(tmp_path / 'current/weights.npy'), next_state['weights'])
    with locked(tmp_path):
        with pytest.raises(ValueError, match='writer'):
            with locked(tmp_path):
                pass


def checkpoint_with_maps(tmp_path, small_map_budget=False):
    from jaguar_irl.data.test_pantanal_bouts import fixture_csv
    from jaguar_irl.data.movement_processor_pantanal_bouts import BoutConfig, BoutProcessor
    from jaguar_irl.data.export_pantanal_bouts_irl import export_bout_collection
    from jaguar_irl.data.pantanal_spatial import SpatialConfig

    path, metadata, _ = fixture_csv(tmp_path)
    with path.open() as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    for row in rows:
        if row['individual.local.identifier (ID)'] == '2':
            row['location.long'] = str(float(row['location.long']) + 1)
    with path.open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    result = BoutProcessor(BoutConfig(
        csv_path=str(path), output_dir=str(tmp_path / 'selection'),
        individual_ids=(1, 2), gap_jitter_minutes=15,
        spatial=SpatialConfig(max_extent_side_km=1, growth_buffer_km=500)
        if small_map_budget else SpatialConfig(),
    )).run_pipeline(collar_metadata_path=metadata, render=False)
    checkpoint = Path(result['checkpoint_dir'])
    original = file_hash(checkpoint / 'checkpoint.json')
    collection = next(item for item in result['collections'] if item['season'] == 'winter')
    groups = collection['group_ids']
    assert groups
    specpath = tmp_path / 'maps.json'
    template(checkpoint, groups, specpath)
    spec = read(specpath)
    spec['features'] = [dict(name='habitat', units='fraction', definition='synthetic test',
                             offset=0, scale=1)]
    grids = read(checkpoint / 'grids.json')
    rng = np.random.default_rng(41)
    for group_id, group in spec['groups'].items():
        grid = grids[group['grid_key']]
        path = tmp_path / f'{group_id}.npy'
        np.save(path, rng.random((grid['rows'], grid['cols'])))
        group['files'] = {'habitat': path.name}
    write(specpath, spec)
    first = bind(checkpoint, specpath)
    assert bind(checkpoint, specpath) == first
    assert file_hash(checkpoint / 'checkpoint.json') == original
    export = export_bout_collection(checkpoint, 'WIN-C01', tmp_path / 'exports')
    return checkpoint, groups, specpath, first, export


def test_real_checkpoint_binding_export_training(tmp_path):
    checkpoint, groups, specpath, first, export = checkpoint_with_maps(tmp_path)
    assert len(groups) >= 2
    run = tmp_path / 'run'
    prepare(checkpoint, run, collection='WIN-C01', export=export, split='unassigned', iterations=2)
    assert prepare(checkpoint, run, collection='WIN-C01', split='unassigned', iterations=2) == run / 'plan.json'
    train(run)
    assert current(run)['iteration'] == 2
    assert current(run)['groups'] == sorted(groups)
    assert not (run / 'current/stages').exists()

    # Reordering group arguments does not create a different experiment.
    explicit = tmp_path / 'explicit'
    prepare(checkpoint, explicit, group_ids=groups, export=export, split='unassigned', iterations=2)
    prepare(checkpoint, explicit, group_ids=list(reversed(groups)), export=export,
            split='unassigned', iterations=2)

    # Omitted groups need no maps, and excluding one creates a distinct plan.
    omitted_map = tmp_path / f'{groups[1]}.npy'
    moved_map = omitted_map.with_suffix('.unused')
    omitted_map.rename(moved_map)
    subset_run = tmp_path / 'subset-run'
    try:
        prepare(checkpoint, subset_run, collection='WIN-C01', export=export,
                split='unassigned', exclude_groups=groups[1:])
    finally:
        moved_map.rename(omitted_map)
    subset_plan = read(subset_run / 'plan.json')
    assert subset_plan['groups'] == groups[:1]
    assert set(subset_plan['bindings']['groups']) == set(groups[:1])
    template_path = tmp_path / 'subset-template.json'
    template(checkpoint, None, template_path, collection='WIN-C01', exclude_groups=groups[1:])
    assert set(read(template_path)['groups']) == set(groups[:1])
    with pytest.raises(ValueError, match='outside the requested'):
        shared.selected_groups(checkpoint, None, 'WIN-C01', ['unknown'])
    with pytest.raises(ValueError, match='no training groups'):
        shared.selected_groups(checkpoint, None, 'WIN-C01', groups)

    # Wrong season must fail before altering the active binding.
    bad = read(specpath)
    bad['groups'][groups[0]]['season'] = 'summer'
    write(specpath, bad)
    with pytest.raises(ValueError, match='season'):
        bind(checkpoint, specpath)
    assert (checkpoint / 'covariates/current/state.json').resolve() == first


def test_transfer_fresh_and_checkpointed_run(tmp_path, monkeypatch):
    original = tmp_path / 'original'
    original.mkdir()
    for name in transfer.TRAINER_FILES:
        destination = original / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(transfer.CODE_ROOT / name, destination)

    def stage(source, destination):
        monkeypatch.setattr(transfer, 'CODE_ROOT', source)
        manifest = transfer.transfer_manifest(source / 'run', source)
        paths = manifest.read_text().splitlines()
        for name in paths:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, target, follow_symlinks=False)
        source.rename(source.with_suffix('.unavailable'))
        return paths

    checkpoint, _, _, binding, export = checkpoint_with_maps(original)
    run = original / 'run'
    options = dict(collection='WIN-C01', split='unassigned', iterations=2)
    prepare(checkpoint, run, export=export, **options)
    plan_bytes = (run / 'plan.json').read_bytes()
    moved = tmp_path / 'cluster'
    assert 'run/current' not in stage(original, moved)

    run = moved / 'run'
    prepare(moved / checkpoint.relative_to(original), run,
            export=moved / export.relative_to(original),
            binding_state=moved / binding.relative_to(original), **options)
    train(run, max_updates=1)
    assert current(run)['iteration'] == 1
    final = tmp_path / 'another-location'
    paths = stage(moved, final)
    assert 'run/current' in paths and (final / 'run/current').is_symlink()
    assert not any(name.endswith('.jsonl') for name in paths)
    train(final / 'run')
    assert current(final / 'run')['iteration'] == 2
    assert (final / 'run/plan.json').read_bytes() == plan_bytes


def test_explicit_map_budget_exception(tmp_path):
    checkpoint, groups, _, _, export = checkpoint_with_maps(tmp_path, small_map_budget=True)
    original_export = file_hash(export / 'export_manifest.json')
    with pytest.warns(UserWarning, match='Automatically accepting'):
        prepare(checkpoint, tmp_path / 'automatic', collection='WIN-C01', export=export,
                split='unassigned')
    automatic = read(tmp_path / 'automatic' / 'plan.json')
    assert automatic['map_budget_exceptions'] == sorted(groups)
    assert all(row['admission'] == 'map_budget_exception' for row in automatic['trajectories'])
    from jaguar_irl.data.pantanal_checkpoint import load_selection_checkpoint
    cp = load_selection_checkpoint(checkpoint)
    lookup = shared.group_lookup(cp)
    included = groups[0]
    excluded = [group for group in groups if group != included]
    run = tmp_path / 'exception'
    options = dict(collection='WIN-C01', export=export, split='unassigned', iterations=1,
                   exclude_groups=excluded, map_budget_exceptions=[included])
    prepare(checkpoint, run, **options)
    plan = read(run / 'plan.json')
    assert plan['groups'] == [included]
    assert plan['excluded_groups'] == sorted(excluded)
    assert set(plan['bindings']['groups']) == {included}
    assert all(row['admission'] == 'map_budget_exception' for row in plan['trajectories'])
    assert all(not row['export_optimizer_candidate'] for row in plan['trajectories'])
    assert prepare(checkpoint, run, **options) == run / 'plan.json'
    train(run)
    assert current(run)['map_budget_exceptions'] == [included]
    assert current(run)['excluded_groups'] == sorted(excluded)
    assert current(run)['map_budget_exception_trajectory_count'] == len(plan['trajectories'])
    assert file_hash(export / 'export_manifest.json') == original_export
    # The runtime guard is independent of the map-size exception.
    plan['optimizer']['max_state_cells'] = 1
    with pytest.raises(ValueError, match='memory budget'):
        objective(shared.resolve_plan_paths(plan, run), np.zeros(1))
    with pytest.raises(ValueError, match='must be included'):
        prepare(checkpoint, tmp_path / 'conflict', **{**options, 'map_budget_exceptions': ['unknown']})
    # A proximity exception must not be hidden by the export's generic label.
    lookup[included]['selection_metadata_json'] = '{"spatial_violation_codes":["mcp_proximity_limit"]}'
    with pytest.raises(ValueError, match='other spatial violations'):
        shared.validate_map_budget_exceptions(cp, groups, [included])


@pytest.mark.parametrize('changes', [
    {'optimizer_exclusion_reason': 'no_route_choice'},
    {'optimizer_exclusion_reason': 'unsupported_residence_evidence'},
    {'data_eligible': 'False'}, {'backend_support_status': 'unsupported'},
    {'route_choice_status': 'unique'}, {'grid_transition_count': '1'}, {'array_path': ''},
])
def test_map_exception_does_not_admit_other_invalid_routes(changes):
    row = dict(group_id='G324', optimizer_candidate='False',
               optimizer_exclusion_reason='selection_map_budget_exceeded',
               data_eligible='True', backend_support_status='supported',
               route_choice_status='not_screened', grid_transition_count='2', array_path='route.npy')
    assert shared.route_admission(row, []) is None
    assert shared.route_admission(row, ['G324']) == 'map_budget_exception'
    assert shared.route_admission({**row, **changes}, ['G324']) is None


def test_checkpoint_records_shared_reward_and_detects_weight_tampering(tmp_path):
    plan = tiny_plan(tmp_path)
    run = make_run(tmp_path, 'run', plan)
    train(run)
    state = current(run)
    assert state['biome'] == 'Pantanal' and state['season'] == 'winter'
    assert state['weighting'] == 'equal_individual_mean_trajectory'
    assert state['grid_keys'] == {group: 'grid_' + group for group in plan['groups']}
    assert state['feature_definitions'] == plan['bindings']['features']
    assert state['optimizer'] == plan['optimizer']
    assert state['individual_count'] == 2 and state['trajectory_count'] == 3
    np.save(run / 'current/weights.npy', [999.0, 999.0])
    with pytest.raises(ValueError, match='weights changed'):
        train(run)


def test_failed_partial_group_evaluation_resumes_identically(tmp_path, monkeypatch):
    plan = tiny_plan(tmp_path)
    full = make_run(tmp_path, 'full', plan)
    train(full)
    run = make_run(tmp_path, 'run', plan)
    train(run, max_updates=1)
    prior = (run / 'current').readlink()
    visited = []

    def fail_second_group(features, *args):
        visited.append(features.shape[1:])
        if len(visited) == 2:
            raise RuntimeError('simulated crash in second group')
        return statistics(features, *args)

    with monkeypatch.context() as patch:
        patch.setattr(shared, 'statistics', fail_second_group)
        with pytest.raises(RuntimeError, match='second group'):
            train(run)
    assert visited == [(3, 4), (4, 5)]
    assert (run / 'current').readlink() == prior
    assert current(run)['iteration'] == 1
    train(run)
    assert current(run) == current(full)


def test_failed_weights_write_preserves_checkpoint_and_can_resume(tmp_path, monkeypatch):
    plan = tiny_plan(tmp_path)
    full = make_run(tmp_path, 'full', plan)
    train(full)
    run = make_run(tmp_path, 'run', plan)
    train(run, max_updates=1)
    prior = (run / 'current').readlink()

    def fail(*args, **kwargs):
        raise OSError('simulated interrupted weights write')

    with monkeypatch.context() as patch:
        patch.setattr(shared_storage.np, 'save', fail)
        with pytest.raises(OSError, match='weights write'):
            train(run)
    assert (run / 'current').readlink() == prior
    assert current(run)['iteration'] == 1
    train(run)
    assert current(run) == current(full)


def test_rejects_legacy_stage_plans_without_touching_them(tmp_path):
    plan = tiny_plan(tmp_path)
    plan['schema'] = 'shared_static_reward/1'
    run = make_run(tmp_path, 'legacy', plan)
    before = file_hash(run / 'plan.json')
    with pytest.raises(ValueError, match='Cumulative-stage runs cannot resume'):
        train(run)
    assert file_hash(run / 'plan.json') == before
    assert not (run / 'current').exists()


def test_route_alternatives_affect_likelihood_but_unreachable_cells_do_not():
    features = np.zeros((1, 5, 5))
    route = np.array([[2, 2], [2, 3], [2, 2]])
    weights = np.ones(1)
    baseline = statistics(features, weights, route)
    # This cell is unobserved, but an alternative two-move return can visit it.
    features[0, 1, 2] = 2
    altered = statistics(features, weights, route)
    assert altered[0] < baseline[0]
    assert not np.allclose(altered[1], baseline[1])
    # This cell cannot be visited on any two-move start/goal bridge.
    features[0, 0, 0] = 100
    unreachable = statistics(features, weights, route)
    assert unreachable[0] == altered[0]
    np.testing.assert_array_equal(unreachable[1], altered[1])
    # Moving a boundary inward removes alternative paths even at zero reward.
    full = statistics(np.zeros((1, 3, 3)), weights,
                      np.array([[1, 1], [1, 2], [1, 1]]))[0]
    edge = statistics(np.zeros((1, 3, 2)), weights,
                      np.array([[1, 0], [1, 1], [1, 0]]))[0]
    assert edge > full
