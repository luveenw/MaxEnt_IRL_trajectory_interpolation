"""Exact static, goal-conditioned, eight-neighbour MaxEnt route likelihood.

The clock counts grid moves. Rewards apply at departure states, excluding the
terminal state. Signed weights are supported; no feature-sign encoding needed.
"""
import numpy as np

MOVES = [(y, x) for y in (-1, 0, 1) for x in (-1, 0, 1) if (y, x) != (0, 0)]


def neighbours(a):
    h, w = a.shape
    pad = np.pad(a, 1, constant_values=-np.inf)
    return np.stack([pad[1+y:1+y+h, 1+x:1+x+w] for y, x in MOVES])


def statistics(features, weights, route, max_state_cells=10_000_000):
    """Return log likelihood and its exact gradient; no path enumeration."""
    f = np.asarray(features, dtype=np.float64)
    route = np.asarray(route)
    if f.ndim != 3 or not np.isfinite(f).all() or not np.isfinite(weights).all():
        raise ValueError('Require finite static [feature,row,col] maps and weights')
    if route.ndim != 2 or route.shape[1] != 2 or len(route) < 3 or not np.issubdtype(route.dtype, np.integer):
        raise ValueError('Require at least three integer route states')
    _, h, w = f.shape
    if np.any(route < 0) or np.any(route >= [h, w]):
        raise ValueError('Route outside feature grid')
    moves = np.abs(np.diff(route, axis=0))
    if not np.all(moves.max(axis=1) == 1):
        raise ValueError('Require adjacent eight-neighbour moves without stays')
    if len(route)*h*w > max_state_cells:
        raise ValueError('Trajectory exceeds max_state_cells; use smaller grids or raise the explicit memory budget')
    reward = np.einsum('f,fhw->hw', weights, f)
    v = np.full((len(route), h, w), -np.inf)
    v[-1, route[-1, 0], route[-1, 1]] = 0
    for t in range(len(route)-2, -1, -1):
        v[t] = reward + np.logaddexp.reduce(neighbours(v[t+1]), axis=0)
    logz = v[0, route[0, 0], route[0, 1]]
    if not np.isfinite(logz):
        raise ValueError('Goal unreachable at this horizon')
    empirical = f[:, route[:-1, 0], route[:-1, 1]].sum(axis=1)
    expected = np.zeros(f.shape[0])
    d = np.zeros((h, w)); d[tuple(route[0])] = 1
    for t in range(len(route)-1):
        expected += np.einsum('fhw,hw->f', f, d)
        nb = neighbours(v[t+1])
        z = np.logaddexp.reduce(nb, axis=0)
        pi = np.zeros_like(nb)
        valid = np.isfinite(z)
        pi[:, valid] = np.exp(nb[:, valid]-z[valid])
        nxt = np.zeros_like(d)
        for a, (dy, dx) in enumerate(MOVES):
            ys, ye = max(0, -dy), h-max(0, dy)
            xs, xe = max(0, -dx), w-max(0, dx)
            nxt[ys+dy:ye+dy, xs+dx:xe+dx] += (d*pi[a])[ys:ye, xs:xe]
        d = nxt
    if not np.isclose(d[tuple(route[-1])], 1, atol=1e-8):
        raise ValueError('State visitation lost probability mass')
    return float(empirical @ weights-logz), empirical-expected
