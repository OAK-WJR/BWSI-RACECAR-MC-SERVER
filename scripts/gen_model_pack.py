#!/usr/bin/env python3
"""Turn the voxel car into one custom item model, packed as a resource pack.

A block display shows one block state, so a voxel car costs one entity per
cuboid — 2481 of them. A resource pack can carry the whole car as a single
item model instead, which the server then shows with one item display: three
orders of magnitude fewer entities, and the model is no longer tied to the
block grid.

    python3 scripts/gen_model_pack.py

Writes pack/bwsi-racecar.zip and prints the SHA-1 the server must send with
it. Players are asked to accept the pack when they join.
"""
import hashlib
import json
import os
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MODEL_JSON = os.path.join(ROOT, "plugins-src/race/src/main/resources/car.json")
OUT_DIR = os.path.join(ROOT, "pack")
OUT_ZIP = os.path.join(OUT_DIR, "bwsi-racecar.zip")

# Resource packs measure in sixteenths of a block and every coordinate must
# stay within -16..32, so the whole car has to fit three blocks.
UNITS_PER_BLOCK = 16
LIMIT_LO, LIMIT_HI = -16.0, 32.0
PACK_FORMAT = 46          # 1.21.4+; newer clients accept it with a notice

car = json.load(open(MODEL_JSON))
size = car["size"]
span = max(size)
unit = (LIMIT_HI - LIMIT_LO) / span          # model units per voxel

# centre the car on the block's middle, wheels on the floor
offset_x = 8.0 - size[0] * unit / 2
offset_y = 0.0
offset_z = 8.0 - size[2] * unit / 2

# Rebuild the voxel grid so faces buried against a neighbour can be dropped:
# every cuboid drawing all six faces would triple the geometry for nothing.
filled = set()
for part in car["parts"]:
    for dx in range(part["w"]):
        for dy in range(part["h"]):
            for dz in range(part["d"]):
                filled.add((part["x"] + dx, part["y"] + dy, part["z"] + dz))

SIDES = {
    "west":  ((-1, 0, 0), "x"), "east": ((1, 0, 0), "x"),
    "down":  ((0, -1, 0), "y"), "up":   ((0, 1, 0), "y"),
    "north": ((0, 0, -1), "z"), "south": ((0, 0, 1), "z"),
}

def visible(part, side):
    """True unless every cell of this face touches another filled cell."""
    (dx, dy, dz), axis = SIDES[side]
    xs = [part["x"] - 1] if dx < 0 else [part["x"] + part["w"]] if dx > 0 else \
         range(part["x"], part["x"] + part["w"])
    ys = [part["y"] - 1] if dy < 0 else [part["y"] + part["h"]] if dy > 0 else \
         range(part["y"], part["y"] + part["h"])
    zs = [part["z"] - 1] if dz < 0 else [part["z"] + part["d"]] if dz > 0 else \
         range(part["z"], part["z"] + part["d"])
    for x in xs:
        for y in ys:
            for z in zs:
                if (x, y, z) not in filled:
                    return True
    return False

textures = {}
elements = []
hidden = 0
for part in car["parts"]:
    block = part["block"].removeprefix("minecraft:")
    textures.setdefault(block, f"minecraft:block/{block}")
    x0 = offset_x + part["x"] * unit
    y0 = offset_y + part["y"] * unit
    z0 = offset_z + part["z"] * unit
    x1 = x0 + part["w"] * unit
    y1 = y0 + part["h"] * unit
    z1 = z0 + part["d"] * unit
    faces = {}
    for side in SIDES:
        if visible(part, side):
            faces[side] = {"texture": f"#{block}", "uv": [0, 0, 16, 16]}
        else:
            hidden += 1
    if not faces:
        continue
    elements.append({
        "from": [round(x0, 4), round(y0, 4), round(z0, 4)],
        "to": [round(x1, 4), round(y1, 4), round(z1, 4)],
        "faces": faces,
    })

for element in elements:
    for value in element["from"] + element["to"]:
        if not LIMIT_LO - 0.001 <= value <= LIMIT_HI + 0.001:
            raise SystemExit(f"element outside the allowed model space: {value}")

model = {
    "textures": textures,
    "elements": elements,
    "display": {
        # the item display entity uses the "head" slot transform
        "head": {"rotation": [0, 0, 0], "translation": [0, 0, 0], "scale": [1, 1, 1]}
    },
}

item_definition = {
    "model": {"type": "minecraft:model", "model": "bwsi:racecar"}
}

os.makedirs(OUT_DIR, exist_ok=True)
with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as pack:
    pack.writestr("pack.mcmeta", json.dumps({
        "pack": {"pack_format": PACK_FORMAT,
                 "description": "BWSI Racecar model"}}, indent=2))
    pack.writestr("assets/bwsi/models/racecar.json", json.dumps(model))
    pack.writestr("assets/bwsi/items/racecar.json", json.dumps(item_definition, indent=2))

digest = hashlib.sha1(open(OUT_ZIP, "rb").read()).hexdigest()
open(os.path.join(OUT_DIR, "sha1.txt"), "w").write(digest + "\n")

print(f"{len(elements)} elements, {len(textures)} textures, "
      f"{hidden} buried faces dropped")
print(f"{OUT_ZIP}: {os.path.getsize(OUT_ZIP) / 1024:.0f} KiB")
print(f"sha1: {digest}")
