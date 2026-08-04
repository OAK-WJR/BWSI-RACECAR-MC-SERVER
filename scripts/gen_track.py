#!/usr/bin/env python3
"""Build the Minecraft track from the simulator's map, and the metadata the
simulator and the replay both need.

The map is the real BWSI track as scanned by the car's lidar, so the track in
game is a scale replica of the one the simulator drives. Like the upstream
Unity pipeline, the course is start to finish along the corridor rather than
a lap: the finish is the point of the corridor geodesically furthest from the
start, and the centerline between them is the path through the middle.

Run it inside the sim image, which has the imaging dependencies:

    docker run --rm -v /root/minecraft:/mc -w /mc bwsi-race-sim \
        python scripts/gen_track.py

The lobby interior is filled with invisible minecraft:light blocks, so fills
here never use a replace filter: an unfiltered fill overwrites them, while a
"replace air" would miss them.
"""
import heapq
import json
import math
import os
import sys

import cv2
import numpy as np

ROOT = "/mc" if os.path.isdir("/mc/sim") else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "sim", "sim2d"))

from world import World

MAP = "sim2d/maps/repaired_track.yaml"
BLOCKS_PER_METRE = 8
Y_FLOOR = -60
Y_STAND = -59
WALL_HEIGHT = 3
MAX_TIME_S = 90
OFFSET_X = -100             # where the track sits in the hall
OFFSET_Z = -100
FINISH_RADIUS_M = 1.5      # how close to the start line counts as home
COARSE = 5                      # pathfinding cell = COARSE map pixels

world = World(os.path.join(ROOT, "sim", MAP))
res = world.resolution
H, W = world.occupancy.shape
sx, sy, sth = world.start_pose

# ---------------------------------------------------------------- the corridor
free = (~world.occupancy).astype(np.uint8)
count, labels = cv2.connectedComponents(free, connectivity=4)
srow, scol = H - 1 - int(sy / res), int(sx / res)
track_mask = (labels == labels[srow, scol]).astype(np.uint8)

# coarse grid for pathfinding: cheap and still far finer than the car
ch, cw = H // COARSE, W // COARSE
coarse = cv2.resize(track_mask, (cw, ch), interpolation=cv2.INTER_AREA) > 0.5
clearance = cv2.distanceTransform(coarse.astype(np.uint8), cv2.DIST_L2, 3) * COARSE * res

