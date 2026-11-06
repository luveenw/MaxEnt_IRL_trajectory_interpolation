"""Atomic, locked publication of complete generations on POSIX filesystems."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import uuid

import numpy as np

from jaguar_irl.data.pantanal_checkpoint import digest, json_text


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    with path.open('w') as handle:
        handle.write(json_text(value) + '\n')
        handle.flush()
        os.fsync(handle.fileno())


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def locked(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(f'Another writer holds {root}') from None
        yield


def generation(root, state):
    """Write a complete immutable binding or optimizer checkpoint before activation."""
    root = Path(root).resolve()
    versions = root / 'versions'
    versions.mkdir(parents=True, exist_ok=True)
    key = digest(state)
    dest = versions / key
    has_weights = state.get('kind') == 'shared_reward_iteration'
    if dest.exists():
        if read(dest / 'state.json') != state:
            raise ValueError('Generation content changed')
        if has_weights:
            weights = np.load(dest / 'weights.npy', allow_pickle=False)
            if not np.array_equal(weights, state['weights']):
                raise ValueError('Checkpoint weights changed')
        # A previous process may have stopped after rename but before fsync.
        sync_dir(versions)
        return key

    temp = versions / ('.pending-' + uuid.uuid4().hex)
    temp.mkdir()
    try:
        write(temp / 'state.json', state)
        if has_weights:
            with (temp / 'weights.npy').open('wb') as handle:
                np.save(handle, np.asarray(state['weights'], dtype=np.float64), allow_pickle=False)
                handle.flush()
                os.fsync(handle.fileno())
        sync_dir(temp)
        os.rename(temp, dest)
        sync_dir(versions)
    finally:
        # A hard kill can leave a pending directory; readers never use it.
        if temp.exists():
            shutil.rmtree(temp)
    return key


def publish(root, state):
    """Atomically activate both state.json and weights.npy with one pointer swap.

    Callers hold locked(root). Only current is authoritative; unused versions
    from an interrupted publication never contribute to resumed training.
    """
    root = Path(root).resolve()
    key = generation(root, state)
    dest = root / 'versions' / key
    pointer = root / ('.current-' + uuid.uuid4().hex)
    try:
        os.symlink(os.path.relpath(dest, root), pointer)
        os.replace(pointer, root / 'current')
        sync_dir(root)
    finally:
        pointer.unlink(missing_ok=True)
    return key
