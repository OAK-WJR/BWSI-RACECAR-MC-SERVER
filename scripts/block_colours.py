#!/usr/bin/env python3
"""Work out every block's average colour from the game's own textures.

Hand-written colour tables are always missing something and always slightly
wrong. The client jar has the real textures, so the table is derived: for
each block texture, average the opaque pixels. Blocks whose look comes from
several textures (a log's side and end) keep the one named after the block.

    python3 scripts/block_colours.py client.jar -o scripts/block_colours.json

Runs inside the sim image, which has opencv for the PNG decoding.
"""
import argparse
import json
import zipfile

import cv2
import numpy as np

# textures that describe something other than a solid block face
SKIP = ("_overlay", "_stage", "_top_", "_side_", "destroy_", "_front_on",
        "_flow", "_still", "water_", "lava_", "fire_", "nether_portal")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jar")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    colours = {}
    with zipfile.ZipFile(args.jar) as jar:
        names = [n for n in jar.namelist()
                 if n.startswith("assets/minecraft/textures/block/")
                 and n.endswith(".png")]
        for name in names:
            stem = name.rsplit("/", 1)[1][:-4]
            if any(bad in stem for bad in SKIP):
                continue
            image = cv2.imdecode(np.frombuffer(jar.read(name), np.uint8),
                                 cv2.IMREAD_UNCHANGED)
            if image is None:
                continue
            if image.ndim == 2:                      # greyscale textures
                image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            if image.shape[2] == 4:
                opaque = image[:, :, 3] > 128
                if not opaque.any():
                    continue
                pixels = image[:, :, :3][opaque]
            else:
                pixels = image[:, :, :3].reshape(-1, 3)
            bgr = pixels.reshape(-1, 3).mean(axis=0)
            colours[stem] = [int(round(bgr[2])), int(round(bgr[1])), int(round(bgr[0]))]

    # A block's own texture wins. Otherwise take its "_top"/"_side" variant,
    # and accept that some blocks are named for a texture that drops the
    # "_block" (snow_block is drawn with snow.png).
    resolved = dict(colours)
    for stem, value in colours.items():
        for suffix in ("_top", "_side", "_front", "_bottom"):
            if stem.endswith(suffix):
                resolved.setdefault(stem[: -len(suffix)], value)
    for stem, value in list(resolved.items()):
        resolved.setdefault(stem + "_block", value)

    json.dump(dict(sorted(resolved.items())), open(args.out, "w"), indent=0)
    print(f"{len(resolved)} block colours -> {args.out}")


if __name__ == "__main__":
    main()
