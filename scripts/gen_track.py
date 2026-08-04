#!/usr/bin/env python3
"""Generate the race track: build function, clear function, and sim/track.json.

One geometry definition feeds all three, so the visible track and the
simulator's track can never drift apart. Ring circuit centred 0,0 inside
the lobby box, raced counter-clockwise; the start sits at angle 0 where
the travel direction is exactly Minecraft yaw 0 (+z).

The lobby interior air is invisible minecraft:light blocks, so fills here
never use a "replace" filter: an unfiltered fill overwrites them, and a
filtered "replace air" would silently miss them.
"""
import json
import math
from pathlib import Path

R_MID = 150.0
WIDTH = 12.0
R_IN = R_MID - WIDTH / 2          # 144
R_OUT = R_MID + WIDTH / 2         # 156
Y_FLOOR = -60
Y_STAND = -59
MAX_TIME_S = 120

FUNC_DIR = Path("/root/minecraft/data/BWSI Racecar/datapacks/lobby/data/bwsi/function")
SIM_DIR = Path("/root/minecraft/sim")

build = []
clear = []

def both(cmd_build, cmd_clear):
    build.append(cmd_build)
    clear.append(cmd_clear)

# --- surface: recolour the quartz floor ring to asphalt ---
lo2, hi2 = R_IN * R_IN, R_OUT * R_OUT
for z in range(-int(R_OUT) - 1, int(R_OUT) + 2):
    spans = []
    run = None
    for x in range(-int(R_OUT) - 1, int(R_OUT) + 3):
        d2 = x * x + z * z
        inside = lo2 <= d2 <= hi2
        if inside and run is None:
            run = x
        elif not inside and run is not None:
            spans.append((run, x - 1))
            run = None
    for x1, x2 in spans:
        both(f"fill {x1} {Y_FLOOR} {z} {x2} {Y_FLOOR} {z} minecraft:black_concrete",
             f"fill {x1} {Y_FLOOR} {z} {x2} {Y_FLOOR} {z} minecraft:smooth_quartz")

# --- kerbs: alternating red/white cells hugging both boundaries ---
kerb_cells = {}
for a10 in range(0, 3600):
    t = math.radians(a10 / 10)
    stripe = (a10 // 60) % 2          # colour flips every 6 degrees
    for r in (R_IN - 0.6, R_OUT + 0.6):
        x, z = round(r * math.cos(t)), round(r * math.sin(t))
        kerb_cells[(x, z)] = stripe
for (x, z), stripe in sorted(kerb_cells.items()):
    colour = "red_concrete" if stripe else "white_concrete"
    both(f"setblock {x} {Y_STAND} {z} minecraft:{colour}",
         f"setblock {x} {Y_STAND} {z} minecraft:light[level=15]")

# --- start/finish: checker strip on the floor, gate overhead ---
for x in range(int(R_IN), int(R_OUT) + 1):
    for z in (-1, 0):
        colour = "white_concrete" if (x + z) % 2 == 0 else "gray_concrete"
        both(f"setblock {x} {Y_FLOOR} {z} minecraft:{colour}",
             f"setblock {x} {Y_FLOOR} {z} minecraft:black_concrete")
gx_in, gx_out = int(R_IN) - 1, int(R_OUT) + 1
for gx in (gx_in, gx_out):
    both(f"fill {gx} {Y_STAND} 0 {gx} -53 0 minecraft:quartz_pillar",
         f"fill {gx} {Y_STAND} 0 {gx} -53 0 minecraft:light[level=15]")
both(f"fill {gx_in} -52 0 {gx_out} -52 0 minecraft:smooth_quartz",
     f"fill {gx_in} -52 0 {gx_out} -52 0 minecraft:light[level=15]")
both(f"setblock {(gx_in + gx_out) // 2} -53 0 minecraft:sea_lantern",
     f"setblock {(gx_in + gx_out) // 2} -53 0 minecraft:light[level=15]")

FUNC_DIR.mkdir(parents=True, exist_ok=True)
(FUNC_DIR / "track.mcfunction").write_text("\n".join(build) + "\n")
(FUNC_DIR / "track_clear.mcfunction").write_text("\n".join(clear) + "\n")

# --- sim/track.json: same geometry for the simulator ---
centerline = []
steps = int(2 * math.pi * R_MID / 2)      # ~one point per 2 blocks
for i in range(steps):
    t = 2 * math.pi * i / steps
    centerline.append([round(R_MID * math.cos(t), 2), round(R_MID * math.sin(t), 2)])

track = {
    "name": "ring-150",
    "track_width": WIDTH,
    "start": {"x": 150.5, "z": 0.5, "yaw_deg": 0.0},
    "finish_line": [[R_IN, 0.5], [R_OUT, 0.5]],
    "centerline": centerline,
    "max_time_s": MAX_TIME_S,
}
SIM_DIR.mkdir(parents=True, exist_ok=True)
(SIM_DIR / "track.json").write_text(json.dumps(track) + "\n")

print(f"track.mcfunction: {len(build)} commands, track_clear: {len(clear)}")
print(f"sim/track.json: {steps} centerline points")
print("plugin config start block:")
print(f"start:\n  x: 150.5\n  y: {Y_STAND}.0\n  z: 0.5\n  yaw: 0.0")
