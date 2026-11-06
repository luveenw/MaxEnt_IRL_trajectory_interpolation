"""Describe retained observed displacements; never join bursts or change selection.

Run from the repository root. Outputs describe telemetry, not fitted movement
states or an estimate of the continuous path. Requires NumPy, pyproj, Matplotlib.
"""
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from pyproj import Geod, Transformer
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

SEASONS = ('winter', 'spring', 'summer', 'autumn')
GRID_SIZES = (100, 200, 250, 500, 1000)
GRID_COLORS = {100: '#487ca5', 200: '#bd7954', 250: '#439184', 500: '#8b699c', 1000: '#53626b'}
DISPLACEMENT_MARKERS = (('mean', '#ff0000'), ('median', '#0000ff'))
COLORS = ('#5a467e', '#477e93', '#439789', '#9d9453')
DEFAULT_CP = 'analysis/pantanal_seasonal_selection/checkpoints/selection_5bf188474d229bb43e3efde0'


def read_csv(path):
    with Path(path).open(newline='') as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    with Path(path).open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def describe(rows):
    result = {'steps': len(rows), 'animals': len({r['individual_id'] for r in rows}),
              'bursts': len({r['burst_id'] for r in rows})}
    for field in ('distance_m', 'speed_kmh', 'gap_h'):
        values = np.array([r[field] for r in rows])
        for name, value in zip(('min', 'p05', 'p25', 'median', 'p75', 'p95', 'p99', 'max'),
                               np.quantile(values, [0, .05, .25, .5, .75, .95, .99, 1])):
            result[f'{field}_{name}'] = float(value)
        result[f'{field}_mean'] = float(values.mean())
    distances = np.array([r['distance_m'] for r in rows])
    for threshold in (100, 200, 250, 500, 707.1067811865, 1000, 2000):
        result[f'pct_distance_lt_{threshold:g}m'] = float(100*np.mean(distances < threshold))
    for size in GRID_SIZES:
        result[f'pct_same_cell_{size}m'] = float(100*np.mean([r[f'same_cell_{size}m'] for r in rows]))
    result['pct_nonadjacent_500m'] = float(100*np.mean([r['grid_moves_500m'] > 1 for r in rows]))
    result['pct_regular_1p5_to_2p5h'] = float(100*np.mean([r['gap_h'] <= 2.5 for r in rows]))
    result['pct_gap_gt4h'] = float(100*np.mean([r['gap_h'] > 4 for r in rows]))
    return result


