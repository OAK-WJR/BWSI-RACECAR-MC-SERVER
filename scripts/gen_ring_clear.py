#!/usr/bin/env python3
"""Remove the first ring track (radius 150) left in the hall.

Its clear function was overwritten when the track was regenerated from the
real map, so the blocks stayed. This rebuilds exactly the cells that track
touched and puts the hall's quartz floor and invisible light back, leaving
anything else in the hall alone.
"""
import math

R_MID, WIDTH = 150.0, 12.0
R_IN, R_OUT = R_MID - WIDTH / 2, R_MID + WIDTH / 2
Y_FLOOR, Y_STAND = -60, -59

out = []
lo2, hi2 = R_IN * R_IN, R_OUT * R_OUT

# road surface and the lantern dots that sat in it
for z in range(-int(R_OUT) - 1, int(R_OUT) + 2):
    run = None
    for x in range(-int(R_OUT) - 1, int(R_OUT) + 3):
        inside = lo2 <= x * x + z * z <= hi2
        if inside and run is None:
            run = x
        elif not inside and run is not None:
            out.append(f"fill {run} {Y_FLOOR} {z} {x - 1} {Y_FLOOR} {z} minecraft:smooth_quartz "
                       "replace minecraft:black_concrete")
            out.append(f"fill {run} {Y_FLOOR} {z} {x - 1} {Y_FLOOR} {z} minecraft:smooth_quartz "
                       "replace minecraft:sea_lantern")
            run = None

# kerbs
cells = set()
for a10 in range(0, 3600):
    t = math.radians(a10 / 10)
    for r in (R_IN - 0.6, R_OUT + 0.6):
        cells.add((round(r * math.cos(t)), round(r * math.sin(t))))
for x, z in sorted(cells):
    for colour in ("red_concrete", "white_concrete"):
        out.append(f"fill {x} {Y_STAND} {z} {x} {Y_STAND} {z} minecraft:light[level=15] "
                   f"replace minecraft:{colour}")

# start line and gate
for x in range(int(R_IN), int(R_OUT) + 1):
    for z in (-1, 0):
        for colour in ("white_concrete", "gray_concrete"):
            out.append(f"fill {x} {Y_FLOOR} {z} {x} {Y_FLOOR} {z} minecraft:smooth_quartz "
                       f"replace minecraft:{colour}")
for gx in (int(R_IN) - 1, int(R_OUT) + 1):
    out.append(f"fill {gx} {Y_STAND} 0 {gx} -53 0 minecraft:light[level=15] "
               "replace minecraft:quartz_pillar")
out.append(f"fill {int(R_IN) - 1} -52 0 {int(R_OUT) + 1} -52 0 minecraft:light[level=15] "
           "replace minecraft:smooth_quartz")
out.append(f"fill {(int(R_IN) - 1 + int(R_OUT) + 1) // 2} -53 0 "
           f"{(int(R_IN) - 1 + int(R_OUT) + 1) // 2} -53 0 minecraft:light[level=15] "
           "replace minecraft:sea_lantern")

path = ("/root/minecraft/data/BWSI Racecar/datapacks/lobby/data/bwsi/function/"
        "ring_clear.mcfunction")
open(path, "w").write("\n".join(out) + "\n")
print(f"{len(out)} commands -> bwsi:ring_clear")
