#!/usr/bin/env python3
"""Voxelise a textured glTF binary into coloured Minecraft blocks.

Surface voxelisation only: the mesh is a scan shell, and a car is hollow
anyway. Each triangle is sampled densely enough that no voxel is missed, and
its base colour texture is read at the triangle centroid, which is accurate
enough once a triangle is smaller than a voxel.
"""

import argparse
import io
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image

# Solid, full-cube blocks with their average texture colour. Restricted to
# blocks that read as a flat colour so nearest-match does not pick something
# that looks patterned in game.
PALETTE = {
    "minecraft:white_concrete": (207, 213, 214),
    "minecraft:light_gray_concrete": (125, 125, 115),
    "minecraft:gray_concrete": (54, 57, 61),
    "minecraft:black_concrete": (8, 10, 15),
    "minecraft:red_concrete": (142, 32, 32),
    "minecraft:orange_concrete": (224, 97, 0),
    "minecraft:yellow_concrete": (240, 175, 21),
    "minecraft:lime_concrete": (94, 168, 24),
    "minecraft:green_concrete": (73, 91, 36),
    "minecraft:cyan_concrete": (21, 119, 136),
    "minecraft:light_blue_concrete": (35, 137, 198),
    "minecraft:blue_concrete": (44, 46, 143),
    "minecraft:purple_concrete": (100, 31, 156),
    "minecraft:magenta_concrete": (169, 48, 159),
    "minecraft:pink_concrete": (213, 101, 142),
    "minecraft:brown_concrete": (96, 59, 31),
    "minecraft:white_wool": (233, 236, 236),
    "minecraft:iron_block": (220, 220, 220),
    "minecraft:gold_block": (246, 208, 61),
    "minecraft:redstone_block": (175, 24, 5),
    "minecraft:coal_block": (16, 15, 15),
    "minecraft:glass": (175, 213, 219),
}


def read_glb(path):
    data = Path(path).read_bytes()
    if data[:4] != b"glTF":
        raise SystemExit("not a glTF binary")
    offset = 12
    chunks = []
    while offset < len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        chunks.append((kind, data[offset + 8: offset + 8 + length]))
        offset += 8 + length + (-length % 4)
    gltf = json.loads(chunks[0][1])
    binary = next(c[1] for c in chunks if c[0] == 0x004E4942)
    return gltf, binary


_DTYPES = {5120: "i1", 5121: "u1", 5122: "i2", 5123: "u2", 5125: "u4", 5126: "f4"}
_COUNTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def accessor(gltf, binary, index):
    acc = gltf["accessors"][index]
    view = gltf["bufferViews"][acc["bufferView"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    count = acc["count"] * _COUNTS[acc["type"]]
    values = np.frombuffer(binary, dtype=_DTYPES[acc["componentType"]],
                           count=count, offset=start)
    return values.reshape(acc["count"], _COUNTS[acc["type"]])


def nearest_block(rgb, names, colours):
    return names[int(np.argmin(((colours - np.array(rgb)) ** 2).sum(axis=1)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glb")
    ap.add_argument("-o", "--out", required=True, help="output JSON of voxels")
    ap.add_argument("--resolution", type=int, default=40,
                    help="voxels along the longest axis")
    args = ap.parse_args()

    gltf, binary = read_glb(args.glb)
    primitive = gltf["meshes"][0]["primitives"][0]
    positions = accessor(gltf, binary, primitive["attributes"]["POSITION"]).astype(np.float64)
    uvs = accessor(gltf, binary, primitive["attributes"]["TEXCOORD_0"]).astype(np.float64)
    indices = accessor(gltf, binary, primitive["indices"]).reshape(-1, 3)

    image_index = gltf["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"]["index"]
    source = gltf["textures"][image_index]["source"]
    view = gltf["bufferViews"][gltf["images"][source]["bufferView"]]
    start = view.get("byteOffset", 0)
    texture = Image.open(io.BytesIO(binary[start:start + view["byteLength"]])).convert("RGB")
    tex = np.asarray(texture)
    print(f"mesh {len(positions):,} verts, {len(indices):,} tris, texture {texture.size[0]}x{texture.size[1]}")

    low = positions.min(axis=0)
    high = positions.max(axis=0)
    voxel = (high - low).max() / args.resolution
    print(f"model {np.round(high - low, 3)} units, voxel {voxel * 100:.2f} cm")

    names = list(PALETTE)
    colours = np.array([PALETTE[n] for n in names], dtype=np.float64)

    voxels = {}
    for tri in indices:
        p0, p1, p2 = positions[tri]
        centroid_uv = uvs[tri].mean(axis=0)
        tx = int(np.clip(centroid_uv[0], 0, 1) * (tex.shape[1] - 1))
        ty = int(np.clip(centroid_uv[1], 0, 1) * (tex.shape[0] - 1))
        rgb = tuple(int(v) for v in tex[ty, tx])

        # Sample the triangle finely enough that consecutive samples cannot
        # straddle a voxel without landing in it.
        longest = max(np.linalg.norm(p1 - p0), np.linalg.norm(p2 - p0), np.linalg.norm(p2 - p1))
        steps = max(2, int(np.ceil(longest / voxel * 2)) + 1)
        for i in range(steps + 1):
            for j in range(steps + 1 - i):
                u, v = i / steps, j / steps
                point = p0 + (p1 - p0) * u + (p2 - p0) * v
                key = tuple(int(c) for c in np.floor((point - low) / voxel))
                voxels.setdefault(key, []).append(rgb)

    out = []
    for (x, y, z), samples in voxels.items():
        mean = np.array(samples, dtype=np.float64).mean(axis=0)
        out.append({"x": x, "y": y, "z": z,
                    "rgb": [int(c) for c in mean],
                    "block": nearest_block(mean, names, colours)})

    size = [max(v[k] for v in out) + 1 for k in ("x", "y", "z")]
    Path(args.out).write_text(json.dumps({"size": size, "voxel_metres": voxel,
                                          "voxels": out}))
    counts = {}
    for v in out:
        counts[v["block"]] = counts.get(v["block"], 0) + 1
    print(f"{len(out):,} voxels, grid {size[0]}x{size[1]}x{size[2]}")
    for block, n in sorted(counts.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {n:6d}  {block}")


if __name__ == "__main__":
    main()
