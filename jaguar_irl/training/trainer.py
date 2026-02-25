# -*- coding: utf-8 -*-
"""
Training module for MaxEnt IRL.

Ported from train.py (Hirakawa et al. 2018) to Python 3.10+.
- print statements → logging
- Integer division fix (/ → //)
- Type hints added
- Configurable paths (no more module-level globals)

Original: Copyright (C) 2018 Tsubasa Hirakawa. All rights reserved.
"""

from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import multiprocessing as mp
import numpy as np
from numpy.typing import NDArray

from jaguar_irl.core.maxent_irl import MaxEntIRL
from jaguar_irl.utils.io import chunk_list, read_text

logger = logging.getLogger(__name__)


@dataclass
class TrainerConfig:
    """Configuration for the IRL training process."""
    base_file: str = "./data/basename.txt"
    trajectory_path: str = "./data/tracking"
    feature_map_file: str = "./data/feature_map/feature_map_3d.npy"
    result_dir: str = "./RESULT"
    cache_dir: str = "./CACHE"
    initial_weight: float = 0.5
    initial_lambda: float = 0.01
    delta: float = 0.01


class Trainer:
    """MaxEnt IRL trainer with multi-process backward-forward pass.

    Args:
        input_basename_list: List of trajectory base filenames.
        config: Training configuration.
    """

    def __init__(
        self,
        input_basename_list: list[str],
        config: Optional[TrainerConfig] = None,
    ) -> None:
        self.config = config or TrainerConfig()
        self.FLOAT_MAX: float = 1e30
        self.FLOAT_MIN: float = 1e-30
        self.n_cpu: int = mp.cpu_count()

        self.basename_list = input_basename_list
        self.split_base_list = chunk_list(
            self.basename_list,
            (len(self.basename_list) // self.n_cpu) + 1,
        )
        self.n_feature: int = np.load(self.config.feature_map_file).shape[0]
        self.n_data: int = len(input_basename_list)

        self.w: NDArray[np.float32] = (
            np.ones(self.n_feature, dtype=np.float32) * self.config.initial_weight
        )
        self.w_best: NDArray[np.float32] = np.array([], dtype=np.float32)

        # Feature counts
        self.f_empirical = np.zeros(self.n_feature, dtype=np.float32)
        self.f_expected = np.zeros(self.n_feature, dtype=np.float32)
        self.f_gradient = np.zeros(self.n_feature, dtype=np.float32)
        self.f_gradient_best: NDArray[np.float32] = np.array([], dtype=np.float32)

        self.loglikelihood: float = 0.0
        self.min_loglikelihood: float = -self.FLOAT_MAX
        self.lam: float = self.config.initial_lambda
        self.converged: bool = False
        self.pid: int = os.getpid()

        # Compute empirical feature count
        for bname in self.basename_list:
            tmp_model = MaxEntIRL()
            tmp_model.load_trajectory(
                os.path.join(self.config.trajectory_path, bname + ".npy")
            )
            tmp_model.update_weight(self.w)
            tmp_model.load_features(self.config.feature_map_file)
            self.f_empirical += tmp_model.compute_empirical_feature_count()
        self.f_empirical /= self.n_feature
        logger.info("Empirical feature count: %s", self.f_empirical)

        # Make cache directory
        os.makedirs(self.config.cache_dir, exist_ok=True)

    def backward_forward_pass(self) -> None:
        """Run parallel backward-forward passes across all trajectories."""
        processes: list[mp.Process] = []
        for th_i, b_list in enumerate(self.split_base_list):
            processes.append(
                mp.Process(
                    target=self.back_forward_single_thread,
                    args=(b_list, self.w, th_i),
                )
            )

        for p in processes:
            p.start()
        for p in processes:
            p.join()

        self.loglikelihood = 0.0
        self.f_expected *= 0.0
        for th_i in range(len(processes)):
            ll_tmp = np.load(
                os.path.join(self.config.cache_dir, f"{self.pid}-{th_i}-ll.npy")
            )
            f_exp_tmp = np.load(
                os.path.join(self.config.cache_dir, f"{self.pid}-{th_i}-fexp.npy")
            )

            self.loglikelihood += np.sum(ll_tmp)
            self.f_expected += np.sum(f_exp_tmp, axis=0)

        self.loglikelihood /= float(self.n_data)
        self.f_expected /= float(self.n_data)

    def back_forward_single_thread(
        self,
        basename: list[str],
        weight: NDArray[np.float32],
        thread_index: int,
    ) -> None:
        """Execute backward-forward pass for a subset of trajectories."""
        loglikelihood_tmp: list[float] = []
        f_expected_list: list[NDArray[np.float32]] = []

        for bn in basename:
            logger.info("Processing: %s", bn)
            _start = time.time()

            model = MaxEntIRL()
            model.load_trajectory(
                os.path.join(self.config.trajectory_path, bn + ".npy")
            )
            model.update_weight(weight)
            model.load_features(self.config.feature_map_file)

            model.compute_reward()
            model.compute_soft_value_function()
            model.compute_policy()
            model.compute_forecast_distribution()

            loglikelihood_tmp.append(model.compute_trajectory_likelihood())
            f_expected_list.append(model.accumulate_expected_feature_count())

            _end = time.time()
            logger.info("    done. time: %.2fs", _end - _start)

        # Save to cache
        np.save(
            os.path.join(self.config.cache_dir, f"{self.pid}-{thread_index}-ll.npy"),
            np.array(loglikelihood_tmp),
        )
        np.save(
            os.path.join(self.config.cache_dir, f"{self.pid}-{thread_index}-fexp.npy"),
            np.array(f_expected_list),
        )

    def gradient_update(self) -> None:
        """Update reward weights using exponentiated gradient descent."""
        improvement = self.loglikelihood - self.min_loglikelihood

        if improvement > self.config.delta:
            self.min_loglikelihood = self.loglikelihood
        elif -self.config.delta < improvement < self.config.delta:
            improvement = 0.0

        logger.info("Improved by: %.6f", improvement)

        if improvement < 0:
            logger.info("NO IMPROVEMENT: decrease step size and redo")
            self.lam *= 0.5
            for f in range(self.n_feature):
                self.w[f] = self.w_best[f] * math.exp(self.lam * self.f_gradient[f])

        elif improvement > 0:
            logger.info("IMPROVEMENT: increase step size")
            self.w_best = self.w.copy()
            self.lam *= 2.0
            for f in range(self.n_feature):
                self.f_gradient[f] = self.f_empirical[f] - self.f_expected[f]
            for f in range(self.n_feature):
                self.w[f] = self.w_best[f] * math.exp(self.lam * self.f_gradient[f])

        else:  # improvement == 0
            logger.info("CONVERGED")
            self.converged = True

        logger.info("lambda: %.6f", self.lam)
        logger.debug("f_empirical: %s", self.f_empirical)
        logger.debug("f_expected: %s", self.f_expected)

    def save_parameter(self, output_filename: str) -> None:
        """Save current weight vector to text file."""
        np.savetxt(output_filename, self.w)


def main() -> None:
    """Main training entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = TrainerConfig()
    os.makedirs(config.result_dir, exist_ok=True)

    basename_list = read_text(config.base_file)
    trainer = Trainer(basename_list, config)

    iteration = 0
    while not trainer.converged:
        start = time.time()

        trainer.backward_forward_pass()
        trainer.gradient_update()
        trainer.save_parameter(
            os.path.join(config.result_dir, f"weight-{iteration:03d}.txt")
        )
        iteration += 1

        end = time.time()
        logger.info("Time of this iteration: %.2fs", end - start)

    trainer.save_parameter(os.path.join(config.result_dir, "weight.txt"))
    logger.info("Training done.")


if __name__ == "__main__":
    main()