start_cell = (srow // COARSE, scol // COARSE)

def neighbours(cell):
    r, c = cell
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr or dc:
                nr, nc = r + dr, c + dc
                if 0 <= nr < ch and 0 <= nc < cw and coarse[nr, nc]:
                    yield (nr, nc), math.hypot(dr, dc)

def dijkstra(source, weight):
    dist = np.full((ch, cw), np.inf)
    prev = {}
    dist[source] = 0.0
    queue = [(0.0, source)]
    while queue:
        d, cell = heapq.heappop(queue)
        if d > dist[cell]:
            continue
        for nxt, step in neighbours(cell):
            nd = d + step * weight(nxt)
            if nd < dist[nxt]:
                dist[nxt] = nd
                prev[nxt] = cell
                heapq.heappush(queue, (nd, nxt))
    return dist, prev

# finish = furthest point of the corridor from the start, measured along it
plain, _ = dijkstra(start_cell, lambda cell: 1.0)
plain[~coarse] = -np.inf
finish_cell = np.unravel_index(np.argmax(np.where(np.isfinite(plain), plain, -np.inf)),
                               plain.shape)

# centerline = the same route, but pushed towards the middle of the corridor
middle, prev = dijkstra(start_cell, lambda cell: 1.0 + 1.0 / max(clearance[cell], 0.05))
path = [tuple(finish_cell)]
while path[-1] != start_cell:
    path.append(prev[path[-1]])
path.reverse()

def cell_to_metres(cell):
    r, c = cell
    return ((c + 0.5) * COARSE * res, (H - 1 - (r + 0.5) * COARSE) * res)

centerline = [cell_to_metres(cell) for cell in path[::4]]
finish_xy = cell_to_metres(tuple(finish_cell))
corridor_m = sum(math.dist(centerline[i], centerline[i + 1])
                 for i in range(len(centerline) - 1))

# ---------------------------------------------------------------- the build
scale = BLOCKS_PER_METRE
width_b = math.ceil(world.width_m * scale)
depth_b = math.ceil(world.height_m * scale)
origin_x = OFFSET_X - width_b // 2
origin_z = OFFSET_Z + depth_b // 2

build, clear = [], []

def emit(cmd_build, cmd_clear):
    build.append(cmd_build)
    clear.append(cmd_clear)

# Row-scan: runs of wall become wall, runs of corridor become asphalt. Free
# space outside the corridor keeps the hall's quartz floor.
for bz in range(depth_b):
    z = origin_z - bz
    run_start, run_kind = None, None
    for bx in range(width_b + 1):
        if bx < width_b:
            mx, my = (bx + 0.5) / scale, (bz + 0.5) / scale
            col, row = int(mx / res), H - 1 - int(my / res)
            if 0 <= row < H and 0 <= col < W:
                kind = "wall" if world.occupancy[row, col] else (
                    "road" if track_mask[row, col] else None)
            else:
                kind = None
        else:
            kind = "end"
        if kind != run_kind:
            if run_kind in ("wall", "road"):
                x1, x2 = origin_x + run_start, origin_x + bx - 1
                if run_kind == "wall":
                    emit(f"fill {x1} {Y_STAND} {z} {x2} {Y_STAND + WALL_HEIGHT - 1} {z} "
                         "minecraft:white_concrete",
                         f"fill {x1} {Y_STAND} {z} {x2} {Y_STAND + WALL_HEIGHT - 1} {z} "
                         "minecraft:light[level=15]")
                else:
                    emit(f"fill {x1} {Y_FLOOR} {z} {x2} {Y_FLOOR} {z} minecraft:black_concrete",
                         f"fill {x1} {Y_FLOOR} {z} {x2} {Y_FLOOR} {z} minecraft:smooth_quartz")
            run_start, run_kind = bx, kind

def to_blocks(x, y):
    return origin_x + x * scale, origin_z - y * scale

def paint_line(centre, direction, colour_a, colour_b):
    """A checker strip across the corridor, perpendicular to the direction."""
    px, pz = -direction[1], direction[0]
    cx, cz = to_blocks(*centre)
    for step in range(-int(1.4 * scale), int(1.4 * scale) + 1):
        for along in (0, 1):
            bx = round(cx + px * step + direction[0] * along)
            bz = round(cz + pz * step + direction[1] * along)
            colour = colour_a if (bx + bz) % 2 == 0 else colour_b
            emit(f"setblock {bx} {Y_FLOOR} {bz} minecraft:{colour}",
                 f"setblock {bx} {Y_FLOOR} {bz} minecraft:black_concrete")

def block_direction(a, b):
    ax, az = to_blocks(*a)
    bx, bz = to_blocks(*b)
    length = math.hypot(bx - ax, bz - az) or 1.0
    return ((bx - ax) / length, (bz - az) / length)

# one start/finish line: the course is a circuit of the corridor
paint_line(centerline[0], block_direction(centerline[0], centerline[3]),
           "white_concrete", "gray_concrete")

func_dir = os.path.join(ROOT, "data/BWSI Racecar/datapacks/lobby/data/bwsi/function")
os.makedirs(func_dir, exist_ok=True)
open(os.path.join(func_dir, "track.mcfunction"), "w").write("\n".join(build) + "\n")
open(os.path.join(func_dir, "track_clear.mcfunction"), "w").write("\n".join(clear) + "\n")

meta = {
    "map": MAP,
    "blocks_per_metre": scale,
    "origin_x": origin_x,
    "origin_z": origin_z,
    "max_time_s": MAX_TIME_S,
    "realism": False,
    "start_radius_m": FINISH_RADIUS_M,
    "min_travel_m": round(0.7 * corridor_m, 1),
    "corridor_m": round(corridor_m, 2),
    "centerline": [[round(x, 3), round(y, 3)] for x, y in centerline],
}
open(os.path.join(ROOT, "sim/track_meta.json"), "w").write(json.dumps(meta) + "\n")

start_mc_x, start_mc_z = to_blocks(sx, sy)
print(f"track {world.width_m:.2f}x{world.height_m:.2f} m -> {width_b}x{depth_b} blocks "
      f"at {scale} blocks/m")
print(f"corridor {corridor_m:.1f} m, lap needs {0.7 * corridor_m:.1f} m travelled")
print(f"{len(build)} build commands")
print("plugin config:")
print(f"start:\n  x: {start_mc_x:.1f}\n  y: {Y_STAND}.0\n  z: {start_mc_z:.1f}\n"
      f"  yaw: {-(math.degrees(sth) + 90):.1f}")
