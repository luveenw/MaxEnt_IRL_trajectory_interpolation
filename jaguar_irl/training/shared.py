"""Versioned covariate bindings and joint biome-season reward training.

Run: python -m jaguar_irl.training.shared --help
"""
from collections import Counter, defaultdict
import argparse
import gzip
import json
import math
import os
import re
import resource
import shutil
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import time
from datetime import datetime, timezone
import uuid

import numpy as np

from jaguar_irl.core.shared_reward import statistics
from jaguar_irl.data.pantanal_checkpoint import (
    digest, file_hash, load_selection_checkpoint, read_table, verify_inventory,
)
from .shared_storage import read, write, locked, publish, sync_dir

BINDING_SCHEMA = 'shared_static_reward/1'
SCHEMA = 'shared_static_reward/2'


class SplitLog:
    """Append whole records, compress closed segments, and optionally expire archives."""

    def __init__(self, path, limit, keep_archives=None, audit=None):
        self.path = path
        self.limit = limit
        self.keep_archives = keep_archives
        self.audit = audit

    def __enter__(self):
        for closed in self._segments(''):
            self._compress(closed)
        self._expire_archives()
        self.handle = self.path.open('ab')
        self.size = self.handle.tell()
        return self

    def _segments(self, suffix):
        pattern = (re.escape(self.path.name)
                   + r'\.\d{8}T\d{6}\.\d{6}Z\.[0-9a-f]{8}'
                   + re.escape(suffix))
        return sorted(path for path in self.path.parent.glob(f'{self.path.name}.*')
                      if re.fullmatch(pattern, path.name)
                      and path.is_file() and not path.is_symlink())

    def _compress(self, closed):
        original_bytes = closed.stat().st_size
        pending = closed.with_name(closed.name + '.gz.pending')
        archive = closed.with_name(closed.name + '.gz')
        try:
            # A prior invocation may have stopped before committing the archive.
            pending.unlink(missing_ok=True)
            with closed.open('rb') as source, pending.open('xb') as target:
                with gzip.GzipFile(filename='', mode='wb', fileobj=target, compresslevel=1) as compressed:
                    shutil.copyfileobj(source, compressed)
                target.flush()
                os.fsync(target.fileno())
            pending.rename(archive)
            sync_dir(self.path.parent)
            closed.unlink()
        except OSError as error:
            if self.audit:
                self.audit('compression_failed', segment=closed.name, error=str(error))
            raise
        if self.audit:
            compressed_bytes = archive.stat().st_size
            self.audit('log_compressed', stream=self.path.name, archive=archive.name,
                       original_bytes=original_bytes, compressed_bytes=compressed_bytes,
                       bytes_reclaimed=original_bytes - compressed_bytes)

    def _expire_archives(self):
        if self.keep_archives is None:
            return
        archives = self._segments('.gz')
        for archive in archives[:max(0, len(archives) - self.keep_archives)]:
            size = archive.stat().st_size
            archive.unlink()
            if self.audit:
                self.audit('log_archive_reaped', stream=self.path.name, archive=archive.name,
                           bytes_reclaimed=size)

    def write(self, line):
        record = (line + '\n').encode('utf-8')
        if self.size and self.size + len(record) > self.limit:
            self.handle.close()
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
            closed = self.path.with_name(f'{self.path.name}.{stamp}.{uuid.uuid4().hex[:8]}')
            self.path.rename(closed)
            self.handle = self.path.open('ab')
            self.size = 0
            if self.audit:
                self.audit('log_rotated', stream=self.path.name, segment=closed.name)
            self._compress(closed)
            self._expire_archives()
        self.handle.write(record)
        self.handle.flush()
        self.size += len(record)

    def __exit__(self, *exc):
        self.handle.close()


