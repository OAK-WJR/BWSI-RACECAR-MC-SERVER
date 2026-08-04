#!/usr/bin/env python3
"""Voxelize a flat-backed relief STL (a coin, a medal) into columns.

The mesh is rasterised into a heightmap, then every cell becomes a solid
column from the flat back up to the surface. Cells whose surface rises above
--relief-z get the relief block, the rest get the base block. Output is the
same JSON that voxels_to_parts.py consumes.
"""

import argparse
import json
import math
import struct
from pathlib import Path


def read_binary_stl(path):
    triangles = []
    with open(path, "rb") as f:
        f.read(80)
        (count,) = struct.unpack("<I", f.read(4))
        for _ in range(count):
            values = struct.unpack("<12fH", f.read(50))
            triangles.append([tuple(values[3 + v * 3:6 + v * 3]) for v in range(3)])
    return triangles


def heightmap(triangles, cell):
    xs = [v[0] for t in triangles for v in t]
    ys = [v[1] for t in triangles for v in t]
    min_x, min_y = min(xs), min(ys)
    width = math.ceil((max(xs) - min_x) / cell)
    depth = math.ceil((max(ys) - min_y) / cell)

    top = {}
    for tri in triangles:
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = tri
        longest = max(math.dist(tri[0][:2], tri[1][:2]),
                      math.dist(tri[0][:2], tri[2][:2]))
        steps = max(2, int(longest / (cell * 0.4)) + 1)
        for i in range(steps + 1):
            for j in range(steps + 1 - i):
                a, b = i / steps, j / steps
                c = 1 - a - b
                x = a * x0 + b * x1 + c * x2
                y = a * y0 + b * y1 + c * y2
                z = a * z0 + b * z1 + c * z2
                key = (int((x - min_x) / cell), int((y - min_y) / cell))
                if z > top.get(key, -1e30):
                    top[key] = z
    return top, width, depth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stl")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--cells", type=int, default=40,
                    help="grid cells across the widest side")
    ap.add_argument("--relief-z", type=float, required=True,
                    help="surface above this model-z gets the relief block")
    ap.add_argument("--relief-block", default="minecraft:gold_block")
    ap.add_argument("--base-block", default="minecraft:raw_gold_block")
    ap.add_argument("--voxel-metres", type=float, required=True,
                    help="in-game edge length of one voxel, in metres")
    args = ap.parse_args()

    triangles = read_binary_stl(args.stl)
    xs = [v[0] for t in triangles for v in t]
    ys = [v[1] for t in triangles for v in t]
    zs = [v[2] for t in triangles for v in t]
    cell = max(max(xs) - min(xs), max(ys) - min(ys)) / args.cells

    top, width, depth = heightmap(triangles, cell)
    min_z = min(zs)

    voxels = []
    max_height = 0
    for (cx, cy), surface in top.items():
        block = args.relief_block if surface > args.relief_z else args.base_block
        layers = max(1, round((surface - min_z) / cell))
        max_height = max(max_height, layers)
        for layer in range(layers):
            # model x -> game z, model y -> game y, model z (thickness) -> game x
            voxels.append({"x": layer, "y": cy, "z": cx, "block": block})

    out = {"size": [max_height, depth, width], "voxel_metres": args.voxel_metres,
           "voxels": voxels}
    Path(args.out).write_text(json.dumps(out))
    print(f"{len(triangles):,} triangles -> {len(voxels):,} voxels, "
          f"grid {max_height}x{depth}x{width}")


if __name__ == "__main__":
    main()
