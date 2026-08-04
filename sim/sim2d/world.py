"""
sim2d — map loading and occupancy grid.

A map is an image plus a YAML file:
    image: track.png             # path relative to the yaml
    resolution: 0.01             # meters per pixel
    start_pose: [x, y, theta]    # meters/radians; origin = bottom-left, x right, y up
    occupied_thresh: 128         # gray < thresh = wall (black walls, ROS map style)
    negate: false                # true = inverted (bright = wall)

Color images (point-cloud exports): a pixel is a wall iff it has real color —
max(B,G,R) > 30 and min(B,G,R) < 200. White/near-white (faint floor points) and
black/transparent are free; occupied_thresh/negate are ignored.
"""

import os
from typing import Tuple

import cv2
import numpy as np
import yaml


class World:
    def __init__(self, yaml_path: str) -> None:
        with open(yaml_path) as f:
            cfg = yaml.safe_load(f)

        img_path = os.path.join(os.path.dirname(os.path.abspath(yaml_path)), cfg["image"])
        img = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise FileNotFoundError(f"cannot read map image: {img_path}")

        self.resolution: float = float(cfg["resolution"])
        self.start_pose: Tuple[float, float, float] = tuple(cfg.get("start_pose", [1.0, 1.0, 0.0]))
        thresh = int(cfg.get("occupied_thresh", 128))

        # occupancy[row, col] = True means wall
        if img.ndim == 3:
            mx = img[..., :3].max(axis=2)
            mn = img[..., :3].min(axis=2)
            self.occupancy: np.ndarray = (mx > 30) & (mn < 200)
        elif cfg.get("negate"):
            self.occupancy = img > 255 - thresh
        else:
            self.occupancy = img < thresh

        self.height_px, self.width_px = self.occupancy.shape
        self.width_m = self.width_px * self.resolution
        self.height_m = self.height_px * self.resolution

    # ---------------------------------------------------------------- queries
    def is_occupied(self, x: float, y: float) -> bool:
        """World coordinates; outside the map counts as wall."""
        col = int(x / self.resolution)
        row = self.height_px - 1 - int(y / self.resolution)
        if row < 0 or row >= self.height_px or col < 0 or col >= self.width_px:
            return True
        return bool(self.occupancy[row, col])

    def box_collides(self, cx: float, cy: float, theta: float,
                     length: float, width: float) -> bool:
        """Oriented rectangle (car body) vs walls: sample corners, edge midpoints, center."""
        c, s = np.cos(theta), np.sin(theta)
        hl, hw = length / 2, width / 2
        for lx, ly in ((hl, hw), (hl, -hw), (-hl, hw), (-hl, -hw),
                       (hl, 0), (-hl, 0), (0, hw), (0, -hw), (0, 0)):
            if self.is_occupied(cx + lx * c - ly * s, cy + lx * s + ly * c):
                return True
        return False
