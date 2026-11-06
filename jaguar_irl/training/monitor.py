"""Display completion counts for the objective evaluation in a live snapshot."""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def report(run):
    plan = json.loads((run / 'plan.json').read_text())
    snapshot = json.loads((run / 'progress.json').read_text())
    routes_by_group = defaultdict(list)
    for route in plan['trajectories']:
        routes_by_group[route['group_id']].append(route)
    routes = [route for group in plan['groups'] for route in routes_by_group[group]]
    last_animal_route = {}
    last_group_route = {}
    for index, route in enumerate(routes, start=1):
        last_animal_route[route['individual_id']] = index
        last_group_route[route['group_id']] = index

    event = snapshot['event']
    print(f"{snapshot['utc']} | {event} | update {snapshot.get('iteration', '—')}")
    if event in {'invocation_started', 'inputs_verified', 'checkpoint_resumed',
                 'initialization', 'iteration_started', 'line_search_trial'}:
        print('Waiting for the next objective evaluation.')
        return
    completed = snapshot.get('route_completed')
    if completed is None:
        return
    if snapshot['route_total'] != len(routes) or not 0 <= completed <= len(routes):
        raise ValueError('Snapshot route counts do not match the run plan')
    animals = sum(index <= completed for index in last_animal_route.values())
    groups = sum(index <= completed for index in last_group_route.values())
    print(f"Evaluation {snapshot['evaluation']} | trial {snapshot.get('trial', '—')}")
    print(f'Routes {completed}/{len(routes)} | '
          f'Individuals {animals}/{len(last_animal_route)} | '
          f'Groups {groups}/{len(last_group_route)}')
    if event in {'route_started', 'route_completed'}:
        label = 'Processing' if event == 'route_started' else 'Last completed'
        print(f"{label} {snapshot['group']} | individual {snapshot['individual_id']} | "
              f"{snapshot['trajectory_id']}")
    elif event == 'group_loading':
        print(f"Loading {snapshot['group']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path)
    args = parser.parse_args()
    try:
        report(args.run)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
