#!/usr/bin/env python3
"""Close the gaps a surface scan leaves in a voxel model.

The scan is a shell about two cells thick, so wherever the scanner could not
see — under the chassis, inside wheel arches — the model has holes you can
look straight through. Filling each vertical column between its lowest and
highest solid cell closes them without touching the silhouette: nothing is
added outside what the shell already encloses.

    python3 scripts/solidify_voxels.py in.json -o out.json [--max-span 40]
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("voxel_json")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--max-span", type=int, default=40,
                    help="leave columns taller than this alone; they are the "
                         "gap between chassis and roof, not a hole")
    args = ap.parse_args()

    data = json.loads(Path(args.voxel_json).read_text())
    cells = {(v["x"], v["y"], v["z"]): v["block"] for v in data["voxels"]}

    columns = defaultdict(list)
    for x, y, z in cells:
        columns[(x, z)].append(y)

    added = 0
    for (x, z), heights in columns.items():
        heights.sort()
        for lower, upper in zip(heights, heights[1:]):
            span = upper - lower
            if span <= 1 or span > args.max_span:
                continue
            colour = cells[(x, lower, z)]
            for y in range(lower + 1, upper):
                cells[(x, y, z)] = colour
                added += 1

    data["voxels"] = [{"x": x, "y": y, "z": z, "block": block}
                      for (x, y, z), block in sorted(cells.items())]
    Path(args.out).write_text(json.dumps(data))
    print(f"{added:,} cells filled, {len(cells):,} total -> {args.out}")


if __name__ == "__main__":
    main()
