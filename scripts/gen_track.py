#!/usr/bin/env python3
"""Generate the ring circuit: the track in game, the map the simulator
drives, and the metadata that ties them together.

One geometry definition feeds all three, so what players see and what the
simulator drives can never drift apart. The circuit is centred on the hall
origin and raced counter-clockwise from the start line at its eastern point.

Run it inside the sim image, which has the imaging dependencies:

    docker run --rm -v /root/minecraft:/mc -w /mc bwsi-race-sim \
        python scripts/gen_track.py

The lobby interior is filled with invisible minecraft:light blocks, so fills
here never use a replace filter: an unfiltered fill overwrites them, while a
"replace air" would miss them.
"""
import json
import math
import os

import cv2
import numpy as np

ROOT = "/mc" if os.path.isdir("/mc/sim") else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")

BLOCKS_PER_METRE = 8
R_MID = 150.0               # blocks
WIDTH = 12.0                # blocks
R_IN, R_OUT = R_MID - WIDTH / 2, R_MID + WIDTH / 2
OFFSET_X, OFFSET_Z = 0, 0   # circuit centre in the hall
Y_FLOOR, Y_STAND = -60, -59
MAX_TIME_S = 150
START_RADIUS_M = 1.5
RESOLUTION = 0.04           # simulator map, metres per pixel; the raycast
                            # marches in half-pixel steps, so this is the
                            # single biggest lever on simulation time

FUNC_DIR = os.path.join(ROOT, "data/BWSI Racecar/datapacks/lobby/data/bwsi/function")
SIM_DIR = os.path.join(ROOT, "sim")

# Road is grey, not black: the car itself is black and would vanish into
# an asphalt-black surface when watched from the chase camera.
# ---------------------------------------------------------------- in game
build, clear = [], []

def both(cmd_build, cmd_clear):
    build.append(cmd_build)
    clear.append(cmd_clear)

lo2, hi2 = R_IN * R_IN, R_OUT * R_OUT
for z in range(-int(R_OUT) - 1, int(R_OUT) + 2):
    run = None
    for x in range(-int(R_OUT) - 1, int(R_OUT) + 3):
        inside = lo2 <= x * x + z * z <= hi2
        if inside and run is None:
            run = x
        elif not inside and run is not None:
            x1, x2, zz = run + OFFSET_X, x - 1 + OFFSET_X, z + OFFSET_Z
            both(f"fill {x1} {Y_FLOOR} {zz} {x2} {Y_FLOOR} {zz} minecraft:gray_concrete",
                 f"fill {x1} {Y_FLOOR} {zz} {x2} {Y_FLOOR} {zz} minecraft:smooth_quartz")
            run = None

