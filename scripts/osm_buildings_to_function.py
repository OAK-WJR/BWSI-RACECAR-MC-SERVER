#!/usr/bin/env python3
"""Extrude OpenStreetMap building footprints into the campus world.

OSM has MIT mapped by building number (`ref`), with storey counts and surveyed
heights, which is enough for an exterior shell. Interiors are left empty: only
the Stata Center has published floor plans, and those are handled separately by
stata_floorplan_to_schem.py.

Shares that script's origin, so the shells line up with the Stata interior.

Building 32 is excluded by default. Its 127-point OSM outline is the ground
projection of Gehry's tilted, cantilevered massing -- extruding it straight up
produces a lumpy prism that looks nothing like the real thing, so the Stata
exterior is hand-built.
"""

import argparse
import json
import math
from pathlib import Path

from stata_floorplan_to_schem import (
    ORIGIN_LAT,
    ORIGIN_LON,
    line_cells,
    polygon_cells,
)

WALL = "minecraft:light_gray_concrete"
ROOF = "minecraft:gray_concrete"
SLAB = "minecraft:stone_bricks"

DEFAULT_STOREY_HEIGHT = 4.5  # metres, when only a storey count is tagged
FALLBACK_HEIGHT = 12.0


def to_block(lon, lat):
    """WGS84 -> campus block coordinates, 1 block = 1 m, north is -Z."""
    metres_per_deg_lon = 111320 * math.cos(math.radians(ORIGIN_LAT))
    return (round((lon - ORIGIN_LON) * metres_per_deg_lon),
            round(-(lat - ORIGIN_LAT) * 110574))


def building_height(tags):
    """Surveyed height if it parses, else storeys, else a plain default."""
    raw = tags.get("height")
    if raw:
        cleaned = "".join(c for c in str(raw) if c.isdigit() or c == ".")
        try:
            h = float(cleaned)
            if h > 0:
                return h
        except ValueError:
            pass
    levels = tags.get("building:levels")
    if levels:
        try:
            h = float(levels) * DEFAULT_STOREY_HEIGHT
            if h > 0:
                return h
        except ValueError:
            pass
    return FALLBACK_HEIGHT


def build_shell(points, height, base_y):
    """Walls, roof and ground slab. Hollow: these interiors are unknown."""
    grid = {}
    top = base_y + max(1, round(height))

    for cell in polygon_cells(points):
        grid[(cell[0], base_y, cell[1])] = SLAB
        grid[(cell[0], top, cell[1])] = ROOF

    wall_cells = set()
    for i in range(len(points)):
        wall_cells |= line_cells(points[i], points[(i + 1) % len(points)])
    for x, z in wall_cells:
        for y in range(base_y, top):
            grid[(x, y, z)] = WALL

    return grid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("osm_json", help="Overpass output with tags and geometry")
    ap.add_argument("--out-dir", required=True, help="where to write .mcfunction files")
    ap.add_argument("--refs", help="comma-separated building refs; overrides --radius")
    ap.add_argument("--radius", type=float, default=250.0,
                    help="metres from the Stata origin, when --refs is not given")
    ap.add_argument("--base-y", type=int, default=64)
    ap.add_argument("--exclude", default="32", help="comma-separated building refs")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    excluded = {r.strip() for r in args.exclude.split(",") if r.strip()}
    wanted = {r.strip() for r in args.refs.split(",")} if args.refs else None
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    elements = json.loads(Path(args.osm_json).read_text())["elements"]
    selected, skipped = [], 0
    for el in elements:
        tags = el.get("tags", {})
        ref = tags.get("ref")
        geometry = el.get("geometry")
        if not ref or not geometry or ref in excluded:
            continue
        if wanted is not None and ref not in wanted:
            continue
        points = [to_block(p["lon"], p["lat"]) for p in geometry]
        # Overpass repeats the first node to close the way.
        if len(points) > 1 and points[0] == points[-1]:
            points = points[:-1]
        if len(points) < 3:
            skipped += 1
            continue
        if wanted is None and min(math.hypot(x, z) for x, z in points) > args.radius:
            continue
        selected.append((ref, tags, points))

    selected.sort(key=lambda s: s[0])
    total = 0
    for ref, tags, points in selected:
        height = building_height(tags)
        grid = build_shell(points, height, args.base_y)
        total += len(grid)
        name = "bldg_" + ref.lower().replace("-", "_")
        print(f"  {ref:<6} {(tags.get('name') or '-')[:26]:<28} "
              f"h={height:5.1f}m  {len(grid):6d} blocks")
        if not args.dry_run:
            lines = [f"setblock {x} {y} {z} {b}" for (x, y, z), b in sorted(grid.items())]
            (out_dir / f"{name}.mcfunction").write_text("\n".join(lines) + "\n")

    print(f"\n{len(selected)} buildings, {total} blocks"
          + (f", {skipped} skipped (degenerate outline)" if skipped else ""))
    if any(len(build_shell(p, building_height(t), args.base_y)) > 65000
           for _, t, p in selected):
        print("warning: a building exceeds maxCommandChainLength; split it")


if __name__ == "__main__":
    main()
