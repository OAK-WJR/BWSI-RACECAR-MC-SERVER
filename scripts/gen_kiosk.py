#!/usr/bin/env python3
"""Build the submission desk beside the start line.

A quartz alcove: chest of blank books on the left, signs explaining the
rules on the right, and a pressure plate in the middle — stand on it holding
your code book and the run is queued. Prints the config block the Race
plugin needs.

    python3 scripts/gen_kiosk.py
    docker exec minecraft rcon-cli "minecraft:reload"
    docker exec minecraft rcon-cli "execute in minecraft:test run function bwsi:kiosk"
"""
import json
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FUNC_DIR = os.path.join(ROOT, "data/BWSI Racecar/datapacks/lobby/data/bwsi/function")

meta = json.load(open(os.path.join(ROOT, "sim/track_meta.json")))
# just outside the track's north-west corner, clear of the corridor
X = meta["origin_x"] - 8
Z = meta["origin_z"] - 8
Y = -60                     # floor; everything stands on Y + 1

out = []
def cmd(text):
    out.append(text)

def sign(x, z, rotation, lines):
    text = ",".join("'\"%s\"'" % line for line in lines)
    cmd(f"setblock {x} {Y + 1} {z} minecraft:oak_sign[rotation={rotation}]"
        f"{{front_text:{{messages:[{text}]}}}}")

# platform and a low wall behind it
cmd(f"fill {X - 4} {Y} {Z - 3} {X + 4} {Y} {Z + 1} minecraft:smooth_quartz")
cmd(f"fill {X - 4} {Y + 1} {Z - 3} {X + 4} {Y + 3} {Z - 3} minecraft:quartz_bricks")
cmd(f"fill {X - 4} {Y + 1} {Z - 2} {X - 4} {Y + 3} {Z + 1} minecraft:quartz_bricks")
cmd(f"fill {X + 4} {Y + 1} {Z - 2} {X + 4} {Y + 3} {Z + 1} minecraft:quartz_bricks")
cmd(f"fill {X - 4} {Y + 4} {Z - 3} {X + 4} {Y + 4} {Z + 1} minecraft:smooth_quartz")
cmd(f"setblock {X - 4} {Y + 4} {Z - 3} minecraft:sea_lantern")
cmd(f"setblock {X + 4} {Y + 4} {Z - 3} minecraft:sea_lantern")

# left: a chest of blank books, kept stocked by the plugin
cmd(f"setblock {X - 3} {Y + 1} {Z - 2} minecraft:chest[facing=south]")
sign(X - 3, Z - 1, 0, ["", "TAKE A BOOK", "write your code", "in it"])

# middle: the pressure plate that submits
cmd(f"setblock {X} {Y + 1} {Z} minecraft:polished_blackstone_pressure_plate")
cmd(f"fill {X - 1} {Y} {Z - 1} {X + 1} {Y} {Z + 1} minecraft:polished_blackstone")
cmd(f"setblock {X} {Y} {Z} minecraft:sea_lantern")
sign(X, Z - 2, 0, ["SUBMIT", "hold your book", "and stand", "on the plate"])

# right: what the rules are
sign(X + 2, Z - 2, 0, ["THE RULE", "one circuit of", "the track, back", "to the line"])
sign(X + 3, Z - 2, 0, ["CODE", "racecar_core", "rc.drive /", "rc.lidar"])
sign(X + 2, Z - 1, 0, ["", "/race top", "shows the", "ranking"])
sign(X + 3, Z - 1, 0, ["", "/race status", "shows your", "run"])

os.makedirs(FUNC_DIR, exist_ok=True)
open(os.path.join(FUNC_DIR, "kiosk.mcfunction"), "w").write("\n".join(out) + "\n")

print(f"{len(out)} commands -> bwsi:kiosk")
print("plugin config:")
print("kiosk:\n  enabled: true")
print(f"  plate: {{x: {X}, y: {Y + 1}, z: {Z}}}")
print(f"  chest: {{x: {X - 3}, y: {Y + 1}, z: {Z - 2}}}")
print("  books: 16")
