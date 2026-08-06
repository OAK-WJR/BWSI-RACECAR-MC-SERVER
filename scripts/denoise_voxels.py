#!/usr/bin/env python3
"""Smooth the speckle out of a scanned voxel model.

The scan sampled photographs, so highlights and overexposed edges landed as
single white or light-grey cells scattered across dark bodywork. Any cell
whose colour disagrees with most of its neighbours is replaced by the colour
those neighbours agree on; passes repeat until the model stops changing.

    python3 scripts/denoise_voxels.py in.json -o out.json [--passes 3]
"""
import argparse
import json
from collections import Counter
from pathlib import Path

NEIGHBOURS = [(dx, dy, dz)
              for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
              if (dx, dy, dz) != (0, 0, 0)]


def denoise(cells, threshold):
    """One pass. Returns the new grid and how many cells changed."""
    updated = dict(cells)
    changed = 0
    for (x, y, z), colour in cells.items():
        around = Counter()
        for dx, dy, dz in NEIGHBOURS:
            other = cells.get((x + dx, y + dy, z + dz))
            if other is not None:
                around[other] += 1
        if not around:
            continue
        winner, count = around.most_common(1)[0]
        if winner != colour and count >= threshold * sum(around.values()):
            updated[(x, y, z)] = winner
            changed += 1
    return updated, changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("voxel_json")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="share of neighbours that must agree to overrule a cell")
    args = ap.parse_args()

    data = json.loads(Path(args.voxel_json).read_text())
    cells = {(v["x"], v["y"], v["z"]): v["block"] for v in data["voxels"]}

    before = len(set(cells.values()))
    for step in range(args.passes):
        cells, changed = denoise(cells, args.threshold)
        print(f"pass {step + 1}: {changed:,} cells recoloured")
        if changed == 0:
            break

    data["voxels"] = [{"x": x, "y": y, "z": z, "block": block}
                      for (x, y, z), block in sorted(cells.items())]
    Path(args.out).write_text(json.dumps(data))
    print(f"{len(cells):,} cells, {before} colours in, "
          f"{len(set(cells.values()))} out -> {args.out}")


if __name__ == "__main__":
    main()
