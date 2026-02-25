# -*- coding: utf-8 -*-
"""
Inference / prediction module for MaxEnt IRL.

Ported from test.py (Hirakawa et al. 2018) to Python 3.10+.
- print statements → logging
- Integer division fix
- Type hints added
- Configurable paths

Original: Copyright (C) 2018 Tsubasa Hirakawa. All rights reserved.
"""

from __future__ import annotations

import logging
import os
import multiprocessing as mp
from dataclasses import dataclass
from typing import Optional

from jaguar_irl.core.maxent_irl import MaxEntIRL
from jaguar_irl.utils.io import chunk_list, read_text

logger = logging.getLogger(__name__)


@dataclass
class PredictorConfig:
    """Configuration for IRL inference."""
    base_file: str = "./data/basename.txt"
    trajectory_path: str = "./data/tracking/"
    feature_map_file: str = "./data/feature_map/feature_map_3d.npy"
    result_dir: str = "./RESULT"
    trained_weight_file: str = "./RESULT/weight-015.txt"


def optimal_control_one_sample(
    input_base: str,
    input_weight_path: str,
    config: PredictorConfig,
) -> None:
    """Run inference on a single trajectory sample.

    Computes value function, policy, and forecast distribution,
    saving results to the result directory.
    """
    model = MaxEntIRL()
    model.load_trajectory(
        os.path.join(config.trajectory_path, input_base + ".npy")
    )
    model.load_reward_weights(input_weight_path)
    model.load_features(config.feature_map_file)

    model.compute_reward()

    # Soft value function
    model.compute_soft_value_function(
        os.path.join(config.result_dir, f"value_{input_base}.npy")
    )

    # Policy
    model.compute_policy(
        os.path.join(config.result_dir, f"policy_{input_base}.npy")
    )

    # Forecast distribution
    model.compute_forecast_distribution(
        os.path.join(config.result_dir, f"prob_{input_base}.npy")
    )

    logger.info("Inference complete for: %s", input_base)


def optimal_control_single_thread(
    input_base_list: list[str],
    input_weight_path: str,
    config: PredictorConfig,
) -> None:
    """Run inference on a list of trajectory samples (single thread)."""
    for base in input_base_list:
        optimal_control_one_sample(base, input_weight_path, config)


def main() -> None:
    """Main inference entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = PredictorConfig()
    n_cpu = mp.cpu_count()

    os.makedirs(config.result_dir, exist_ok=True)

    base_list = read_text(config.base_file)
    split_base_list = chunk_list(
        base_list,
        (len(base_list) // n_cpu) + 1,
    )

    processes: list[mp.Process] = []
    for b_list in split_base_list:
        processes.append(
            mp.Process(
                target=optimal_control_single_thread,
                args=(b_list, config.trained_weight_file, config),
            )
        )
    for p in processes:
        p.start()
    for p in processes:
        p.join()

    logger.info("Inference done.")


if __name__ == "__main__":
    main()
