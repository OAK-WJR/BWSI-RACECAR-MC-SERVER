#!/usr/bin/env python3
"""Race simulator: runs student racecar code and returns a lap.

    python3 simulate.py --code player.py --track track_meta.json --out out.json

out.json, always written (exit 0) unless the infrastructure itself fails:
    {"status": "ok", "time_s": 42.15, "trajectory": [[x, z, yaw_deg, speed], ...]}
    {"status": "error", "error": "message"}

Physics and sensors come from sim2d (1:1 calibrated against the real
BWSI RACECAR); this file only runs the code and converts the resulting
path into Minecraft coordinates for replay.

Player code runs via exec() with no Python-level sandboxing on purpose:
the container this runs in (no network, read-only, cpu/mem/pid limits)
is the security boundary, not this process.
"""
import argparse
import json
import math
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import racecar_core

MC_HZ = 20                      # replay is one trajectory point per server tick


def to_minecraft(x, y, theta, meta):
    """sim metres -> Minecraft blocks. Sim +y is north, so it maps to -z;
    Minecraft yaw 0 = +z, hence the -(theta + 90) heading."""
    scale = meta["blocks_per_metre"]
    return (round(meta["origin_x"] + x * scale, 3),
            round(meta["origin_z"] - y * scale, 3),
            round(-(math.degrees(theta) + 90.0), 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", required=True)
    ap.add_argument("--track", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    meta = json.load(open(args.track))
    map_yaml = os.path.join(os.path.dirname(os.path.abspath(args.track)), meta["map"])

    car = racecar_core.Racecar(map_yaml, realism=meta.get("realism", False),
                               max_time_s=meta.get("max_time_s", 180),
                               min_travel_m=meta.get("min_travel_m", 25.0),
                               start_radius=meta.get("start_radius_m", 1.5))
    racecar_core._install(car)

    result = None
    try:
        code = open(args.code).read()
        namespace = {"__name__": "__main__", "rc": car}
        exec(compile(code, "player.py", "exec"), namespace)
        if car.finished_at is None and car.error is None:
            # code returned without ever calling rc.go(): nothing was driven
            car.error = "your code finished without running the car (call rc.go())"
    except Exception:
        lines = traceback.format_exc().strip().splitlines()
        result = {"status": "error", "error": lines[-1]}

    if result is None:
        if car.error:
            result = {"status": "error", "error": car.error}
        else:
            step = max(1, round(racecar_core.P.SIM_HZ / MC_HZ))
            trajectory = []
            for i in range(0, len(car.trajectory), step):
                x, y, theta = car.trajectory[i]
                mx, mz, yaw = to_minecraft(x, y, theta, meta)
                trajectory.append([mx, mz, yaw, 0.0])
            result = {"status": "ok",
                      "time_s": round(car.finished_at, 2),
                      "trajectory": trajectory}

    with open(args.out, "w") as fh:
        json.dump(result, fh)


if __name__ == "__main__":
    main()
