#!/usr/bin/env python3
"""Sponge .schem -> voxel JSON for voxels_to_parts.py (uses nbt_tools).

The Racecar plugin drives along +z (lengthMetres = size[2]); if the build
lies along x, the grid is rotated so the long horizontal axis becomes z.
voxel_metres is recomputed from the real object length.
"""
import argparse
import json
from pathlib import Path

import nbt_tools


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("schem")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--length-m", type=float, default=0.43,
                    help="real-world length of the object in metres")
    args = ap.parse_args()

    root, name, _ = nbt_tools.load(args.schem)
    if "Schematic" in root:
        root = root["Schematic"]
    W, H, L = int(root["Width"]) & 0xFFFF, int(root["Height"]) & 0xFFFF, int(root["Length"]) & 0xFFFF
    if "Blocks" in root:                       # sponge v3
        pal, data = root["Blocks"]["Palette"], bytes(root["Blocks"]["Data"])
    else:                                      # sponge v2
        pal, data = root["Palette"], bytes(root["BlockData"])
    names = {int(v): str(k) for k, v in pal.items()}
    print(f"schem {W}x{H}x{L}, palette {len(names)}")

    ids, i = [], 0
    while i < len(data):
        val = shift = 0
        while True:
            b = data[i]; i += 1
            val |= (b & 0x7F) << shift
            if not b & 0x80:
                break
            shift += 7
        ids.append(val)

    vox = []
    for idx, pid in enumerate(ids):
        n = names[pid].split("[")[0]
        if n == "minecraft:air":
            continue
        x = idx % W
        z = (idx // W) % L
        y = idx // (W * L)
        vox.append((x, y, z, n))

    if W > L:                                  # long axis -> z
        vox = [(z, y, W - 1 - x, n) for x, y, z, n in vox]
        W, L = L, W
        print("rotated 90deg so length runs along z")


    out = {"size": [W, H, L], "voxel_metres": args.length_m / L,
           "voxels": [{"x": x, "y": y, "z": z, "block": n} for x, y, z, n in vox]}
    Path(args.out).write_text(json.dumps(out))
    print(f"{len(vox):,} voxels, voxel_metres={args.length_m / L:.5f}")


if __name__ == "__main__":
    main()
