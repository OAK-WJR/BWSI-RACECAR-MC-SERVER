#!/usr/bin/env python3
"""Voxelise the scanned GLB straight into Minecraft blocks, with the colour
error kept as small as the block palette allows.

Three things matter for that, and the earlier pass got all three wrong:

  * every texture pixel that lands in a voxel is averaged, rather than one
    point being sampled — a single sample lands on a specular highlight and
    turns a black panel into a white speck
  * the match runs in CIELAB, where distance means what the eye means, not
    in RGB where dark browns and dark greys are neighbours
  * the palette holds every solid colour block, not the couple of dozen the
    old table listed

Runs inside the sim image (numpy, opencv).

    python3 voxelize_glb_lab.py model.glb -o voxels.json --grid 193
"""
import argparse
import json
import math
import struct

import cv2
import numpy as np

# Average colours of the solid colour blocks, sRGB. Concrete is flat, wool is
# slightly lighter, terracotta is muted and warm — together they cover the
# space well enough that nothing has to travel far.
PALETTE = {
    "white_concrete": (207, 213, 214), "orange_concrete": (224, 97, 0),
    "magenta_concrete": (169, 48, 159), "light_blue_concrete": (36, 137, 199),
    "yellow_concrete": (241, 175, 21), "lime_concrete": (94, 168, 24),
    "pink_concrete": (214, 101, 143), "gray_concrete": (54, 57, 61),
    "light_gray_concrete": (125, 125, 115), "cyan_concrete": (21, 119, 136),
    "purple_concrete": (100, 32, 156), "blue_concrete": (44, 46, 143),
    "brown_concrete": (96, 59, 31), "green_concrete": (73, 91, 36),
    "red_concrete": (142, 33, 33), "black_concrete": (8, 10, 15),
    "white_wool": (233, 236, 236), "orange_wool": (240, 118, 19),
    "magenta_wool": (189, 68, 179), "light_blue_wool": (58, 175, 217),
    "yellow_wool": (248, 198, 39), "lime_wool": (112, 185, 25),
    "pink_wool": (237, 141, 172), "gray_wool": (62, 68, 71),
    "light_gray_wool": (142, 142, 134), "cyan_wool": (21, 137, 145),
    "purple_wool": (121, 42, 172), "blue_wool": (53, 57, 157),
    "brown_wool": (114, 71, 40), "green_wool": (84, 109, 27),
    "red_wool": (160, 39, 34), "black_wool": (20, 21, 25),
    "white_terracotta": (209, 178, 161), "orange_terracotta": (161, 83, 37),
    "magenta_terracotta": (149, 88, 108), "light_blue_terracotta": (113, 108, 137),
    "yellow_terracotta": (186, 133, 35), "lime_terracotta": (103, 117, 52),
    "pink_terracotta": (161, 78, 78), "gray_terracotta": (57, 42, 35),
    "light_gray_terracotta": (135, 106, 97), "cyan_terracotta": (86, 91, 91),
    "purple_terracotta": (118, 70, 86), "blue_terracotta": (74, 59, 91),
    "brown_terracotta": (77, 51, 35), "green_terracotta": (76, 83, 42),
    "red_terracotta": (143, 61, 46), "black_terracotta": (37, 22, 16),
    "coal_block": (16, 15, 15), "smooth_stone": (158, 158, 158),
    "stone": (125, 125, 125), "deepslate": (77, 77, 80),
    "iron_block": (220, 220, 220), "polished_andesite": (132, 134, 133),
}


def lab(rgb):
    """sRGB 0-255 to CIELAB, via opencv so the maths is somebody else's."""
    arr = np.asarray(rgb, np.float32).reshape(-1, 1, 3) / 255.0
    return cv2.cvtColor(arr[:, :, ::-1], cv2.COLOR_RGB2LAB).reshape(-1, 3)


def load_glb(path):
    data = open(path, "rb").read()
    _, _, length = struct.unpack("<III", data[:12])
    off, chunks = 12, []
    while off < length:
        clen, ctype = struct.unpack("<II", data[off:off + 8])
        chunks.append((ctype, off + 8, clen))
        off += 8 + clen
    js = [c for c in chunks if c[0] == 0x4E4F534A][0]
    bn = [c for c in chunks if c[0] == 0x004E4942][0]
    return json.loads(data[js[1]:js[1] + js[2]]), data[bn[1]:bn[1] + bn[2]]