def analyze(cp, exports_index, out):
    out.mkdir(parents=True, exist_ok=True)
    provenance = {'checkpoint': str(cp), 'checkpoint_sha256': sha(cp/'checkpoint.json'),
                  'script_sha256': sha(__file__), 'exports_index': str(exports_index),
                  'input_hashes': {}, 'export_input_hashes': {}}
    names = ('source_points.csv', 'selector_points.csv', 'collection_members.csv',
             'window_seasons.csv', 'groups.csv', 'grids.json')
    for name in names:
        provenance['input_hashes'][name] = sha(cp/name)
    events = {r['source_event_key']: r for r in read_csv(cp/'source_points.csv')}
    transformer = Transformer.from_crs(4326, 32721, always_xy=True)
    for event in events.values():
        event['time'] = datetime.fromisoformat(event['timestamp'])
        event['lon'], event['lat'] = float(event['longitude']), float(event['latitude'])
        event['x'], event['y'] = transformer.transform(event['lon'], event['lat'])
    grids = json.loads((cp/'grids.json').read_text())
    groups = {r['group_id']: r for r in read_csv(cp/'groups.csv')}
    seasons = {r['window_key']: r['season'] for r in read_csv(cp/'window_seasons.csv')}
    canonical = {(r['group_id'], r['window_key']): r for r in read_csv(cp/'collection_members.csv')
                 if r['selection_status'] == 'selected'}
    segments = defaultdict(set)
    all_events = set()
    for row in read_csv(cp/'selector_points.csv'):
        all_events.add((row['window_key'], row['source_event_key']))
        if (row['group_id'], row['window_key']) in canonical:
            segments[(row['group_id'], row['window_key'], row['selector_subtrajectory_id'])].add(row['source_event_key'])
    selected_events = {(window, key) for (_, window, _), keys in segments.items() for key in keys}
    assert selected_events == all_events, 'Canonical cover must retain all temporal selector evidence'
    assert len({key for _, key in selected_events}) == len(selected_events), 'Repeated seasonal evidence'

    # Independently identify current exported optimizer-candidate observation edges.
    export_edges, candidate_edges = set(), set()
    export_same_cells = {}
    export_counts = {}
    for season, directory in json.loads(exports_index.read_text()).items():
        directory = Path(directory)
        rows = [r for r in read_csv(directory/'data/trajectory_manifest.csv')
                if r['variant'] == 'two_hour' and r['collection'] == 'independent']
        roster = {r['trajectory_id']: r for r in rows}
        links = defaultdict(list)
        for row in read_csv(directory/'data/point_links.csv'):
            if row['trajectory_id'] in roster:
                links[row['trajectory_id']].append(row)
        for ident, points in links.items():
            points.sort(key=lambda r: int(r['ordinal']))
            for a, b in zip(points, points[1:]):
                pair = (a['source_event_key'], b['source_event_key'])
                export_edges.add(pair)
                export_same_cells[pair] = (a['grid_row'], a['grid_col']) == (b['grid_row'], b['grid_col'])
                if roster[ident]['optimizer_candidate'] == 'True':
                    candidate_edges.add(pair)
        eligible = [r for r in rows if r['optimizer_candidate'] == 'True']
        export_counts[season] = {'candidate_routes': len(eligible),
                                'candidate_animals': len({r['individual_id'] for r in eligible})}
        for name in ('trajectory_manifest.csv', 'point_links.csv'):
            provenance['export_input_hashes'][str(directory/'data'/name)] = sha(directory/'data'/name)
    geod = Geod(ellps='WGS84')
    steps = []
    for (group, window, burst), keys in sorted(segments.items()):
        track = sorted((events[key] for key in keys), key=lambda r: r['time'])
        assert len(track) >= 3
        grid = grids[groups[group]['grid_key']]
        assert grid['crs'] == 'EPSG:32721' and grid['cell_size_m'] == 500
        xmin, ymin, xmax, ymax = grid['bounds']
        for a, b in zip(track, track[1:]):
            assert a['individual_id'] == b['individual_id'] and a['tag_id'] == b['tag_id']
            hours = (b['time']-a['time']).total_seconds()/3600
            assert 1.5 <= hours <= 4.25
            distance = geod.inv(a['lon'], a['lat'], b['lon'], b['lat'])[2]
            row = {'season': seasons[window], 'individual_id': a['individual_id'],
                   'group_id': group, 'window_key': window, 'burst_id': burst,
                   'from_event': a['source_event_key'], 'to_event': b['source_event_key'],
                   'from_timestamp': a['timestamp'], 'to_timestamp': b['timestamp'],
                   'gap_h': hours, 'gap_class': 'regular' if hours <= 2.5 else 'longer',
                   'distance_m': distance, 'speed_kmh': distance/1000/hours,
                   'projected_distance_m': float(np.hypot(b['x']-a['x'], b['y']-a['y'])),
                   'optimizer_candidate': (a['source_event_key'], b['source_event_key']) in candidate_edges}
            for size in GRID_SIZES:
                # Same upper-left origin; counterfactual sizes do not change maps or export.
                cells = [(int(np.floor((p['x']-xmin)/size)), int(np.floor((ymax-p['y'])/size))) for p in (a,b)]
                # Match exporter's treatment of exact exterior boundaries at actual 500 m size.
                if size == 500:
                    cells = [(min(c,grid['cols']-1), min(r,grid['rows']-1)) for c,r in cells]
                moves = max(abs(cells[0][i]-cells[1][i]) for i in (0,1))
                row[f'same_cell_{size}m'] = moves == 0
                if size == 500:
                    row['grid_moves_500m'] = moves
            assert row['same_cell_500m'] == export_same_cells[(row['from_event'], row['to_event'])]
            steps.append(row)
    edges = {(r['from_event'], r['to_event']) for r in steps}
    assert len(edges) == len(steps)
    provenance['export_comparison'] = {'selector_edges': len(edges), 'export_edges': len(export_edges),
                                     'selector_only': len(edges-export_edges), 'export_only': len(export_edges-edges)}
    # Explicit equality prevents attributing export gates to a different thinning result.
    assert edges == export_edges, provenance['export_comparison']
    write_csv(out/'steps.csv', steps)
    summary, animals = [], []
    for season in SEASONS:
        selected = [r for r in steps if r['season'] == season]
        for scope, subset in [('all_retained', selected),
                              ('regular_1p5_to_2p5h', [r for r in selected if r['gap_h'] <= 2.5]),
                              ('longer_gt2p5_to4p25h', [r for r in selected if r['gap_h'] > 2.5]),
                              ('optimizer_candidate', [r for r in selected if r['optimizer_candidate']]),
                              ('sensitivity_without_ID114', [r for r in selected if r['individual_id'] != '114'])]:
            if subset:
                summary.append({'season': season, 'scope': scope, **describe(subset)})
        for ident in sorted({r['individual_id'] for r in selected}, key=int):
            animals.append({'season': season, 'individual_id': ident,
                            **describe([r for r in selected if r['individual_id'] == ident])})
    write_csv(out/'season_metrics.csv', summary)
    write_csv(out/'animal_metrics.csv', animals)
    write_csv(out/'largest_speeds.csv', sorted(steps, key=lambda r:r['speed_kmh'], reverse=True)[:30])
    balanced = []
    for season in SEASONS:
        group = [r for r in animals if r['season'] == season]
        balanced.append({'season': season, 'median_animal_distance_median_m': float(np.median([r['distance_m_median'] for r in group])),
                         'median_animal_speed_median_kmh': float(np.median([r['speed_kmh_median'] for r in group])),
                         'equal_animal_pct_below500m': float(np.mean([r['pct_distance_lt_500m'] for r in group])),
                         'equal_animal_pct_same_cell500m': float(np.mean([r['pct_same_cell_500m'] for r in group])),
                         'largest_animal_share_pct': 100*max(r['steps'] for r in group)/sum(r['steps'] for r in group),
                         **export_counts[season]})
    write_csv(out/'animal_balanced_metrics.csv', balanced)
    provenance['counts'] = {'selected_fixes':len(selected_events), 'bursts':len(segments), 'steps':len(steps)}
    provenance['geodesic_projection_max_difference_m'] = max(abs(r['distance_m']-r['projected_distance_m']) for r in steps)
    provenance['checks'] = ['all canonical selected events equal deduplicated selector evidence',
        'unique event and edge ownership across seasons', 'within-burst same animal and tag',
        'at least three fixes and 1.5–4.25 hour step gaps', 'selector edges equal independent two_hour export edges',
        '500 m same-cell classifications match actual export point links']
    (out/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    plots(steps, summary, animals, out)
    print(json.dumps({'summary': [r for r in summary if r['scope']=='all_retained'], 'balanced':balanced,
                      'provenance':provenance['counts']}, indent=2))


def plots(steps, summary, animals, out):
    plt.rcParams.update({'font.size':10, 'axes.spines.top':False, 'axes.spines.right':False,
                         'axes.titleweight':'bold', 'savefig.dpi':170, 'svg.fonttype':'none'})
    duration_plot(steps, summary, out)
    cell_reference_plot(steps, summary, out)
    fig,axes=plt.subplots(1,2,figsize=(10.5,4.2),layout='constrained')
    rng=np.random.default_rng(17)
    for i,(season,color) in enumerate(zip(SEASONS,COLORS)):
        vals=[r['distance_m_median'] for r in animals if r['season']==season]
        axes[0].scatter(np.full(len(vals),i)+rng.uniform(-.13,.13,len(vals)),vals,s=23,color=color,alpha=.75)
        axes[0].plot([i-.2,i+.2],[np.median(vals)]*2,color='#333333',lw=2)
    axes[0].axhline(500,color='#555555',ls='--',lw=1)
    axes[0].set(xticks=range(4),xticklabels=[s.title() for s in SEASONS],ylabel='Each animal’s median displacement (m)',title='Each dot is one animal–season')
    for j,size in enumerate(GRID_SIZES):
        vals=[next(r for r in summary if r['season']==s and r['scope']=='all_retained')[f'pct_same_cell_{size}m'] for s in SEASONS]
        axes[1].bar(np.arange(4)+(j-2)*.16,vals,.15,label=f'{size} m',color=GRID_COLORS[size])
    axes[1].set(xticks=range(4),xticklabels=[s.title() for s in SEASONS],ylabel='Consecutive fixes in the same cell (%)',title='Grid-size sensitivity (fixed origin)')
    axes[1].set_ylim(0,95)
    axes[1].legend(frameon=False,ncol=5,loc='upper center',fontsize=8)
    for ax in axes: ax.grid(axis='y',alpha=.15)
    fig.savefig(out/'grid_sensitivity.png');fig.savefig(out/'grid_sensitivity.svg');plt.close(fig)


def displacement_markers(ax, metric):
    for statistic, color in DISPLACEMENT_MARKERS:
        distance = metric[f'distance_m_{statistic}']
        ax.axvline(distance, color=color, linestyle='--', linewidth=1.5,
                   label=f'{statistic.title()}: {distance:.0f} m', zorder=4)


def duration_plot(steps, summary, out):
    fig, axes = plt.subplots(4, 3, figsize=(12, 10), sharex='col', sharey='col',
                             layout='constrained')
    for row_axes, season, color in zip(axes, SEASONS, COLORS):
        regular_ax, longer_ax, speed_ax = row_axes
        rows = [row for row in steps if row['season'] == season]
        metric = next(row for row in summary if row['season'] == season and row['scope'] == 'all_retained')
        regular = [row['distance_m'] for row in rows if row['gap_h'] <= 2.5]
        regular_ax.hist(regular, bins=np.linspace(0, 3000, 41),
                        weights=np.full(len(regular), 100 / len(regular)),
                        histtype='step', color=color, linewidth=1.5)
        longer = np.sort([row['distance_m'] for row in rows if row['gap_h'] > 2.5])
        longer_ax.plot(longer, np.arange(1, len(longer) + 1) / len(longer) * 100, color=color)
        speed = np.sort([row['speed_kmh'] for row in rows])
        speed_ax.plot(speed, np.arange(1, len(speed) + 1) / len(speed) * 100, color=color)
        for ax in (regular_ax, longer_ax):
            ax.axvline(500, color='#555555', linestyle='--', linewidth=1)
            displacement_markers(ax, metric)
            ax.set_xlim(0, 3000)
        regular_ax.legend(loc='upper right', fontsize=8, frameon=False)
        regular_ax.set_ylabel(f'{season.title()}\nSteps per bin (%)')
        longer_ax.set_ylabel('Cumulative share (%)')
        speed_ax.set_ylabel('Cumulative share (%)')
        speed_ax.set_xscale('symlog', linthresh=.005)
        speed_ax.set_xlim(0, 7)
        speed_ax.set_xticks([0, .01, .1, 1, 7], ['0', '0.01', '0.1', '1', '7'])
        for ax in row_axes:
            ax.grid(alpha=.15)
    axes[0, 0].set_title('Regular gaps · 1.5–2.5 hours')
    axes[0, 1].set_title('Longer gaps · >2.5–4.25 hours')
    axes[0, 2].set_title('Speed · all retained steps')
    for ax in axes[-1, :2]:
        ax.set_xlabel('Observed displacement (m)')
    axes[-1, 2].set_xlabel('Displacement / elapsed time (km/h)')
    fig.suptitle('Displacements by gap length and seasonal speeds', fontsize=15)
    fig.savefig(out/'duration_distributions.png')
    fig.savefig(out/'duration_distributions.svg')
    plt.close(fig)


def cell_reference_plot(steps, summary, out):
    """Cell widths mark x-axis references; legend rates come from actual cells.

    Same-cell frequency cannot be read from the displacement CDF, because cell
    membership depends on endpoint positions and grid origin as well as distance.
    """
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), layout='constrained')
    for ax, season in zip(axes.flat, SEASONS):
        rows = [r for r in steps if r['season'] == season]
        metric = next(r for r in summary if r['season'] == season and r['scope'] == 'all_retained')
        values = np.sort([r['distance_m'] for r in rows])
        ax.plot(values, np.arange(1, len(values)+1)/len(values)*100, color='#344851', lw=1.9)
        for size in (100, 200, 250, 500):
            share = metric[f'pct_same_cell_{size}m']
            ax.axvline(size, color=GRID_COLORS[size], ls='--', lw=1.5,
                       label=f'{size} m: {share:.1f}% same-cell pairs')
        displacement_markers(ax, metric)
        ax.set_xscale('symlog', linthresh=10)
        ax.set(xlim=(0,20000), ylim=(0,102), xlabel='Observed displacement (m)',
               ylabel='Cumulative share of observed steps (%)',
               title=f'{season.title()} · {len(rows):,} retained steps')
        ax.set_xticks([0,10,100,500,1000,5000,20000], ['0','10','100','500','1k','5k','20k'])
        ax.legend(loc='lower right', fontsize=9, framealpha=.96,
                  title='Grid assignment and displacement', title_fontsize=9)
        ax.grid(alpha=.13)
    fig.suptitle('Retained displacements and cell-width sensitivity', fontsize=15)
    fig.supxlabel('Grid-width legend percentages give the measured share of same-cell pairs.', fontsize=10)
    fig.savefig(out/'distributions.png'); fig.savefig(out/'distributions.svg'); plt.close(fig)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint',type=Path,default=Path(DEFAULT_CP))
    parser.add_argument('--exports-index',type=Path,default=Path('analysis/pantanal_seasonal_selection/exports.json'))
    parser.add_argument('--output',type=Path,default=Path('analysis/pantanal_movement_scale/results'))
    args=parser.parse_args()
    analyze(args.checkpoint,args.exports_index,args.output)
