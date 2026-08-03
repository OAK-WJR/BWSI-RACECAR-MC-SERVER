#!/usr/bin/env python3
"""Turn an MIT Stata Center floor plan into a WorldEdit schematic.

Source data: https://projects.csail.mit.edu/stata/ (CC BY 3.0), the "floorplans"
XML of the MIT Stata Center Data Set. Each file holds one floor as a set of
`space` polygons carrying the real MIT room number and a room-type code, plus
`portal` elements marking the doorways between them.

Coordinates in the XML are NAD27 Massachusetts Mainland State Plane (EPSG:26786),
identified by reprojecting the floor 1 centroid and landing on the Stata Center.
Going through pyproj rather than scaling the raw feet matters: OSM is WGS84, and
skipping the NAD27 datum shift puts the floor plans 35 m east of the building.
All floors share one origin so they stack and line up with the rest of campus.

A portal's `edge index` is local to the contour of the element that owns it, and
`param` (or the midpoint of `minparam`/`maxparam`) locates the door along that
edge. Verified against floor 32-1: all 256 doorways land on the target room's
boundary, median error 0.00 ft.
"""

import argparse
import gzip
import math
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

from pyproj import Transformer

SOURCE_CRS = "EPSG:26786"  # NAD27 / Massachusetts Mainland

# Origin: centroid of the floor 1 outline. Every floor and every other campus
# building must use this same origin or the pieces will not line up.
ORIGIN_X_FT = 710545.123773
ORIGIN_Y_FT = 496378.473009

_TO_WGS84 = Transformer.from_crs(SOURCE_CRS, "EPSG:4326", always_xy=True)
ORIGIN_LON, ORIGIN_LAT = _TO_WGS84.transform(ORIGIN_X_FT, ORIGIN_Y_FT)

FLOOR_HEIGHT = 5  # blocks per storey: y=0 is the slab, y=1..4 are the walls
DATA_VERSION = 4790  # Minecraft 26.1.2

WALL = "minecraft:white_concrete"
DEFAULT_FLOOR = "minecraft:smooth_stone"
FLOOR_BY_TYPE = {
    "CORR": "minecraft:light_gray_concrete",   # corridor
    "LAV": "minecraft:cyan_terracotta",        # lavatory
    "STRS": "minecraft:polished_andesite",     # stairs
    "ELEV": "minecraft:polished_andesite",     # elevator
    "OFF": "minecraft:oak_planks",             # office
    "CLASS": "minecraft:spruce_planks",        # classroom
    "LAB": "minecraft:light_blue_concrete",    # lab
}

DOOR_HALF_RADIUS = 1  # blocks either side of the portal point


# --------------------------------------------------------------------------
# NBT writing (just enough of the format to emit a Sponge schematic v2)
# --------------------------------------------------------------------------

def _tag(tag_id, name):
    n = name.encode()
    return bytes([tag_id]) + struct.pack(">H", len(n)) + n


def nbt_int(name, v):
    return _tag(3, name) + struct.pack(">i", v)


def nbt_short(name, v):
    return _tag(2, name) + struct.pack(">h", v)


def nbt_string(name, v):
    b = v.encode()
    return _tag(8, name) + struct.pack(">H", len(b)) + b


def nbt_byte_array(name, data):
    return _tag(7, name) + struct.pack(">i", len(data)) + bytes(data)


def nbt_compound(name, body):
    return _tag(10, name) + body + b"\x00"


def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


# --------------------------------------------------------------------------
# Floor plan parsing
# --------------------------------------------------------------------------

def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def contour_points(el):
    c = el.find("contour")
    if c is None:
        return []
    return [(float(p.get("x")), float(p.get("y")))
            for p in c.findall("point") if p.get("x") is not None]


def portal_points(el, points):
    """Locate this element's doorways on its own contour."""
    out = []
    for portal in el.findall("portal"):
        edge = portal.find("edge")
        if edge is None:
            continue
        idx = _num(edge.get("index"))
        if idx is None or int(idx) >= len(points):
            continue
        idx = int(idx)
        param = _num(edge.get("param"))
        if param is None:
            lo = _num(edge.get("minparam"))
            hi = _num(edge.get("maxparam"))
            param = ((lo if lo is not None else 0.0) + (hi if hi is not None else 1.0)) / 2
        param = max(0.0, min(1.0, param))
        a, b = points[idx], points[(idx + 1) % len(points)]
        out.append((a[0] + (b[0] - a[0]) * param, a[1] + (b[1] - a[1]) * param))
    return out


# --------------------------------------------------------------------------
# Rasterising
# --------------------------------------------------------------------------

def to_block(x_ft, y_ft):
    """State plane -> block coordinates, 1 block = 1 m. North is -Z.

    Projected via WGS84 so that these blocks share a frame with the OSM-derived
    buildings around Stata.
    """
    lon, lat = _TO_WGS84.transform(x_ft, y_ft)
    metres_per_deg_lon = 111320 * math.cos(math.radians(ORIGIN_LAT))
    return (round((lon - ORIGIN_LON) * metres_per_deg_lon),
            round(-(lat - ORIGIN_LAT) * 110574))


def line_cells(a, b):
    """Every block a wall segment passes through."""
    x0, z0 = a
    x1, z1 = b
    steps = max(abs(x1 - x0), abs(z1 - z0))
    if steps == 0:
        return {(x0, z0)}
    return {(round(x0 + (x1 - x0) * i / steps), round(z0 + (z1 - z0) * i / steps))
            for i in range(steps + 1)}


