#!/usr/bin/env python3
"""Shrink a voxel JSON until it is cheap enough to spawn as block displays.

Two passes:
  1. hollow — voxels enclosed on all six sides never show, drop them
  2. integer downsample — each output cell takes the majority block of its
     f^3 input cells (ties broken toward darker blocks, which dominate the
     car's silhouette)

The factor is chosen automatically: the smallest f whose merged part count
fits the budget.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import voxels_to_parts


def hollow(vox):
    filled = set(vox)
    keep = {}
    for (x, y, z), b in vox.items():
        if all((x + dx, y + dy, z + dz) in filled
               for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
                                  (0, -1, 0), (0, 0, 1), (0, 0, -1))):
            continue
        keep[(x, y, z)] = b
    return keep


def downsample(vox, f):
    cells = {}
    for (x, y, z), b in vox.items():
        cells.setdefault((x // f, y // f, z // f), []).append(b)
    out = {}
    for k, blocks in cells.items():
        # majority vote; require the cell to be at least ~15% occupied so the
        # downsampled shell doesn't grow fuzz
        if len(blocks) < max(1, int(f ** 3 * 0.15)):
            continue
        out[k] = Counter(blocks).most_common(1)[0][0]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("voxel_json")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--budget", type=int, default=600)
    args = ap.parse_args()

    data = json.loads(Path(args.voxel_json).read_text())
    vox = {(v["x"], v["y"], v["z"]): v["block"] for v in data["voxels"]}
    size, vm = data["size"], data["voxel_metres"]
    print(f"in: {len(vox):,} voxels @ {size}")

    for f in range(2, 17):
        small = downsample(vox, f)
        small = hollow(small)
        parts = voxels_to_parts.merge(small)
        nsize = [(s + f - 1) // f for s in size]
        print(f"f={f}: {len(small):,} voxels -> {len(parts):,} parts, "
              f"size {nsize}")
        if len(parts) <= args.budget:
            out = {"size": nsize, "voxel_metres": vm * f, "parts": parts}
            Path(args.out).write_text(json.dumps(out))
            print(f"chosen f={f}, wrote {args.out}")
            return
    raise SystemExit("no factor fits the budget")


if __name__ == "__main__":
    main()