# kerbs: alternating red and white, hugging both boundaries
kerb = {}
for a10 in range(3600):
    t = math.radians(a10 / 10)
    stripe = (a10 // 60) % 2
    for r in (R_IN - 0.6, R_OUT + 0.6):
        kerb[(round(r * math.cos(t)), round(r * math.sin(t)))] = stripe
for (x, z), stripe in sorted(kerb.items()):
    colour = "red_concrete" if stripe else "white_concrete"
    both(f"setblock {x + OFFSET_X} {Y_STAND} {z + OFFSET_Z} minecraft:{colour}",
         f"setblock {x + OFFSET_X} {Y_STAND} {z + OFFSET_Z} minecraft:light[level=15]")

# start line and gate at the eastern point
for x in range(int(R_IN), int(R_OUT) + 1):
    for z in (-1, 0):
        colour = "white_concrete" if (x + z) % 2 == 0 else "gray_concrete"
        both(f"setblock {x + OFFSET_X} {Y_FLOOR} {z + OFFSET_Z} minecraft:{colour}",
             f"setblock {x + OFFSET_X} {Y_FLOOR} {z + OFFSET_Z} minecraft:gray_concrete")
gate_in, gate_out = int(R_IN) - 1 + OFFSET_X, int(R_OUT) + 1 + OFFSET_X
for gx in (gate_in, gate_out):
    both(f"fill {gx} {Y_STAND} {OFFSET_Z} {gx} -53 {OFFSET_Z} minecraft:quartz_pillar",
         f"fill {gx} {Y_STAND} {OFFSET_Z} {gx} -53 {OFFSET_Z} minecraft:light[level=15]")
both(f"fill {gate_in} -52 {OFFSET_Z} {gate_out} -52 {OFFSET_Z} minecraft:smooth_quartz",
     f"fill {gate_in} -52 {OFFSET_Z} {gate_out} -52 {OFFSET_Z} minecraft:light[level=15]")
both(f"setblock {(gate_in + gate_out) // 2} -53 {OFFSET_Z} minecraft:sea_lantern",
     f"setblock {(gate_in + gate_out) // 2} -53 {OFFSET_Z} minecraft:light[level=15]")

os.makedirs(FUNC_DIR, exist_ok=True)
open(os.path.join(FUNC_DIR, "track.mcfunction"), "w").write("\n".join(build) + "\n")
open(os.path.join(FUNC_DIR, "track_clear.mcfunction"), "w").write("\n".join(clear) + "\n")

# ---------------------------------------------------------------- simulator map
scale = BLOCKS_PER_METRE
r_mid_m, r_in_m, r_out_m = R_MID / scale, R_IN / scale, R_OUT / scale
half_m = r_out_m + 1.0
size_px = int(round(2 * half_m / RESOLUTION))

# black = wall, white = free (ROS map convention, occupied_thresh 128)
image = np.zeros((size_px, size_px), np.uint8)
yy, xx = np.mgrid[0:size_px, 0:size_px]
x_m = (xx + 0.5) * RESOLUTION
y_m = (size_px - 1 - yy + 0.5) * RESOLUTION
radius = np.hypot(x_m - half_m, y_m - half_m)
image[(radius >= r_in_m) & (radius <= r_out_m)] = 255

maps_dir = os.path.join(SIM_DIR, "sim2d", "maps")
cv2.imwrite(os.path.join(maps_dir, "ring.png"), image)

# start on the eastern point, heading north: counter-clockwise
start_x_m, start_y_m = half_m + r_mid_m, half_m
open(os.path.join(maps_dir, "ring.yaml"), "w").write(
    "# ring circuit, generated by scripts/gen_track.py - do not edit\n"
    "image: ring.png\n"
    f"resolution: {RESOLUTION}\n"
    f"start_pose: [{start_x_m:.3f}, {start_y_m:.3f}, {math.pi / 2:.4f}]\n"
    "occupied_thresh: 128\n")

# ---------------------------------------------------------------- metadata
lap_m = 2 * math.pi * r_mid_m
# the simulator works in its own map metres; place that map's corner here
meta = {
    "map": "sim2d/maps/ring.yaml",
    "blocks_per_metre": scale,
    "origin_x": OFFSET_X - half_m * scale,
    "origin_z": OFFSET_Z + half_m * scale,
    "max_time_s": MAX_TIME_S,
    "realism": False,
    "start_radius_m": START_RADIUS_M,
    "min_travel_m": round(0.7 * lap_m, 1),
    "corridor_m": round(lap_m, 2),
}
open(os.path.join(SIM_DIR, "track_meta.json"), "w").write(json.dumps(meta) + "\n")

print(f"ring r={r_mid_m:.2f} m, width {WIDTH / scale:.2f} m, lap {lap_m:.1f} m")
print(f"sim map {size_px}x{size_px} px at {RESOLUTION} m/px")
print(f"{len(build)} build commands")
print("plugin config:")
print(f"start:\n  x: {R_MID + OFFSET_X + 0.5}\n  y: {Y_STAND}.0\n"
      f"  z: {OFFSET_Z + 0.5}\n  yaw: 0.0")