class TrainingProgress:
    """Non-authoritative runtime telemetry, separate from optimizer checkpoints."""

    def __init__(self, run, console_log=False, trace_routes=False, keep_log_archives=None):
        self.run = Path(run)
        self.started = time.monotonic()
        self.last_console = -math.inf
        self.invocation = uuid.uuid4().hex
        prior = read(self.run / 'progress.json') if (self.run / 'progress.json').exists() else {}
        self.prior_elapsed = prior.get('total_elapsed_s', 0.)
        self.context = {}
        self.console_log = console_log
        self.trace_routes = trace_routes
        self.keep_log_archives = keep_log_archives

    def __enter__(self):
        with ExitStack() as logs:
            self.housekeeping = logs.enter_context(
                SplitLog(self.run / 'housekeeping.jsonl', 1024**2, self.keep_log_archives)
            )
            self.storage_event('housekeeping_started', keep_log_archives=self.keep_log_archives)
            self.events = logs.enter_context(
                SplitLog(self.run / 'progress.jsonl', 64 * 1024**2,
                         self.keep_log_archives, self.storage_event)
            )
            self.console = None
            if self.console_log:
                self.console = logs.enter_context(
                    SplitLog(self.run / 'training.console.log', 10 * 1024**2,
                             self.keep_log_archives, self.storage_event)
                )
            self.emit('invocation_started', function='verify_inputs', force=True)
            self.logs = logs.pop_all()
        return self

    def storage_event(self, event, **fields):
        self.housekeeping.write(json.dumps(
            dict(event=event, utc=datetime.now(timezone.utc).isoformat(),
                 invocation=self.invocation, **fields), sort_keys=True,
        ))

    def emit(self, event, force=False, **fields):
        self.context.update(fields)
        elapsed = time.monotonic() - self.started
        item = dict(self.context, event=event, invocation=self.invocation,
                    pid=os.getpid(), utc=datetime.now(timezone.utc).isoformat(),
                    elapsed_s=elapsed, total_elapsed_s=self.prior_elapsed + elapsed,
                    peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
        item = {key: str(value) if isinstance(value, float) and not math.isfinite(value) else value
                for key, value in item.items()}
        record = json.dumps(item, sort_keys=True, allow_nan=False)
        if (self.trace_routes or event in {'failed', 'training_complete', 'training_paused'}
                or (event == 'checkpoint_published' and item['iteration'] > 0)):
            self.events.write(record)
        pending = self.run / '.progress.pending'
        pending.write_text(record + '\n')
        pending.replace(self.run / 'progress.json')
        if force or elapsed - self.last_console >= 5:
            line = f'[{elapsed:.1f}s] {event}: ' + ' '.join(
                f'{key}={item[key]}' for key in (
                    'iteration', 'iteration_limit', 'evaluation', 'trial', 'group',
                    'route_completed', 'route_total', 'function', 'objective',
                    'gradient_norm', 'learning_rate', 'iteration_budget_fraction',
                ) if key in item)
            if self.console is not None:
                self.console.write(line)
            print(line, flush=True)
            self.last_console = elapsed

    def __exit__(self, typ, error, traceback):
        with self.logs:
            if error is not None:
                self.emit('failed', function='train', error_type=typ.__name__, error=str(error), force=True)


def require_training_schema(value):
    if value.get('schema') != SCHEMA:
        raise ValueError(
            'Unsupported training schema. Cumulative-stage runs cannot resume as '
            'joint fits; prepare a new run directory, reusing the existing '
            'covariate bindings and trajectory export.'
        )


def software():
    from jaguar_irl.core import shared_reward
    from . import shared_storage
    paths = (__file__, shared_reward.__file__, shared_storage.__file__)
    return {Path(path).name: file_hash(path) for path in paths}


def binding_root(checkpoint):
    return Path(checkpoint).resolve() / 'covariates'


def group_lookup(checkpoint):
    return {group['group_id']: group for group in checkpoint['groups'].values()}


def selected_groups(checkpoint, group_ids, collection, exclude_groups=None):
    """Canonical order keeps argument order from changing numerical summation."""
    group_ids = list(group_ids or [])
    if bool(collection) == bool(group_ids):
        raise ValueError('Choose either --collection or one or more --group values')
    if collection:
        matches = [
            row for row in read_table(Path(checkpoint) / 'collections.csv')
            if row['collection_id'] == collection
        ]
        if len(matches) != 1:
            raise ValueError('Unknown collection')
        group_ids = json.loads(matches[0]['group_ids_json'])
    if not group_ids or len(set(group_ids)) != len(group_ids):
        raise ValueError('Require nonempty, unique groups')
    excluded = set(exclude_groups or [])
    unknown = excluded - set(group_ids)
    if unknown:
        raise ValueError(f'Excluded groups are outside the requested selection: {sorted(unknown)}')
    selected = sorted(set(group_ids) - excluded)
    if not selected:
        raise ValueError('Group exclusions leave no training groups')
    return selected


def feature_array(entry):
    array = np.load(entry['path'], mmap_mode='r', allow_pickle=False)
    if entry.get('band') is not None:
        if array.ndim != 3 or not 0 <= entry['band'] < array.shape[0]:
            raise ValueError('Band requires a valid zero-based index in a 3-D static stack')
        array = array[entry['band']]
    if (array.ndim != 2 or not np.issubdtype(array.dtype, np.number)
            or np.iscomplexobj(array) or not np.isfinite(array).all()):
        raise ValueError(
            'Each covariate must be a finite numeric 2-D array '
            '(or indexed static stack band)'
        )
    return array


def bind(checkpoint, manifest, binding_dir=None):
    """Add/replace group bindings; original checkpoint inventory stays unchanged."""
    checkpoint, manifest = Path(checkpoint).resolve(), Path(manifest).resolve()
    cp = load_selection_checkpoint(checkpoint)
    groups = group_lookup(cp)
    spec = read(manifest)
    if spec.get('biome') != 'Pantanal':
        raise ValueError('This checkpoint adapter currently supports biome Pantanal')
    features = spec['features']
    names = [feature['name'] for feature in features]
    if (not names or len(set(names)) != len(names)
            or any(not isinstance(name, str) or not name for name in names)):
        raise ValueError('Feature names must be nonempty and unique')
    for feature in features:
        if (not feature.get('units') or not feature.get('definition')
                or 'REPLACE' in (feature['units'], feature['definition'])):
            raise ValueError('Every feature needs units and definition')
        feature.setdefault('offset', 0.0)
        feature.setdefault('scale', 1.0)
        if (not math.isfinite(feature['offset']) or not math.isfinite(feature['scale'])
                or feature['scale'] <= 0):
            raise ValueError('Require finite shared offset and positive scale')
    if not spec.get('groups'):
        raise ValueError('No group bindings supplied')

    root = Path(binding_dir).resolve() if binding_dir else binding_root(checkpoint)

    def relative_raster(path):
        # state.json lives one directory below versions, at its own content hash.
        return str(Path('..') / os.path.relpath(path, root / 'versions'))

    bound = {}
    for group_id, item in spec['groups'].items():
        if group_id not in groups:
            raise ValueError(f'Unknown group: {group_id}')
        group = groups[group_id]
        grid = cp['grids'][group['grid_key']]
        # The grid ID is a spatial alignment declaration: NPY cannot prove CRS.
        if item.get('grid_key') != group['grid_key']:
            raise ValueError(f'{group_id}: grid_key does not match checkpoint')
        season = json.loads(group['selection_metadata_json'])['season']
        if item.get('season') != season:
            raise ValueError(f'{group_id}: season does not match checkpoint')
        if item.get('temporal_scope') != 'static_season_across_years':
            raise ValueError('Declare static_season_across_years applicability')
        if set(item['files']) != set(names):
            raise ValueError(f'{group_id}: feature names do not match shared definition')
        files = {}
        for name, value in item['files'].items():
            entry = dict(path=value) if isinstance(value, str) else dict(value)
            path = Path(entry['path'])
            entry['path'] = str((path if path.is_absolute() else manifest.parent / path).resolve())
            if 'band' in entry and type(entry['band']) is not int:
                raise ValueError('band must be an integer')
            array = feature_array(entry)
            if array.shape != (grid['rows'], grid['cols']):
                raise ValueError(f'{group_id}/{name}: array shape does not match grid')
            entry.update(sha256=file_hash(entry['path']), shape=list(array.shape))
            entry['path'] = relative_raster(entry['path'])
            files[name] = entry
        bound[group_id] = dict(
            grid_key=group['grid_key'], grid=grid, season=season,
            temporal_scope=item['temporal_scope'], files=files,
        )

    with locked(root):
        old_path = (root / 'current/state.json').resolve()
        old = read(old_path) if old_path.exists() else None
        checkpoint_hash = file_hash(checkpoint / 'checkpoint.json')
        if old and (old['checkpoint_sha256'] != checkpoint_hash or old['features'] != features):
            raise ValueError(
                'Existing binding has different checkpoint/features/scaling; '
                'use a separate checkpoint copy for another feature specification'
            )
        if old:
            for group in old['groups'].values():
                for entry in group['files'].values():
                    entry['path'] = relative_raster((old_path.parent / entry['path']).resolve())
        state = dict(
            schema=BINDING_SCHEMA, kind='covariates', biome=spec['biome'],
            checkpoint_sha256=checkpoint_hash, features=features,
            groups={**(old['groups'] if old else {}), **bound},
        )
        key = publish(root, state)
    return root / 'versions' / key / 'state.json'


def template(checkpoint, group_ids, destination, collection=None, exclude_groups=None):
    cp = load_selection_checkpoint(checkpoint)
    groups = group_lookup(cp)
    group_ids = selected_groups(checkpoint, group_ids, collection, exclude_groups)
    names = ['roughness', 'human_population', 'grassland', 'tree_cover',
             'flooded_habitat', 'shrubland']
    spec = dict(
        biome='Pantanal',
        features=[dict(name=name, units='REPLACE', definition='REPLACE', offset=0, scale=1)
                  for name in names],
        groups={},
    )
    for group_id in group_ids:
        group = groups[group_id]
        spec['groups'][group_id] = dict(
            grid_key=group['grid_key'],
            season=json.loads(group['selection_metadata_json'])['season'],
            temporal_scope='static_season_across_years',
            files={name: f'features/{group_id}/{name}.npy' for name in names},
        )
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    write(destination, spec)
    return destination


def route_admission(row, map_budget_exceptions):
    """An explicit map exception waives only the selection map-size budget."""
    if row['optimizer_candidate'] == 'True':
        return 'optimizer_candidate'
    if (row['group_id'] in map_budget_exceptions
            and row['optimizer_exclusion_reason'] == 'selection_map_budget_exceeded'
            and row['data_eligible'] == 'True'
            and row['backend_support_status'] == 'supported'
            and row['route_choice_status'] != 'unique'
            and int(row['grid_transition_count'] or 0) >= 2
            and row['array_path']):
        return 'map_budget_exception'
    return None


def validate_map_budget_exceptions(checkpoint, groups, exceptions):
    """Export's generic map-budget reason can also hide a proximity violation."""
    if not set(exceptions) <= set(groups):
        raise ValueError('Map-budget exception groups must be included in the training selection')
    lookup = group_lookup(checkpoint)
    for group in exceptions:
        codes = set(json.loads(lookup[group]['selection_metadata_json'])['spatial_violation_codes'])
        if codes - {'map_side_limit', 'map_area_limit'}:
            raise ValueError(f'{group}: map-budget exception cannot waive other spatial violations')


def resolve_map_budget_exceptions(checkpoint, groups, explicit=()):
    """Admit and report size-only exceptions; other eligibility gates still apply."""
    import warnings
    lookup = group_lookup(checkpoint)
    automatic = []
    for group in groups:
        codes = set(json.loads(lookup[group]['selection_metadata_json'])['spatial_violation_codes'])
        if codes and codes <= {'map_side_limit', 'map_area_limit'}:
            automatic.append(group)
    exceptions = sorted(set(explicit) | set(automatic))
    validate_map_budget_exceptions(checkpoint, groups, exceptions)
    if automatic:
        warnings.warn('Automatically accepting map-size exceptions: ' + ', '.join(sorted(automatic)),
                      UserWarning, stacklevel=2)
    return exceptions


def pin_trajectories(export, group_ids, split, bindings, map_budget_exceptions=()):
    """Select eligible routes and reject duplicated source evidence across maps."""
    rows = [
        row for row in read_table(export / 'data/trajectory_manifest.csv')
        if row['group_id'] in group_ids and row['variant'] == 'two_hour'
        and row['collection'] == 'independent' and row['split'] == split
    ]
    exclusions = Counter(
        row['optimizer_exclusion_reason'] for row in rows
        if route_admission(row, map_budget_exceptions) is None
    )
    rows = [row for row in rows if route_admission(row, map_budget_exceptions) is not None]
    if not rows:
        raise ValueError(
            f'No optimizer candidates for split {split}; '
            'exploratory unassigned data require --split unassigned'
        )

    trajectory_ids = {row['trajectory_id'] for row in rows}
    events_by_trajectory = defaultdict(set)
    for row in read_table(export / 'data/point_links.csv'):
        if row['trajectory_id'] in trajectory_ids:
            events_by_trajectory[row['trajectory_id']].add(row['source_event_key'])

    seen = defaultdict(set)
    pinned = []
    for row in sorted(rows, key=lambda row: (row['group_id'], row['trajectory_id'])):
        individual = row['individual_id']
        events = events_by_trajectory[row['trajectory_id']]
        if not events or seen[individual] & events:
            raise ValueError(
                'Repeated or missing source evidence; select a canonical collection '
                'and check the export point links'
            )
        seen[individual].update(events)
        if row['grid_key'] != bindings['groups'][row['group_id']]['grid_key']:
            raise ValueError('Trajectory grid differs from bound map grid')
        path = export / row['array_path']
        array = np.load(path, allow_pickle=False)
        if not np.array_equal(array[:, 2], np.arange(len(array))):
            raise ValueError('Invalid route move clock')
        pinned.append(dict(
            group_id=row['group_id'], individual_id=individual,
            trajectory_id=row['trajectory_id'], path=str(path), sha256=file_hash(path),
            admission=route_admission(row, map_budget_exceptions),
            export_optimizer_candidate=row['optimizer_candidate'] == 'True',
            export_optimizer_exclusion_reason=row['optimizer_exclusion_reason'],
        ))
    return pinned, dict(exclusions)


def prepare(checkpoint, run, group_ids=None, collection=None, export=None, split='train',
            iterations=None, learning_rate=0.1, l2=0.01, tolerance=1e-6,
            max_state_cells=10_000_000, exclude_groups=None, map_budget_exceptions=None,
            binding_state=None):
    """Pin all inputs for one joint fit. Identical preparation is a no-op."""
    from jaguar_irl.data.export_pantanal_bouts_irl import export_bout_collection, POLICY, JITTER_POLICY
    from jaguar_irl.data.export_pantanal_irl import export_checkpoint, validate_export
    from jaguar_irl.data.pantanal_irl_temporal import ExportConfig

    checkpoint, run = Path(checkpoint).resolve(), Path(run).resolve()
    if ((iterations is not None and iterations < 1) or max_state_cells < 1
            or not all(math.isfinite(value) for value in (learning_rate, l2, tolerance))
            or learning_rate <= 0 or l2 < 0 or tolerance <= 0):
        raise ValueError('Invalid optimizer configuration')
    if split not in ('train', 'unassigned'):
        raise ValueError('Training split must be train or explicitly unassigned')
    cp = load_selection_checkpoint(checkpoint)
    if cp['manifest']['selection_policy'] not in (POLICY, JITTER_POLICY):
        raise ValueError('Require a registered seasonal bout checkpoint')
    excluded = sorted(set(exclude_groups or []))
    group_ids = selected_groups(checkpoint, group_ids, collection, excluded)
    exceptions = resolve_map_budget_exceptions(cp, group_ids, map_budget_exceptions or ())
    binding_path = (Path(binding_state) if binding_state else binding_root(checkpoint) / 'current/state.json').resolve()
    bindings = read(binding_path)
    if bindings.get('schema') != BINDING_SCHEMA or bindings.get('kind') != 'covariates':
        raise ValueError('Require a named covariate binding state')
    if bindings['checkpoint_sha256'] != file_hash(checkpoint / 'checkpoint.json'):
        raise ValueError('Covariates belong to a different checkpoint')
    if not set(group_ids) <= bindings['groups'].keys():
        raise ValueError('Bind all requested groups before preparing training')
    if len({bindings['groups'][group]['season'] for group in group_ids}) != 1:
        raise ValueError('A shared run must contain exactly one season')
    for group_id in group_ids:
        for entry in bindings['groups'][group_id]['files'].values():
            entry['path'] = str((binding_path.parent / entry['path']).resolve())

    with locked(run):
        existing = read(run / 'plan.json') if (run / 'plan.json').exists() else None
        if existing:
            require_training_schema(existing)
        if export is None:
            if existing:
                export = run / existing['export']
            elif collection:
                export = export_bout_collection(checkpoint, collection, run / 'exports')
            else:
                cap = 4.25 if cp['manifest']['selection_policy'] == JITTER_POLICY else 4.0
                export = export_checkpoint(
                    checkpoint, run / 'exports', group_keys=group_ids,
                    config=ExportConfig(
                        min_source_segment_points=3, min_comparison_segment_points=3,
                        source_gap_hours=cap, max_comparison_gap_hours=cap,
                        max_affected_fraction=1,
                    ),
                )
        export = Path(export).resolve()
        export_manifest = validate_export(export)
        if export_manifest['checkpoint_sha256'] != file_hash(checkpoint / 'checkpoint.json'):
            raise ValueError('Export belongs to a different checkpoint')
        if collection and export_manifest.get('collection_id') != collection:
            raise ValueError('Export belongs to a different collection')
        pinned, exclusions = pin_trajectories(export, group_ids, split, bindings, exceptions)
        plan = dict(
            schema=SCHEMA,
            checkpoint=str(checkpoint), checkpoint_sha256=file_hash(checkpoint / 'checkpoint.json'),
            export=str(export), export_sha256=file_hash(export / 'export_manifest.json'),
            binding_path=str(binding_path), binding_sha256=file_hash(binding_path),
            bindings={**bindings, 'groups': {group: bindings['groups'][group] for group in group_ids}},
            groups=group_ids, collection=collection, split=split, trajectories=pinned,
            training_active_groups=sorted({row['group_id'] for row in pinned}),
            training_empty_groups=sorted(set(group_ids) - {row['group_id'] for row in pinned}),
            excluded_groups=excluded, map_budget_exceptions=exceptions,
            exclusions=exclusions, weighting='equal_individual_mean_trajectory',
            optimizer=dict(iterations=iterations, learning_rate=learning_rate, l2=l2,
                           tolerance=tolerance, max_state_cells=max_state_cells),
            software=software(),
        )
        verify_inputs(plan)
        plan = map_plan_paths(plan, lambda path: os.path.relpath(path, run))
        if existing:
            if existing != plan:
                raise ValueError('Run plan differs; choose a new run directory')
        else:
            # A single-file plan needs only a file replacement, not a generation.
            write(run / '.plan.pending', plan)
            (run / '.plan.pending').replace(run / 'plan.json')
            sync_dir(run)
        return run / 'plan.json'


def verify_inputs(plan, check_software=True):
    require_training_schema(plan)
    if check_software and plan['software'] != software():
        raise ValueError('Training software changed; prepare a new run')
    manifests = [
        (Path(plan['checkpoint']) / 'checkpoint.json', plan['checkpoint_sha256']),
        (Path(plan['export']) / 'export_manifest.json', plan['export_sha256']),
        (plan['binding_path'], plan['binding_sha256']),
    ]
    if plan.get('continuation'):
        parent = plan['continuation']
        manifests += [
            (Path(parent['source_run']) / 'plan.json', parent['source_plan_sha256']),
            (Path(parent['source_checkpoint']) / 'state.json', parent['source_state_sha256']),
            (Path(parent['source_checkpoint']) / 'weights.npy', parent['source_weights_sha256']),
        ]
    for path, sha in manifests:
        if file_hash(path) != sha:
            raise ValueError(f'Pinned input changed: {path}')
    for root, name in [(plan['checkpoint'], 'checkpoint.json'),
                       (plan['export'], 'export_manifest.json')]:
        verify_inventory(root, read(Path(root) / name))
    entries = [entry for group in plan['bindings']['groups'].values()
               for entry in group['files'].values()]
    checked = set()
    for entry in entries + plan['trajectories']:
        identity = (entry['path'], entry['sha256'])
        if identity not in checked:
            if file_hash(entry['path']) != entry['sha256']:
                raise ValueError(f'Pinned array changed: {entry["path"]}')
            checked.add(identity)


def objective(plan, weights, progress=None):
    """Evaluate the joint likelihood and gradient, loading one extent at a time.

    Each individual's weight is divided across all of its retained trajectories,
    including trajectories in other groups. Regularization is applied once.
    """
    rows_by_group = defaultdict(list)
    counts = Counter(row['individual_id'] for row in plan['trajectories'])
    for row in plan['trajectories']:
        rows_by_group[row['group_id']].append(row)

    value = 0.0
    gradient = np.zeros(len(weights))
    evaluated = 0
    if progress:
        progress.emit('evaluation_started', function='objective', route_completed=0,
                      route_total=len(plan['trajectories']))
    for group_id in plan['groups']:
        if not rows_by_group[group_id]:
            continue
        entry = plan['bindings']['groups'][group_id]
        if progress:
            progress.emit('group_loading', function='feature_array', group=group_id)
        features = np.stack([
            (feature_array(entry['files'][feature['name']]).astype(float)
             - feature['offset']) / feature['scale']
            for feature in plan['bindings']['features']
        ])
        for row in rows_by_group[group_id]:
            route = np.load(row['path'], allow_pickle=False)[:, :2]
            if progress:
                progress.emit('route_started', function='statistics',
                              individual_id=row['individual_id'], trajectory_id=row.get('trajectory_id', row['path']),
                              route_states=len(route), route_completed=evaluated)
            try:
                route_value, route_gradient = statistics(
                    features, weights, route, plan['optimizer']['max_state_cells']
                )
            except ValueError as error:
                raise ValueError(f'{group_id}, {row["path"]}: {error}') from error
            factor = 1 / (len(counts) * counts[row['individual_id']])
            value += factor * route_value
            gradient += factor * route_gradient
            evaluated += 1
            if progress:
                progress.emit('route_completed', function='objective', route_completed=evaluated,
                              evaluation_fraction=evaluated / len(plan['trajectories']))
        # Release this stack before building the next group's stack.
        del features

    l2 = plan['optimizer']['l2']
    if progress:
        progress.emit('evaluation_finished', function='objective',
                      objective=float(value - 0.5 * l2 * (weights @ weights)),
                      gradient_norm=float(np.linalg.norm(gradient - l2 * weights)))
    return float(value - 0.5 * l2 * (weights @ weights)), gradient - l2 * weights


def load_generation(run, key):
    directory = Path(run) / 'versions' / key
    state = read(directory / 'state.json')
    require_training_schema(state)
    if state.get('kind') != 'shared_reward_iteration' or digest(state) != key:
        raise ValueError('Training checkpoint content changed')
    weights = np.load(directory / 'weights.npy', allow_pickle=False)
    if not np.array_equal(weights, state['weights']):
        raise ValueError('Checkpoint weights changed')
    return state


def iteration_state(plan, weights, value, gradient, history):
    """Describe one fully evaluated parameter vector for the entire experiment."""
    iteration = history[-1]['iteration']
    gradient_norm = float(np.linalg.norm(gradient))
    converged = gradient_norm <= plan['optimizer']['tolerance']
    limit = plan['optimizer']['iterations']
    complete = converged or (limit is not None and iteration >= limit)
    return dict(
        schema=SCHEMA,
        kind='shared_reward_iteration',
        plan_key=digest(plan),
        biome=plan['bindings']['biome'],
        season=plan['bindings']['groups'][plan['groups'][0]]['season'],
        weighting=plan['weighting'],
        feature_definitions=plan['bindings']['features'],
        feature_names=[feature['name'] for feature in plan['bindings']['features']],
        optimizer=plan['optimizer'],
        grid_keys={
            group: plan['bindings']['groups'][group]['grid_key']
            for group in plan['groups']
        },
        groups=plan['groups'],
        excluded_groups=plan.get('excluded_groups', []),
        map_budget_exceptions=plan.get('map_budget_exceptions', []),
        map_budget_exception_trajectory_count=sum(
            row.get('admission') == 'map_budget_exception' for row in plan['trajectories']
        ),
        individual_count=len({row['individual_id'] for row in plan['trajectories']}),
        trajectory_count=len(plan['trajectories']),
        iteration=iteration,
        weights=weights.tolist(),
        objective=value,
        gradient=gradient.tolist(),
        gradient_norm=gradient_norm,
        history=history,
        complete=complete,
        stop_reason=(
            'gradient_tolerance' if converged
            else 'iteration_limit' if complete
            else 'in_progress'
        ),
    )


def pin_generation(run, key):
    """Protect a generation under the source run's writer lock."""
    directory = run / 'checkpoint-pins'
    directory.mkdir(exist_ok=True)
    (directory / key).touch(exist_ok=True)
    sync_dir(directory)
    sync_dir(run)


def checkpoint_pins(run):
    """Read explicit pins and recognize older sibling continuation plans."""
    directory = run / 'checkpoint-pins'
    pins = {entry.name for entry in directory.iterdir()} if directory.exists() else set()
    for path in run.parent.glob('*/plan.json'):
        parent = read(path).get('continuation')
        if parent and (path.parent / parent['source_run']).resolve() == run:
            pins.add(Path(parent['source_checkpoint']).name)
    return pins


def prune_checkpoints(run, complete, pins, audit):
    """Bound storage after publication while holding the run's writer lock."""
    versions = run / 'versions'
    current = (run / 'current').resolve(strict=True)
    keep = {current.name} | pins
    candidates = sorted(
        (path for path in versions.iterdir()
         if re.fullmatch(r'[0-9a-f]{64}', path.name)
         and path.is_dir() and not path.is_symlink()
         and (path / 'state.json').is_file() and (path / 'weights.npy').is_file()),
        key=lambda path: ((path / 'state.json').stat().st_mtime_ns, path.name),
        reverse=True,
    )
    if not complete:
        # Pins may extend retention. Always count current in the rolling five.
        keep.update([path.name for path in candidates if path != current][:4])
    removed = []
    reclaimed = 0
    for path in candidates:
        if path.name not in keep:
            size = (path / 'state.json').stat().st_size + (path / 'weights.npy').stat().st_size
            shutil.rmtree(path)
            removed.append(path.name)
            reclaimed += size
    if removed:
        sync_dir(versions)
        audit('checkpoints_reaped', current=current.name, complete=complete,
              removed=removed, bytes_reclaimed=reclaimed)


def map_plan_paths(plan, transform):
    """Apply a path transform to executable references, leaving provenance intact."""
    mapped = deepcopy(plan)
    for key in ('checkpoint', 'export', 'binding_path'):
        mapped[key] = transform(mapped[key])
    for group in mapped['bindings']['groups'].values():
        for entry in group['files'].values():
            entry['path'] = transform(entry['path'])
    for row in mapped['trajectories']:
        row['path'] = transform(row['path'])
    if mapped.get('continuation'):
        for key in ('source_run', 'source_checkpoint'):
            mapped['continuation'][key] = transform(mapped['continuation'][key])
    return mapped


def resolve_plan_paths(plan, run):
    """Resolve a stored plan for execution without changing its checkpoint identity."""
    return map_plan_paths(plan, lambda path: str((Path(run) / path).resolve()))


def relocate_plan_paths(plan, old_root, new_root):
    """Translate absolute references from a historical plan."""
    old_root = Path(old_root)
    if not old_root.is_absolute():
        raise ValueError('The original repository root must be an absolute path')
    new_root = Path(new_root).resolve()

    def moved(value):
        path = Path(value)
        if not path.is_relative_to(old_root):
            raise ValueError(f'Input path is outside the original repository root: {path}')
        return str(new_root / path.relative_to(old_root))

    return map_plan_paths(plan, moved)


def continue_run(source_run, run, iterations=None, relocate_from=None, relocate_to=None):
    """Warm-start a new immutable plan; never rewrite the source run or cap.

    No iterations argument means no accepted-update cap. The numerical core and
    storage hashes must match; a wrapper-only migration reevaluates and checks
    the saved objective/gradient before publishing the new initial checkpoint.
    """
    source_run, run = Path(source_run).resolve(), Path(run).resolve()
    if source_run == run:
        raise ValueError('Continuation requires a new run directory')
    if (relocate_from is None) != (relocate_to is None):
        raise ValueError('Use --relocate-from and --relocate-to together')
    with locked(source_run), locked(run):
        original = read(source_run / 'plan.json')
        inputs = resolve_plan_paths(original, source_run) if relocate_from is None else relocate_plan_paths(
            original, relocate_from, relocate_to,
        )
        verify_inputs(inputs, check_software=False)
        for name in ('shared_reward.py', 'shared_storage.py'):
            if original['software'].get(name) != software()[name]:
                raise ValueError('Numerical core/storage changed; continuation requires explicit migration review')
        source = (source_run / 'current').resolve(strict=True)
        saved = load_generation(source_run, source.name)
        if saved['plan_key'] != digest(original):
            raise ValueError('Source checkpoint does not match source plan')
        if iterations is not None and iterations <= saved['iteration']:
            raise ValueError('New total iteration limit must exceed source iteration')
        runtime_plan = dict(inputs, optimizer={**original['optimizer'], 'iterations': iterations},
                    software=software(), continuation=dict(
                        source_run=str(source_run), source_plan_sha256=file_hash(source_run / 'plan.json'),
                        source_checkpoint=str(source), source_state_sha256=file_hash(source / 'state.json'),
                        source_weights_sha256=file_hash(source / 'weights.npy'),
                        source_iteration=saved['iteration'],
                        policy='Same inputs/objective/scaling; wrapper migration verified by objective/gradient reevaluation'))
        plan = map_plan_paths(runtime_plan, lambda path: os.path.relpath(path, run))
        existing = run / 'plan.json'
        if existing.exists():
            if read(existing) != plan:
                raise ValueError('Continuation plan differs; use a new run directory')
            verify_inputs(runtime_plan)
            if (run / 'current').exists():
                active = load_generation(run, (run / 'current').resolve().name)
                if active['plan_key'] != digest(plan):
                    raise ValueError('Continuation checkpoint does not match plan')
                pin_generation(source_run, source.name)
                return existing
        weights = np.asarray(saved['weights'], dtype=float)
        value, gradient = objective(runtime_plan, weights)
        if not (np.isclose(value, saved['objective'], rtol=1e-12, atol=1e-12)
                and np.allclose(gradient, saved['gradient'], rtol=1e-10, atol=1e-12)):
            raise ValueError('Continuation objective/gradient differ from source checkpoint')
        verify_inputs(runtime_plan)
        pin_generation(source_run, source.name)
        write(run / '.plan.pending', plan)
        (run / '.plan.pending').replace(existing)
        sync_dir(run)
        publish(run, iteration_state(plan, weights, value, gradient, saved['history']))
        return existing


def ascent_step(plan, weights, value, gradient, progress=None):
    """Backtrack on the full joint objective; partial group totals are never used."""
    rate = plan['optimizer']['learning_rate']
    slope = float(gradient @ gradient)
    for trial in range(1, 41):
        candidate = weights + rate * gradient
        if progress:
            progress.emit('line_search_trial', function='ascent_step', trial=trial,
                          learning_rate=rate, force=True)
        new_value, new_gradient = objective(plan, candidate, progress)
        if (np.isfinite(new_value) and np.isfinite(new_gradient).all()
                and new_value >= value + 1e-4 * rate * slope):
            return candidate, new_value, new_gradient, rate
        if progress:
            progress.emit('line_search_rejected', function='ascent_step', trial=trial, force=True)
        rate *= 0.5
    raise ValueError('Line search failed; last completed iteration is safely checkpointed')


def train(run, max_updates=None, console_log=False, trace_routes=False, keep_log_archives=None):
    """Resume one joint fit from its last complete optimizer iteration.

    Every accepted update includes every planned group. A failed evaluation or
    publication leaves the previous active checkpoint available. max_updates
    limits new updates in this invocation, not the number of groups processed.
    """
    if max_updates is not None and max_updates < 0:
        raise ValueError('max-updates must be nonnegative')
    if keep_log_archives is not None and keep_log_archives < 1:
        raise ValueError('keep-log-archives must be positive')
    run = Path(run).resolve()
    with locked(run), TrainingProgress(run, console_log, trace_routes, keep_log_archives) as progress:
        stored_plan = read(run / 'plan.json')
        plan = resolve_plan_paths(stored_plan, run)
        verify_inputs(plan)
        pins = checkpoint_pins(run)
        progress.emit('inputs_verified', function='train', iteration_limit=plan['optimizer']['iterations'],
                      route_total=len(plan['trajectories']), force=True)
        if (run / 'current').is_symlink() or (run / 'current').exists():
            # Resolve once so state and weights come from the same generation.
            saved = load_generation(run, (run / 'current').resolve().name)
            if saved['plan_key'] != digest(stored_plan):
                raise ValueError('Training checkpoint does not match plan')
            weights = np.asarray(saved['weights'], dtype=float)
            value = saved['objective']
            gradient = np.asarray(saved['gradient'], dtype=float)
            history = saved['history']
            progress.emit('checkpoint_resumed', function='load_generation', iteration=saved['iteration'], force=True)
        else:
            if stored_plan.get('continuation'):
                raise ValueError('Missing continuation checkpoint; finish the continuation before training')
            weights = np.zeros(len(plan['bindings']['features']))
            progress.emit('initialization', function='objective', iteration=0, evaluation=0, force=True)
            value, gradient = objective(plan, weights, progress)
            history = [dict(iteration=0, objective=value)]
            saved = iteration_state(stored_plan, weights, value, gradient, history)
            publish(run, saved)
            progress.emit('checkpoint_published', function='publish', iteration=0,
                          checkpoint=str((run / 'current').resolve()), force=True)

        prune_checkpoints(run, saved['complete'], pins, progress.storage_event)
        updates = 0
        while not saved['complete']:
            if max_updates is not None and updates >= max_updates:
                break
            progress.emit('iteration_started', function='ascent_step', iteration=saved['iteration'] + 1,
                          evaluation=saved['iteration'] + 1, force=True)
            weights, value, gradient, rate = ascent_step(plan, weights, value, gradient, progress)
            history = history + [dict(
                iteration=saved['iteration'] + 1,
                objective=value,
                learning_rate=rate,
            )]
            saved = iteration_state(stored_plan, weights, value, gradient, history)
            publish(run, saved)
            updates += 1
            progress.emit('checkpoint_published', function='publish', iteration=saved['iteration'],
                          objective=value, gradient_norm=saved['gradient_norm'], learning_rate=rate,
                          iteration_budget_fraction=(saved['iteration'] / plan['optimizer']['iterations']
                                                     if plan['optimizer']['iterations'] is not None else None),
                          checkpoint=str((run / 'current').resolve()), force=True)
            prune_checkpoints(run, saved['complete'], pins, progress.storage_event)
        progress.emit('training_complete' if saved['complete'] else 'training_paused', function='train',
                      iteration=saved['iteration'], objective=value, gradient_norm=saved['gradient_norm'],
                      stop_reason=saved['stop_reason'], force=True)
        return run / 'current'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)

    templates = sub.add_parser('template', help='Create a covariate binding manifest')
    templates.add_argument('--checkpoint', required=True)
    template_pick = templates.add_mutually_exclusive_group(required=True)
    template_pick.add_argument('--group', action='append')
    template_pick.add_argument('--collection')
    templates.add_argument('--output', required=True)
    templates.add_argument('--exclude-group', dest='exclude_groups', action='append',
                           help='Omit a group from the requested collection or group list; repeatable')

    binding = sub.add_parser('bind', help='Attach covariate maps to a selection checkpoint')
    binding.add_argument('--checkpoint', required=True)
    binding.add_argument('--manifest', required=True)
    binding.add_argument('--binding-dir', help='Separate versioned binding profile root; default checkpoint/covariates')

    preparation = sub.add_parser('prepare', help='Pin all groups for one joint fit')
    preparation.add_argument('--checkpoint', required=True)
    preparation.add_argument('--run', required=True)
    pick = preparation.add_mutually_exclusive_group(required=True)
    pick.add_argument('--group', action='append')
    pick.add_argument('--collection')
    preparation.add_argument('--exclude-group', dest='exclude_groups', action='append',
                             help='Omit a group before checking maps and routes; repeatable')
    preparation.add_argument('--allow-map-budget-exception', dest='map_budget_exceptions',
                             action='append', metavar='GROUP',
                             help='Admit this group despite its selection map-size limit; repeatable. '
                                  'Other route checks and the runtime memory limit still apply.')
    preparation.add_argument('--export')
    preparation.add_argument('--binding-state', help='Explicit binding state/version; default checkpoint current binding')
    preparation.add_argument('--split', choices=['train', 'unassigned'], default='train')
    preparation.add_argument('--iterations', type=int,
                             help='Optional maximum total joint optimizer updates; default no cap, stop at gradient tolerance')
    preparation.add_argument('--learning-rate', type=float, default=0.1)
    preparation.add_argument('--l2', type=float, default=0.01)
    preparation.add_argument('--tolerance', type=float, default=1e-6)
    preparation.add_argument('--max-state-cells', type=int, default=10_000_000)

    status = sub.add_parser('status', help='Show the current complete optimizer checkpoint')
    status.add_argument('--run', required=True)
    continuation = sub.add_parser('continue', help='Prepare a new run from a checkpoint; default no iteration cap')
    continuation.add_argument('--from-run', dest='source_run', required=True)
    continuation.add_argument('--run', required=True)
    continuation.add_argument('--iterations', type=int, help='Optional new total update cap; omit for convergence-only stopping')
    continuation.add_argument('--relocate-from', help='Original absolute repository root recorded in the source plan')
    continuation.add_argument('--relocate-to', help='Repository root containing the transferred inputs')
    training = sub.add_parser('train', help='Train or resume the joint fit')
    training.add_argument('--run', required=True)
    training.add_argument('--max-updates', type=int,
                          help='Pause after this many new accepted updates')
    training.add_argument('--console-log', action='store_true',
                          help='Also write and rotate RUN/training.console.log')
    training.add_argument('--trace-routes', action='store_true',
                          help='Record every progress event in progress.jsonl')
    training.add_argument('--keep-log-archives', type=int,
                          help='Keep this many compressed segments per log; default keeps all')

    args = vars(parser.parse_args())
    command = args.pop('command')
    if command == 'template':
        result = template(args['checkpoint'], args['group'], args['output'],
                          args['collection'], args['exclude_groups'])
    elif command == 'bind':
        result = bind(**args)
    elif command == 'prepare':
        args['group_ids'] = args.pop('group')
        result = prepare(**args)
    elif command == 'status':
        root = Path(args['run'])
        result = json.dumps(load_generation(root, (root / 'current').resolve().name), indent=2)
    elif command == 'continue':
        result = continue_run(**args)
    else:
        result = train(**args)
    print(result)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, FileNotFoundError, FileExistsError, KeyError) as error:
        raise SystemExit(f'Error: {error}') from None
