#!/usr/bin/env python3
"""Fill the hollow inside of a scanned voxel model.

The scan is a surface shell, so any pinhole in it looks straight through the
car to whatever is behind — which reads as white speckle against a light
background. Flood filling from outside the bounding box marks everything the
outside can reach; every empty cell left over is interior and gets filled
with the colour of the nearest shell cell.

    python3 scripts/fill_cavities.py in.json -o out.json
"""
import argparse
import json
from collections import deque
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("voxel_json")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    data = json.loads(Path(args.voxel_json).read_text())
    cells = {(v["x"], v["y"], v["z"]): v["block"] for v in data["voxels"]}
    xs = [p[0] for p in cells]
    ys = [p[1] for p in cells]
    zs = [p[2] for p in cells]
    lo = (min(xs) - 1, min(ys) - 1, min(zs) - 1)
    hi = (max(xs) + 1, max(ys) + 1, max(zs) + 1)

    # flood the empty space from a corner outside the model
    outside = set()
    queue = deque([lo])
    outside.add(lo)
    while queue:
        x, y, z = queue.popleft()
        for nxt in ((x + 1, y, z), (x - 1, y, z), (x, y + 1, z),
                    (x, y - 1, z), (x, y, z + 1), (x, y, z - 1)):
            if nxt in outside or nxt in cells:
                continue
            if not all(lo[i] <= nxt[i] <= hi[i] for i in range(3)):
                continue
            outside.add(nxt)
            queue.append(nxt)

    interior = []
    for x in range(lo[0], hi[0] + 1):
        for y in range(lo[1], hi[1] + 1):
            for z in range(lo[2], hi[2] + 1):
                if (x, y, z) not in cells and (x, y, z) not in outside:
                    interior.append((x, y, z))

    # give each interior cell the colour of the nearest shell cell above or
    # below it, so a pinhole shows bodywork rather than sky
    filled = 0
    for x, y, z in interior:
        colour = None
        for step in range(1, 40):
            for probe in ((x, y - step, z), (x, y + step, z),
                          (x - step, y, z), (x + step, y, z)):
                if probe in cells:
                    colour = cells[probe]
                    break
            if colour:
                break
        cells[(x, y, z)] = colour or "minecraft:black_concrete"
        filled += 1

    data["voxels"] = [{"x": x, "y": y, "z": z, "block": block}
                      for (x, y, z), block in sorted(cells.items())]
    Path(args.out).write_text(json.dumps(data))
    print(f"{filled:,} interior cells filled, {len(cells):,} total -> {args.out}")


if __name__ == "__main__":
    main()
