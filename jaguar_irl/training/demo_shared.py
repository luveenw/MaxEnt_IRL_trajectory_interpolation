"""Build and verify a small, entirely synthetic joint fit across three extents."""
import argparse
import csv
from datetime import datetime, timedelta
import os
from pathlib import Path

import numpy as np

from jaguar_irl.data.movement_processor_pantanal_bouts import BoutConfig, BoutProcessor
from .shared import bind, map_plan_paths, prepare, resolve_plan_paths, template, train
from .shared_storage import read, write


def demo(output):
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    fields = ['Event_ID', 'timestamp', 'location.long', 'location.lat',
              'individual.local.identifier (ID)', 'study.name', 'country',
              'tag.local.identifier']
    with (out / 'synthetic_tracks.csv').open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        for individual in (1, 2, 3):
            for index in range(8):
                timestamp = datetime(2020, 6, 1) + timedelta(hours=2 * index)
                writer.writerow([
                    100 * individual + index, timestamp.strftime('%m/%d/%y %H:%M'),
                    -57 + individual + 0.006 * index, -18 + 0.006 * (index % 3),
                    individual, 'Pantanal', 'Brazil', f'tag{individual}',
                ])
    (out / 'synthetic_collars.csv').write_text(
        'ID,Sex,Planned Schedule (h)\n1,Male,2\n2,Female,2\n3,Male,2\n'
    )
    result = BoutProcessor(BoutConfig(
        csv_path=str(out / 'synthetic_tracks.csv'), output_dir=str(out / 'selection'),
        individual_ids=(1, 2, 3), gap_jitter_minutes=15,
    )).run_pipeline(collar_metadata_path=out / 'synthetic_collars.csv', render=False)
    checkpoint = Path(result['checkpoint_dir'])
    collection = next(item for item in result['collections'] if item['season'] == 'winter')
    groups = collection['group_ids']
    assert len(groups) == 3

    path = out / 'covariates.json'
    template(checkpoint, None, path, collection='WIN-C01')
    spec = read(path)
    spec['features'] = [
        dict(name=name, units='arbitrary synthetic units',
             definition='Random test landscape; no ecological interpretation', offset=0, scale=1)
        for name in ('synthetic_a', 'synthetic_b')
    ]
    rng = np.random.default_rng(20261102)
    grids = read(checkpoint / 'grids.json')
    (out / 'features').mkdir()
    for group_id, item in spec['groups'].items():
        grid = grids[item['grid_key']]
        item['files'] = {}
        for feature in spec['features']:
            filename = f'features/{group_id}_{feature["name"]}.npy'
            np.save(out / filename, rng.normal(size=(grid['rows'], grid['cols'])))
            item['files'][feature['name']] = filename
    write(path, spec)
    bind(checkpoint, path)

    run = out / 'run'
    prepare(checkpoint, run, collection='WIN-C01', split='unassigned', iterations=3)
    train(run, max_updates=1)
    first = read(run / 'current/state.json')
    assert first['iteration'] == 1 and first['groups'] == sorted(groups)
    train(run)
    resumed = read(run / 'current/state.json')

    # Use identical pinned inputs for an independent uninterrupted reference fit.
    reference = out / 'uninterrupted'
    reference.mkdir()
    inputs = resolve_plan_paths(read(run / 'plan.json'), run)
    write(reference / 'plan.json', map_plan_paths(inputs, lambda path: os.path.relpath(path, reference)))
    train(reference)
    reference_state = read(reference / 'current/state.json')
    assert {k: v for k, v in reference_state.items() if k != 'plan_key'} == {
        k: v for k, v in resumed.items() if k != 'plan_key'
    }
    pointer = (run / 'current').readlink()
    train(run)
    assert (run / 'current').readlink() == pointer
    assert not (run / 'current/stages').exists()

    write(out / 'verification.json', dict(
        synthetic_only=True, extents=3, individuals=3, joint_updates=3,
        all_groups_in_first_update=True, completed_iteration_resume_passed=True,
        uninterrupted_and_resumed_optimizer_states_identical=True,
        completed_run_is_noop=True, checkpoint=str(checkpoint), run=str(run),
    ))
    (out / 'README.md').write_text('''# Synthetic joint reward demonstration

All telemetry and environmental values here are synthetic. Coefficients have no
ecological interpretation. `run/current/state.json` contains the shared reward
for three spatial extents and three equally weighted individuals. Every optimizer
update includes all three extents. `run/current/weights.npy` stores coefficients
in the feature order listed in that JSON file.

`verification.json` records a pause after one complete update, successful resume,
and exact agreement with a separate uninterrupted fit in `uninterrupted/`.
`covariates.json` is a working example of named feature files attached to spatial
groups. The selector and exporter used the two-hour target, minimum three fixes,
and four-hour gap limit with fifteen minutes of jitter.
''')
    print(out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    demo(parser.parse_args().output)
