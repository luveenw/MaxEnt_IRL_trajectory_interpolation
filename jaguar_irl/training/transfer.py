"""List the files needed to train or resume a prepared run on another machine."""

import argparse
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .shared import load_generation, resolve_plan_paths, software, verify_inputs
from .shared_storage import locked, read
from jaguar_irl.data.pantanal_checkpoint import digest


CODE_ROOT = Path(__file__).resolve().parents[2]
TRAINER_FILES = (
    'jaguar_irl/__init__.py',
    'jaguar_irl/core/__init__.py',
    'jaguar_irl/core/shared_reward.py',
    'jaguar_irl/data/__init__.py',
    'jaguar_irl/data/pantanal_checkpoint.py',
    'jaguar_irl/training/__init__.py',
    'jaguar_irl/training/monitor.py',
    'jaguar_irl/training/shared.py',
    'jaguar_irl/training/shared_storage.py',
    'jaguar_irl/training/transfer.py',
)


def transfer_manifest(run, root, output=None):
    """Write an rsync file list under the same writer lock as training."""
    run, root = Path(run).resolve(), Path(root).resolve()
    plan_path = run / 'plan.json'
    if not plan_path.is_file():
        raise ValueError(f'Prepare the run before generating a transfer list: {plan_path}')
    if not run.is_relative_to(root) or not CODE_ROOT.is_relative_to(root):
        raise ValueError('Transfer root must contain both the run and trainer checkout')
    output = Path(output).resolve() if output else run / 'cluster-transfer-files.txt'

    with locked(run):
        stored = read(plan_path)
        plan = resolve_plan_paths(stored, run)
        current = run / 'current'
        has_checkpoint = current.is_symlink()
        if not has_checkpoint and (current.exists() or plan.get('continuation')):
            raise ValueError('Expected a published checkpoint symlink for this run')
        verify_inputs(plan, check_software=not has_checkpoint)
        files = {plan_path, Path(plan['binding_path'])}
        if has_checkpoint:
            installed = software()
            for name in ('shared_reward.py', 'shared_storage.py'):
                if stored['software'].get(name) != installed[name]:
                    raise ValueError('Checkpoint transfer requires matching numerical core and storage code')
            generation = current.resolve(strict=True)
            if current.readlink().is_absolute() or generation.parent != run / 'versions':
                raise ValueError('Expected current to link relatively to a generation in versions/')
            if load_generation(run, generation.name)['plan_key'] != digest(stored):
                raise ValueError('Published checkpoint does not match the run plan')
            files.update((current, generation / 'state.json', generation / 'weights.npy'))

        for key, name in (('checkpoint', 'checkpoint.json'), ('export', 'export_manifest.json')):
            directory = Path(plan[key])
            manifest = directory / name
            files.add(manifest)
            files.update(directory / member for member in read(manifest)['files'])
        for group in plan['bindings']['groups'].values():
            files.update(Path(entry['path']) for entry in group['files'].values())
        files.update(Path(row['path']) for row in plan['trajectories'])
        if parent := plan.get('continuation'):
            generation = Path(parent['source_checkpoint'])
            source_run = Path(parent['source_run'])
            files.update((source_run / 'plan.json', generation / 'state.json',
                          generation / 'weights.npy'))
            pin = source_run / 'checkpoint-pins' / generation.name
            if pin.exists():
                files.add(pin)
        files.update(CODE_ROOT / name for name in TRAINER_FILES)

        names = []
        for path in sorted(files):
            if not path.is_relative_to(root) or not path.resolve().is_relative_to(root):
                raise ValueError(f'Input lies outside the transfer root: {path}')
            if path != current and (path != path.resolve() or not path.is_file()):
                raise ValueError(f'Expected a regular input file, without symlinks: {path}')
            name = path.relative_to(root).as_posix()
            if '\n' in name or '\r' in name:
                raise ValueError(f'Cannot represent this path in a line-based list: {path!r}')
            names.append(f'./{name}' if name.startswith(('#', ';')) else name)
        if (output in files or output == run / '.lock'
                or output.is_relative_to(run / 'versions')
                or output.is_relative_to(run / 'checkpoint-pins')):
            raise ValueError('Transfer list destination overlaps a pinned input or generation')

        with NamedTemporaryFile(mode='w', encoding='utf-8', dir=output.parent,
                                prefix='.transfer-', delete=False) as handle:
            temporary = Path(handle.name)
            try:
                handle.write('\n'.join(names) + '\n')
                handle.close()
                os.replace(temporary, output)
            finally:
                temporary.unlink(missing_ok=True)
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, help='Prepared training directory')
    parser.add_argument('--root', default='.', help='Source root for the file list, defaults to cwd')
    parser.add_argument('--output', help='Defaults to RUN/cluster-transfer-files.txt')
    args = parser.parse_args()
    try:
        print(transfer_manifest(args.run, args.root, args.output))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
