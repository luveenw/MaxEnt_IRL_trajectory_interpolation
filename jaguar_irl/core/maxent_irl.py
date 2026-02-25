# -*- coding: utf-8 -*-
"""
MaxEnt IRL core implementation.

Ported from Hirakawa et al. (2018) Python 2.7 codebase to Python 3.10+.
- cv2.dilate replaced with scipy.ndimage.binary_dilation
- cv2.imread/imwrite replaced with imageio
- print statements replaced with logging
- sys.exit replaced with exceptions
- np.bool deprecated → bool
- Type hints added throughout

Original: Copyright (C) 2018 Tsubasa Hirakawa. All rights reserved.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import binary_dilation

logger = logging.getLogger(__name__)


class MaxEntIRLError(Exception):
    """Base exception for MaxEntIRL errors."""
    pass


class MaxEntIRL:
    """Maximum Entropy Inverse Reinforcement Learning.

    Implements soft value iteration, policy computation, forecast
    distribution, and training utilities for a 3D (y, x, time) state
    space with 9 discrete actions (8 neighbours + stay).

    Attributes:
        w: Reward weight vector of shape (n_feature,).
        feature_map: Feature map array of shape (n_feature, *state_size).
        reward: Computed reward map of shape state_size.
        V: Soft value function of shape state_size.
        pax: Policy array of shape (n_action, *state_size).
        D: State visitation distribution of shape state_size.
        start: Start coordinates [y, x, t].
        end: End coordinates [y, x, t].
        trajectory: Trajectory array of shape (n_steps, 3).
        state_size: Tuple (height, width, time_steps).
        n_action: Number of actions (default 9).
        n_feature: Number of features.
        max_length: Maximum trajectory length (default 610).
    """

    def __init__(self, max_length: int = 610, n_action: int = 9) -> None:
        self.w: Optional[NDArray[np.float32]] = None
        self.feature_map: NDArray = np.empty([0])
        self.reward: NDArray = np.array([])
        self.V: NDArray = np.array([])
        self.pax: NDArray = np.array([])
        self.D: NDArray = np.array([])
        self.start: NDArray = np.array([])
        self.end: NDArray = np.array([])
        self.trajectory: NDArray = np.empty([0])
        self.FLOAT_MAX: float = 1e30
        self.FLOAT_MIN: float = 1e-30
        self.state_size: tuple[int, ...] = ()
        self.n_action: int = n_action
        self.n_feature: int = 0
        self.max_length: int = max_length

    # ------------------------------------------------------------------ #
    #  Data loading
    # ------------------------------------------------------------------ #

    def load_trajectory(self, input_filename: str, verbose: bool = False) -> None:
        """Load trajectory from a .npy file.

        Expects an array of shape (n_steps, 3) where columns are [y, x, t].
        """
        if verbose:
            logger.info("Loading terminal points...")
        self.trajectory = np.load(input_filename)
        self.start = self.trajectory[0, :]
        self.end = self.trajectory[-1, :]
        if verbose:
            logger.info("    length of the trajectory: %d", self.trajectory.shape[0])
            logger.info("    start: %s", self.start)
            logger.info("    end: %s", self.end)

    def load_reward_weights(self, input_filename: str, verbose: bool = False) -> None:
        """Load reward weights from a text file."""
        if verbose:
            logger.info("Loading reward weights...")
        self.w = np.loadtxt(input_filename).astype(np.float32)
        if verbose:
            logger.info("    number of weights loaded: %d", self.w.shape[0])

    def load_features(self, input_filename: str, verbose: bool = False) -> None:
        """Load feature map from a .npy file.

        Expects shape (n_features, *state_size).
        """
        if verbose:
            logger.info("Loading features...")

        self.feature_map = np.load(input_filename)

        if self.w is None:
            raise MaxEntIRLError("Weights must be loaded before features.")
        if self.feature_map.shape[0] != self.w.shape[0]:
            raise MaxEntIRLError(
                f"Weight length ({self.w.shape[0]}) and feature count "
                f"({self.feature_map.shape[0]}) do not match."
            )
        self.n_feature = self.feature_map.shape[0]
        self.state_size = self.feature_map[0].shape
        if verbose:
            logger.info("    number of feature maps loaded: %d", self.feature_map.shape[0])
            logger.info("    state space size: %s", self.state_size)

    # ------------------------------------------------------------------ #
    #  Core IRL computations
    # ------------------------------------------------------------------ #

    def compute_reward(self, bias: float = 0.0, verbose: bool = False) -> None:
        """Compute reward map R = sum_i(w_i * f_i) + bias."""
        if verbose:
            logger.info("Computing reward value...")
        self.reward = np.zeros(self.state_size, dtype=np.float32)
        for i in range(self.n_feature):
            self.reward += self.w[i] * self.feature_map[i]
        self.reward += float(bias)
        if verbose:
            logger.info("    done")

    def compute_soft_value_function(
        self,
        output_filename: Optional[str] = None,
        verbose: bool = False,
    ) -> None:
        """Compute soft value function via backward pass.

        Uses log-sum-exp (softmax) Bellman backup from the goal state.
        """
        if verbose:
            logger.info("Computing soft value function...")

        v = [
            np.ones(self.state_size, dtype=np.float32) * -self.FLOAT_MAX,
            np.ones(self.state_size, dtype=np.float32) * -self.FLOAT_MAX,
        ]

        # init goal
        end_y, end_x, end_t = int(self.end[0]), int(self.end[1]), int(self.end[2])
        v[0][end_y, end_x, end_t] = 0.0

        is_searched = np.zeros(self.state_size, dtype=bool)
        is_searched[end_y, end_x, end_t] = True

        backward_mask = self.make_backward_mask()

        v_padded = np.ones(
            [self.state_size[0] + 2, self.state_size[1] + 2, self.state_size[2] + 2],
            dtype=np.float32,
        ) * -self.FLOAT_MAX

        n = 0
        b_time = end_t
        while True:
            b_time -= 1

            v_padded[
                1:1 + self.state_size[0],
                1:1 + self.state_size[1],
                1:1 + self.state_size[2],
            ] = v[0].copy()

            if b_time >= 0:
                is_searched[:, :, b_time] = backward_mask[:, :, b_time].copy()

            for y in range(3):
                for x in range(3):
                    if y == 1 and x == 1:
                        continue
                    minv = np.minimum(
                        v[0],
                        v_padded[
                            y:y + self.state_size[0],
                            x:x + self.state_size[1],
                            2:2 + self.state_size[2],
                        ],
                    )
                    maxv = np.maximum(
                        v[0],
                        v_padded[
                            y:y + self.state_size[0],
                            x:x + self.state_size[1],
                            2:2 + self.state_size[2],
                        ],
                    )
                    softmax = maxv + np.log(1.0 + np.exp(minv - maxv))
                    v[0][is_searched] = softmax[is_searched]

            v[0][is_searched] += self.reward[is_searched]

            # bias for reward map (retained from original)
            v[0][is_searched] -= 10.0

            if np.sum(v[0][is_searched] > 0) > 0:
                raise MaxEntIRLError(
                    "Elements of V[0] should be <= 0. "
                    "Check reward map and bias values."
                )

            # re-init goal
            v[0][end_y, end_x, end_t] = 0.0

            # convergence criteria
            residual = np.abs(v[0] - v[1])
            maxval = np.max(residual[backward_mask])
            v[1] = v[0].copy()

            if maxval < 0.9:
                break

            n += 1
            if n > 1000:
                logger.warning("Max number of iterations reached: %d", n)
                break

        self.V = v[0].copy()

        if output_filename is not None:
            np.save(output_filename, self.V)

    def compute_policy(
        self,
        output_filename: Optional[str] = None,
        verbose: bool = False,
    ) -> None:
        """Compute stochastic policy from the soft value function.

        Policy π(a|s) is proportional to exp(Q(s,a) - V(s)).
        """
        if verbose:
            logger.info("Computing policy...")

        policy = [np.zeros(self.state_size, dtype=np.float32) for _ in range(self.n_action)]

        self.V[self.V <= -self.FLOAT_MAX] = -np.inf
        v_padded = np.ones(
            [self.state_size[0] + 2, self.state_size[1] + 2, self.state_size[2] + 2],
            dtype=np.float32,
        ) * -np.inf
        v_padded[
            1:1 + self.state_size[0],
            1:1 + self.state_size[1],
            1:1 + self.state_size[2],
        ] = self.V.copy()

        end_t = int(self.end[2])
        for t in range(self.state_size[2]):
            if t == end_t:
                break

            sub = np.zeros(
                [self.n_action, self.state_size[0], self.state_size[1]],
                dtype=np.float32,
            )

            # Each action corresponds to a spatial offset in the padded array
            sub[0, :, :] = v_padded[0:self.state_size[0], 0:self.state_size[1], t + 2]
            sub[1, :, :] = v_padded[0:self.state_size[0], 1:1 + self.state_size[1], t + 2]
            sub[2, :, :] = v_padded[0:self.state_size[0], 2:2 + self.state_size[1], t + 2]
            sub[3, :, :] = v_padded[1:1 + self.state_size[0], 0:self.state_size[1], t + 2]
            sub[4, :, :] = v_padded[1:1 + self.state_size[0], 1:1 + self.state_size[1], t + 2]
            sub[5, :, :] = v_padded[1:1 + self.state_size[0], 2:2 + self.state_size[1], t + 2]
            sub[6, :, :] = v_padded[2:2 + self.state_size[0], 0:self.state_size[1], t + 2]
            sub[7, :, :] = v_padded[2:2 + self.state_size[0], 1:1 + self.state_size[1], t + 2]
            sub[8, :, :] = v_padded[2:2 + self.state_size[0], 2:2 + self.state_size[1], t + 2]

            max_values = np.max(sub, axis=0)
            is_not_inf_mask = ~np.isinf(max_values)

            p = sub.copy()
            p[:, is_not_inf_mask] = sub[:, is_not_inf_mask] - max_values[is_not_inf_mask]
            p = np.exp(p)
            p[4, :, :] = 0.0  # "stay" action probability set to 0

            summation = np.sum(p, axis=0)
            is_pos = summation > 0

            for i in range(self.n_action):
                policy[i][is_pos, t] = p[i, is_pos] / summation[is_pos]
                if i == 4:
                    policy[i][~is_pos, t] = 0.0
                else:
                    policy[i][~is_pos, t] = 1.0 / (self.n_action - 1.0)

        if verbose:
            logger.info("    done")

        self.pax = np.array(policy)

        if output_filename is not None:
            np.save(output_filename, self.pax)

    def compute_forecast_distribution(
        self,
        output_filename: Optional[str] = None,
        verbose: bool = False,
    ) -> None:
        """Compute forecast distribution via forward pass.

        Propagates probability mass from the start state using the
        learned policy.
        """
        if verbose:
            logger.info("Computing forecast distribution...")

        self.D = np.zeros(self.state_size, dtype=np.float32)
        N = [self.D.copy(), self.D.copy()]

        start_y, start_x, start_t = int(self.start[0]), int(self.start[1]), int(self.start[2])
        end_y, end_x, end_t = int(self.end[0]), int(self.end[1]), int(self.end[2])

        N[0][start_y, start_x, start_t] = 1.0

        col = self.state_size[0]
        row = self.state_size[1]
        length = self.state_size[2]

        border = self.make_border_mask()
        forward_mask = self.make_forward_mask()
        backward_mask = self.make_backward_mask()
        back_forward_mask = np.logical_and(forward_mask, backward_mask)

        mask = np.zeros(self.state_size, dtype=bool)

        n = 0
        while True:
            N[1] *= 0.0

            mask[:, :, n] = back_forward_mask[:, :, n].copy()
            padded_mask = np.pad(mask, 1, mode='constant', constant_values=False)

            n_pax_tmp = [N[0] * self.pax[i, :, :, :] for i in range(9)]

            # north-west (top-left)
            N[1][padded_mask[2:2 + col, 2:2 + row, 0:length]] += \
                n_pax_tmp[0][np.logical_and(mask, border[0])]
            # north (top)
            N[1][padded_mask[2:2 + col, 1:1 + row, 0:length]] += \
                n_pax_tmp[1][np.logical_and(mask, border[1])]
            # north-east (top-right)
            N[1][padded_mask[2:2 + col, 0:0 + row, 0:length]] += \
                n_pax_tmp[2][np.logical_and(mask, border[2])]
            # west (left)
            N[1][padded_mask[1:1 + col, 2:2 + row, 0:length]] += \
                n_pax_tmp[3][np.logical_and(mask, border[3])]
            # east (right)
            N[1][padded_mask[1:1 + col, 0:0 + row, 0:length]] += \
                n_pax_tmp[5][np.logical_and(mask, border[5])]
            # south-west (bottom-left)
            N[1][padded_mask[0:0 + col, 2:2 + row, 0:length]] += \
                n_pax_tmp[6][np.logical_and(mask, border[6])]
            # south (bottom)
            N[1][padded_mask[0:0 + col, 1:1 + row, 0:length]] += \
                n_pax_tmp[7][np.logical_and(mask, border[7])]
            # south-east (bottom-right)
            N[1][padded_mask[0:0 + col, 0:0 + row, 0:length]] += \
                n_pax_tmp[8][np.logical_and(mask, border[8])]

            # init goal
            N[1][end_y, end_x, end_t] = 0.0

            self.D += N[1]

            # swap buffers
            N[0], N[1] = N[1], N[0]

            n += 1
            if n > end_t:
                break

        if verbose:
            logger.info("    done")

        if output_filename is not None:
            np.save(output_filename, self.D)

    # ------------------------------------------------------------------ #
    #  Mask construction (cv2.dilate → scipy.ndimage.binary_dilation)
    # ------------------------------------------------------------------ #

    def make_backward_mask(self) -> NDArray[np.bool_]:
        """Create reachability mask expanding backward from the goal."""
        logger.debug("    Making backward mask...")
        mask = np.zeros(self.state_size, dtype=bool)
        end_y, end_x, end_t = int(self.end[0]), int(self.end[1]), int(self.end[2])
        mask[end_y, end_x, end_t] = True

        # 3×3 structuring element = 8-connected neighbourhood
        struct = np.ones((3, 3), dtype=bool)
        mask_slice = mask[:, :, end_t].copy()

        for i in reversed(range(end_t)):
            if mask_slice.all():
                mask[:, :, 0:i + 1] = True
                break
            mask_slice = binary_dilation(mask_slice, structure=struct)
            mask[:, :, i] = mask_slice.copy()

        return mask

    def make_forward_mask(self) -> NDArray[np.bool_]:
        """Create reachability mask expanding forward from the start."""
        logger.debug("    Making forward mask...")
        mask = np.zeros(self.state_size, dtype=bool)
        start_y, start_x, start_t = (
            int(self.start[0]), int(self.start[1]), int(self.start[2])
        )
        mask[start_y, start_x, start_t] = True

        struct = np.ones((3, 3), dtype=bool)
        mask_slice = mask[:, :, start_t].copy()

        for i in range(self.state_size[2]):
            if mask_slice.all():
                mask[:, :, i:self.state_size[2]] = True
                break
            mask[:, :, i] = mask_slice.copy()
            mask_slice = binary_dilation(mask_slice, structure=struct)

        return mask

    def make_border_mask(self) -> list[NDArray[np.bool_]]:
        """Create masks for valid moves away from grid boundaries.

        Returns a list of 9 boolean arrays (one per action direction).
        """
        top = np.ones(self.state_size, dtype=bool)
        top[0, :, :] = False
        bottom = np.ones(self.state_size, dtype=bool)
        bottom[-1, :, :] = False
        left = np.ones(self.state_size, dtype=bool)
        left[:, 0] = False
        right = np.ones(self.state_size, dtype=bool)
        right[:, -1] = False

        return [
            np.logical_and(top, left),               # 0: top-left
            top.copy(),                               # 1: top
            np.logical_and(top, right),               # 2: top-right
            left.copy(),                              # 3: left
            np.ones(self.state_size, dtype=bool),      # 4: center (not used)
            right.copy(),                             # 5: right
            np.logical_and(bottom, left),             # 6: bottom-left
            bottom.copy(),                            # 7: bottom
            np.logical_and(bottom, right),            # 8: bottom-right
        ]

    # ------------------------------------------------------------------ #
    #  Training utilities
    # ------------------------------------------------------------------ #

    def compute_empirical_feature_count(self) -> NDArray[np.float32]:
        """Sum feature values along the observed trajectory."""
        f_empirical = np.zeros(self.n_feature, dtype=np.float32)
        for coord in self.trajectory:
            f_empirical += self.feature_map[
                :, int(coord[0]), int(coord[1]), int(coord[2])
            ]
        return f_empirical

    def update_weight(self, input_weight: NDArray[np.float32]) -> None:
        """Set the reward weight vector."""
        self.w = input_weight

    def compute_trajectory_likelihood(self) -> float:
        """Compute log-likelihood of the trajectory under the learned policy.

        Returns:
            Log-likelihood value (float). Returns -FLOAT_MAX on failure.
        """
        trans_index = np.array(
            [[0, 1, 2],
             [3, -1, 5],
             [6, 7, 8]],
            dtype=np.int32,
        )
        ll = 0.0

        for t in range(self.trajectory.shape[0] - 1):
            dx = int(self.trajectory[t + 1, 1] - self.trajectory[t, 1])
            dy = int(self.trajectory[t + 1, 0] - self.trajectory[t, 0])

            a = trans_index[dy + 1, dx + 1]

            if a < 0:
                raise MaxEntIRLError(
                    f"Invalid action at step {t}: dx={dx}, dy={dy}. "
                    "Preprocess trajectory data properly."
                )

            val = np.log(
                self.pax[a][
                    int(self.trajectory[t, 0]),
                    int(self.trajectory[t, 1]),
                    int(self.trajectory[t, 2]),
                ]
            )

            if val < -self.FLOAT_MAX:
                ll = -self.FLOAT_MAX
                break

            ll += val
        return ll

    def accumulate_expected_feature_count(self) -> NDArray[np.float32]:
        """Compute expected feature counts under the forecast distribution."""
        f_expected_tmp = []
        for f in range(self.n_feature):
            F = self.D * self.feature_map[f, :, :, :]
            f_expected_tmp.append(np.sum(F))
        return np.array(f_expected_tmp, dtype=np.float32)

    # ------------------------------------------------------------------ #
    #  Endpoint manipulation (for reverse-time simulation)
    # ------------------------------------------------------------------ #

    def set_endpoint(self, endpoint: NDArray) -> None:
        """Override the trajectory endpoint (for reverse-time simulation)."""
        self.end = np.asarray(endpoint, dtype=self.trajectory.dtype)

    def set_startpoint(self, startpoint: NDArray) -> None:
        """Override the trajectory startpoint (for forward simulation)."""
        self.start = np.asarray(startpoint, dtype=self.trajectory.dtype)
