"""
sim2d — RPLidar A1 simulation (official spec + real-car measured defects).

- Native 1454 beams/rev (8000 samples/s / 5.5 Hz), 0 = front, clockwise
- Output resampled to the racecar_core 720-sample array, in cm, 0.0 = no return
- REALISM mode (default): scan-interval jitter, whole-scan dropouts, 13%
  no-return beams, range-proportional noise, delivery latency
- ideal mode: refresh every tick, no noise, no defects
"""

import math
import random
from typing import Optional, Tuple

import numpy as np

import car_params as P
from world import World


class LidarA1:
    def __init__(self, world: World, realism: bool = True, seed: Optional[int] = None) -> None:
        self.world = world
        self.realism = realism
        self.rng = np.random.default_rng(seed)
        self.pyrng = random.Random(seed)

        # native beam directions (car frame, clockwise): world angle = theta - beam
        self._beam_angles = np.linspace(0, 2 * math.pi, P.LIDAR_BEAMS, endpoint=False)
        # ray march distances (m): half-pixel steps so walls cannot be skipped
        step = world.resolution / 2
        self._dists = np.arange(P.LIDAR_RANGE_MIN, P.LIDAR_RANGE_MAX + step, step)
        # nearest-beam mapping from 1454 native beams to the 720 output samples
        out_angles = np.linspace(0, 2 * math.pi, P.LIDAR_NUM_SAMPLES, endpoint=False)
        self._out_to_beam = np.round(
            out_angles / (2 * math.pi) * P.LIDAR_BEAMS
        ).astype(int) % P.LIDAR_BEAMS

        self.samples = np.zeros(P.LIDAR_NUM_SAMPLES, np.float32)  # delivered scan (cm)
        self.last_scan_time = -1.0    # capture time of the delivered scan
        self._next_capture = 0.0
        # pending = (deliver_time, samples, capture_pose, capture_time)
        self._pending: Optional[tuple] = None
        self.scan_pose: Optional[Tuple[float, float, float]] = None  # matches samples

    # marching step count per chunk; 100 steps is 0.5 m at 1 cm/px
    CHUNK = 100

    # ---------------------------------------------------------------- raycast
    def _raycast(self, x: float, y: float, theta: float) -> np.ndarray:
        """Hit distance (m) for all native beams; 0 = no hit. Vectorized DDA.

        Marched in chunks so beams that hit early stop costing work: in a
        corridor almost every beam hits within a couple of metres, while the
        A1 range runs to 12 m. Same first-hit result as marching the whole
        range at once, an order of magnitude less array traffic.
        """
        world_angles = theta - self._beam_angles
        cos_a = np.cos(world_angles)[:, None]
        sin_a = np.sin(world_angles)[:, None]

        res = self.world.resolution
        occupancy = self.world.occupancy
        height_px, width_px = self.world.height_px, self.world.width_px

        ranges = np.zeros(len(world_angles), np.float32)
        pending = np.ones(len(world_angles), bool)

        for lo in range(0, len(self._dists), self.CHUNK):
            if not pending.any():
                break
            dists = self._dists[lo:lo + self.CHUNK]
            px = x + cos_a[pending] * dists[None, :]
            py = y + sin_a[pending] * dists[None, :]

            cols = (px / res).astype(np.int32)
            rows = height_px - 1 - (py / res).astype(np.int32)
            outside = (rows < 0) | (rows >= height_px) | (cols < 0) | (cols >= width_px)
            hit = occupancy[np.clip(rows, 0, height_px - 1),
                            np.clip(cols, 0, width_px - 1)] | outside

            any_hit = hit.any(axis=1)
            if any_hit.any():
                first = hit.argmax(axis=1)
                idx = np.nonzero(pending)[0][any_hit]
                ranges[idx] = dists[first[any_hit]]
                pending[idx] = False

        return ranges

    def _make_scan(self, x: float, y: float, theta: float) -> np.ndarray:
        ranges = self._raycast(x, y, theta)               # m, native beams

        if self.realism:
            # range-proportional noise bands (A1 accuracy) + measured floor
            sigma = np.full_like(ranges, P.LIDAR_NOISE_FLOOR)
            lo = 0.0
            for hi, pct in P.LIDAR_ACC_BANDS:
                band = (ranges > lo) & (ranges <= hi)
                sigma[band] = np.maximum(P.LIDAR_NOISE_FLOOR, ranges[band] * pct)
                lo = hi
            noisy = ranges + self.rng.normal(0, 1, ranges.shape) * sigma
            noisy[ranges == 0.0] = 0.0
            # random no-return beams (real-car measured fraction)
            noisy[self.rng.random(ranges.shape) < P.LIDAR_NO_RETURN_FRAC] = 0.0
            ranges = noisy

        ranges = np.where(
            (ranges < P.LIDAR_RANGE_MIN) | (ranges > P.LIDAR_RANGE_MAX), 0.0, ranges
        )
        # native -> 720 nearest-beam, m -> cm
        return (ranges[self._out_to_beam] * 100.0).astype(np.float32)

    # ---------------------------------------------------------------- timing
    def update(self, t: float, x: float, y: float, theta: float) -> None:
        """Call every sim tick; captures new scans on the A1 schedule."""
        if not self.realism:
            self.samples = self._make_scan(x, y, theta)
            self.last_scan_time = t
            self.scan_pose = (x, y, theta)
            return

        # deliver a pending scan (samples/scan_pose/last_scan_time move together,
        # otherwise the renderer would draw an old scan at a new pose)
        if self._pending is not None and t >= self._pending[0]:
            _, self.samples, self.scan_pose, self.last_scan_time = self._pending
            self._pending = None

        if t >= self._next_capture:
            scan = self._make_scan(x, y, theta)
            self._pending = (t + P.LIDAR_LATENCY, scan, (x, y, theta), t)

            period = 1.0 / P.LIDAR_SCAN_HZ
            # interval jitter (measured std), floored at half a period
            interval = max(period * 0.5,
                           self.pyrng.gauss(period, P.LIDAR_JITTER_STD))
            # whole-scan dropout events (measured up to 1.36 s)
            if self.pyrng.random() < P.LIDAR_DROPOUT_PROB:
                interval += self.pyrng.uniform(0.3, P.LIDAR_DROPOUT_MAX)
            self._next_capture = t + interval

    def set_realism(self, realism: bool) -> None:
        self.realism = realism
        self._pending = None
        self._next_capture = 0.0
