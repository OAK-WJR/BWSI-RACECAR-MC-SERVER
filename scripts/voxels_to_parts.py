#!/usr/bin/env python3
"""Merge voxels of the same block into cuboids.

Every part becomes one block_display entity in game, so the part count is what
decides whether the car is cheap enough to drive around. Greedy merging along
x, then z, then y typically cuts the count by an order of magnitude.
"""

import argparse
import json
from pathlib import Path


def merge(voxels):
    """Greedy 3D merge. Grows a run along x, widens it in z, then in y."""
    remaining = dict(voxels)
    parts = []
    for key in sorted(voxels):
        if key not in remaining:
            continue
        block = remaining[key]
        x, y, z = key

        width = 1
        while remaining.get((x + width, y, z)) == block:
            width += 1

        depth = 1
        while all(remaining.get((x + i, y, z + depth)) == block for i in range(width)):
            depth += 1

        height = 1
        while all(remaining.get((x + i, y + height, z + j)) == block
                  for i in range(width) for j in range(depth)):
            height += 1

        for i in range(width):
            for j in range(height):
                for k in range(depth):
                    remaining.pop((x + i, y + j, z + k), None)
        parts.append({"x": x, "y": y, "z": z,
                      "w": width, "h": height, "d": depth, "block": block})
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("voxel_json")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.voxel_json).read_text())
    voxels = {(v["x"], v["y"], v["z"]): v["block"] for v in data["voxels"]}
    parts = merge(voxels)

    out = {"size": data["size"], "voxel_metres": data["voxel_metres"], "parts": parts}
    Path(args.out).write_text(json.dumps(out))
    print(f"{len(voxels):,} voxels -> {len(parts):,} parts "
          f"({len(voxels) / max(1, len(parts)):.1f}x fewer entities)")


if __name__ == "__main__":
    main()