def accessor(gltf, binary, index):
    acc = gltf["accessors"][index]
    view = gltf["bufferViews"][acc["bufferView"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    kinds = {5126: "<f4", 5125: "<u4", 5123: "<u2", 5121: "<u1"}
    counts = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[acc["type"]]
    dtype = np.dtype(kinds[acc["componentType"]])
    raw = binary[start:start + acc["count"] * counts * dtype.itemsize]
    return np.frombuffer(raw, dtype=dtype).reshape(acc["count"], counts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glb")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--grid", type=int, default=193,
                    help="cells along the longest axis")
    args = ap.parse_args()

    gltf, binary = load_glb(args.glb)
    prim = gltf["meshes"][0]["primitives"][0]
    pos = accessor(gltf, binary, prim["attributes"]["POSITION"]).astype(np.float64)
    uv = accessor(gltf, binary, prim["attributes"]["TEXCOORD_0"]).astype(np.float64)
    idx = accessor(gltf, binary, prim["indices"]).reshape(-1, 3)

    view = gltf["bufferViews"][gltf["images"][0]["bufferView"]]
    blob = binary[view.get("byteOffset", 0):view.get("byteOffset", 0) + view["byteLength"]]
    tex = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)[:, :, ::-1]
    th, tw = tex.shape[:2]

    # The raw scan is not square to its own axes: yaw it so the long axis of
    # the car runs along z, or the grid ends up 11 cm wider than the car and
    # every voxel column cuts the bodywork on a diagonal.
    flat = pos[:, [0, 2]] - pos[:, [0, 2]].mean(0)
    _, _, vh = np.linalg.svd(flat, full_matrices=False)
    long_axis = vh[0]
    angle = math.atan2(long_axis[0], long_axis[1])
    cos_a, sin_a = math.cos(-angle), math.sin(-angle)
    turned = pos.copy()
    turned[:, 0] = pos[:, 0] * cos_a - pos[:, 2] * sin_a
    turned[:, 2] = pos[:, 0] * sin_a + pos[:, 2] * cos_a
    pos = turned
    print(f"levelled: turned {math.degrees(angle):+.1f} deg about the vertical",
          flush=True)

    lo, hi = pos.min(0), pos.max(0)
    pitch = (hi - lo).max() / args.grid
    print(f"{len(idx):,} triangles, texture {tw}x{th}, pitch {pitch * 1000:.3f} mm",
          flush=True)

    # Every triangle is sampled densely enough that no cell it crosses is
    # missed, and every sample contributes its texture colour to that cell.
    sums = {}
    for tri in idx:
        p = pos[tri]
        t = uv[tri]
        edge = max(np.linalg.norm(p[1] - p[0]), np.linalg.norm(p[2] - p[0]),
                   np.linalg.norm(p[2] - p[1]))
        steps = max(2, int(edge / (pitch * 0.4)) + 1)
        for i in range(steps + 1):
            for j in range(steps + 1 - i):
                a = i / steps
                b = j / steps
                c = 1.0 - a - b
                point = p[0] * a + p[1] * b + p[2] * c
                texel = t[0] * a + t[1] * b + t[2] * c
                cell = tuple(((point - lo) / pitch).astype(np.int32))
                x = min(tw - 1, max(0, int(texel[0] * tw)))
                y = min(th - 1, max(0, int(texel[1] * th)))
                acc = sums.get(cell)
                colour = tex[y, x].astype(np.float64)
                if acc is None:
                    sums[cell] = [colour, 1]
                else:
                    acc[0] += colour
                    acc[1] += 1

    print(f"{len(sums):,} cells with samples", flush=True)

    names = list(PALETTE)
    palette_lab = lab([PALETTE[n] for n in names])
    cells = sorted(sums)
    averages = np.array([sums[c][0] / sums[c][1] for c in cells])
    sample_lab = lab(averages)
    # nearest palette entry per cell, in Lab
    diff = sample_lab[:, None, :] - palette_lab[None, :, :]
    best = np.argmin((diff ** 2).sum(axis=2), axis=1)
    error = np.sqrt((diff ** 2).sum(axis=2)).min(axis=1)
    print(f"mean Lab error {error.mean():.2f}, p95 {np.percentile(error, 95):.2f}",
          flush=True)

    size = [int((hi[i] - lo[i]) / pitch) + 1 for i in range(3)]
    out = {"size": size, "voxel_metres": float(pitch),
           "voxels": [{"x": int(c[0]), "y": int(c[1]), "z": int(c[2]),
                       "block": "minecraft:" + names[best[k]]}
                      for k, c in enumerate(cells)]}
    json.dump(out, open(args.out, "w"))
    print(f"{len(cells):,} voxels, grid {size} -> {args.out}")


if __name__ == "__main__":
    main()
