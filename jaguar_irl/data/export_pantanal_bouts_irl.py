"""Export a seasonal bout collection with the matching three-fix/four-hour policy."""
import argparse

from .export_pantanal_seasonal_irl import export_collection
from .pantanal_checkpoint import load_selection_checkpoint
from .pantanal_irl_temporal import ExportConfig
from .movement_processor_pantanal_bouts import POLICY, JITTER_POLICY


def export_bout_collection(checkpoint_path, collection_id, output_root=None,
                           split_path=None, feature_maps_path=None):
    checkpoint = load_selection_checkpoint(checkpoint_path)
    policy = checkpoint['manifest']['selection_policy']
    if policy not in (POLICY, JITTER_POLICY):
        raise ValueError('Require an all-seasonal-bouts checkpoint')
    cap = 4.25 if policy == JITTER_POLICY else 4.0
    config = ExportConfig(min_source_segment_points=3, min_comparison_segment_points=3,
                          max_affected_fraction=1, source_gap_hours=cap, max_comparison_gap_hours=cap)
    return export_collection(checkpoint_path, collection_id, output_root, config,
                             split_path, feature_maps_path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint', required=True)
    p.add_argument('--collection', required=True)
    p.add_argument('--output')
    p.add_argument('--split')
    p.add_argument('--feature-maps')
    a = p.parse_args()
    print(export_bout_collection(a.checkpoint, a.collection, a.output, a.split, a.feature_maps))


if __name__ == '__main__':
    main()