def polygon_cells(points):
    """Block columns inside a polygon, by scanline."""
    if len(points) < 3:
        return set()
    zs = [p[1] for p in points]
    cells = set()
    for z in range(min(zs), max(zs) + 1):
        xs = []
        for i in range(len(points)):
            (x0, z0), (x1, z1) = points[i], points[(i + 1) % len(points)]
            if (z0 <= z < z1) or (z1 <= z < z0):
                xs.append(x0 + (x1 - x0) * (z - z0) / (z1 - z0))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            for x in range(math.ceil(xs[i]), math.floor(xs[i + 1]) + 1):
                cells.add((x, z))
    return cells


def build_floor(path):
    root = ET.parse(path).getroot()
    floor_el = root.find("floor")
    spaces = root.findall(".//space")

    outline = [to_block(*p) for p in contour_points(floor_el)] if floor_el is not None else []

    walls, doors = set(), set()
    rooms = []
    for sp in spaces:
        pts_ft = contour_points(sp)
        if len(pts_ft) < 3:
            continue
        pts = [to_block(*p) for p in pts_ft]
        for i in range(len(pts)):
            walls |= line_cells(pts[i], pts[(i + 1) % len(pts)])
        rooms.append((sp.get("name"), (sp.get("type") or "").split("/")[0], pts))

    # Doorways are carved after every wall is drawn, so a door is never
    # re-filled by the neighbouring room's wall.
    for el in list(spaces) + ([floor_el] if floor_el is not None else []):
        pts_ft = contour_points(el)
        if len(pts_ft) < 3:
            continue
        for dx_ft, dy_ft in portal_points(el, pts_ft):
            cx, cz = to_block(dx_ft, dy_ft)
            r = DOOR_HALF_RADIUS
            for x in range(cx - r, cx + r + 1):
                for z in range(cz - r, cz + r + 1):
                    doors.add((x, z))

    return outline, walls, doors, rooms


def build_grid(outline, walls, doors, rooms):
    """Block layout for one storey, keyed by (x, y, z) with y=0 at the slab."""
    grid = {}
    for name, rtype, pts in rooms:
        block = FLOOR_BY_TYPE.get(rtype, DEFAULT_FLOOR)
        for cell in polygon_cells(pts):
            grid[(cell[0], 0, cell[1])] = block
    for cell in outline:
        grid[(cell[0], 0, cell[1])] = DEFAULT_FLOOR
    for cell in walls:
        grid[(cell[0], 0, cell[1])] = grid.get((cell[0], 0, cell[1]), DEFAULT_FLOOR)
        for y in range(1, FLOOR_HEIGHT):
            grid[(cell[0], y, cell[1])] = WALL
    for cell in doors:
        for y in range(1, FLOOR_HEIGHT - 1):  # leave a lintel on top
            grid.pop((cell[0], y, cell[1]), None)
    return grid


def write_schematic(path, grid):
    min_x = min(k[0] for k in grid)
    max_x = max(k[0] for k in grid)
    min_z = min(k[2] for k in grid)
    max_z = max(k[2] for k in grid)
    width = max_x - min_x + 1
    length = max_z - min_z + 1

    palette = {"minecraft:air": 0}
    for block in grid.values():
        palette.setdefault(block, len(palette))

    data = bytearray()
    for y in range(FLOOR_HEIGHT):
        for z in range(min_z, max_z + 1):
            for x in range(min_x, max_x + 1):
                data += varint(palette.get(grid.get((x, y, z), "minecraft:air"), 0))

    body = b"".join([
        nbt_int("Version", 2),
        nbt_int("DataVersion", DATA_VERSION),
        nbt_short("Width", width),
        nbt_short("Height", FLOOR_HEIGHT),
        nbt_short("Length", length),
        nbt_compound("Palette", b"".join(nbt_int(k, v) for k, v in palette.items())),
        nbt_int("PaletteMax", len(palette)),
        nbt_byte_array("BlockData", data),
    ])
    Path(path).write_bytes(gzip.compress(nbt_compound("Schematic", body)))
    return width, length, len(palette), (min_x, min_z)


def write_mcfunction(path, grid, base_y, world):
    """Emit setblock lines so a floor can be placed without anyone in-game."""
    lines = [f"setblock {x} {base_y + y} {z} {block}"
             for (x, y, z), block in sorted(grid.items())]
    Path(path).write_text("\n".join(lines) + "\n")
    return len(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xml", help="floor plan, e.g. campus-data/floorplans/32-1.xml")
    ap.add_argument("-o", "--out", help="output .schem for builders using WorldEdit")
    ap.add_argument("--mcfunction", help="output .mcfunction for server-side placement")
    ap.add_argument("--base-y", type=int, default=64, help="world Y of this storey's slab")
    ap.add_argument("--world", default="minecraft:campus")
    args = ap.parse_args()
    if not args.out and not args.mcfunction:
        ap.error("give --out and/or --mcfunction")

    outline, walls, doors, rooms = build_floor(args.xml)
    grid = build_grid(outline, walls, doors, rooms)
    if not grid:
        raise SystemExit("floor plan produced no blocks")

    print(f"{args.xml}")
    print(f"  rooms   {len(rooms)}")
    print(f"  doors   {len(doors)} block columns")
    print(f"  blocks  {len(grid)}")
    if args.out:
        w, l, pal, origin = write_schematic(args.out, grid)
        print(f"  -> {args.out}: {w} x {FLOOR_HEIGHT} x {l}, {pal} palette entries")
        print(f"     paste at x={origin[0]} z={origin[1]} (Stata origin)")
    if args.mcfunction:
        n = write_mcfunction(args.mcfunction, grid, args.base_y, args.world)
        print(f"  -> {args.mcfunction}: {n} setblock lines at y={args.base_y}")


if __name__ == "__main__":
    main()
