#!/usr/bin/env python3
"""Race simulator contract. CLI, schemas and conventions are fixed; the
physics inside is a placeholder to be replaced with the real simulator.

    python3 simulate.py --code player.py --track track.json --out out.json

out.json, always written (exit 0) unless the infrastructure itself fails:
    {"status": "ok", "time_s": 42.15, "trajectory": [[x, z, yaw_deg, speed], ...]}
    {"status": "error", "error": "message"}

Conventions: Minecraft world coordinates; yaw in Minecraft degrees
(yaw 0 = +z, yaw 90 = -x); trajectory sampled at exactly 20 Hz.

Player code runs via exec() with no Python-level sandboxing on purpose:
the Docker container this runs in (no network, read-only, cpu/mem/pid
limits) is the security boundary, not this process.
"""
import argparse
import json
import math

DT = 0.05                 # 20 Hz
MAX_SPEED = 15.0          # m/s; the 942 m lap needs pace to fit max_time_s
MAX_STEER = 30.0          # degrees
STEER_RATE = 90.0         # deg/s of heading change at full steering


class Simulation:
    def __init__(self, track):
        self.track = track
        self.x = track["start"]["x"]
        self.z = track["start"]["z"]
        self.yaw = track["start"]["yaw_deg"]
        self.speed = 0.0
        self.steer = 0.0
        self.t = 0.0
        self.trajectory = [[self.x, self.z, self.yaw, self.speed]]
        self.progress = 0            # furthest centerline index reached
        self.finished_at = None
        half = track["track_width"] / 2
        self._half2 = half * half
        self._center = track["centerline"]

    def set_controls(self, speed, steer):
        self.speed = max(-MAX_SPEED, min(MAX_SPEED, speed))
        self.steer = max(-MAX_STEER, min(MAX_STEER, steer))

    def advance(self, seconds):
        steps = max(1, round(seconds / DT))
        for _ in range(steps):
            if self.finished_at is not None:
                return
            self._step()

    def _step(self):
        self.t += DT
        if self.t > self.track["max_time_s"]:
            raise RaceError(f"did not finish within {self.track['max_time_s']}s")
        self.yaw += STEER_RATE * (self.steer / MAX_STEER) * DT
        radians = math.radians(self.yaw)
        old_z = self.z
        self.x += -math.sin(radians) * self.speed * DT
        self.z += math.cos(radians) * self.speed * DT
        self.trajectory.append(
            [round(self.x, 3), round(self.z, 3), round(self.yaw, 2), round(self.speed, 3)])

        idx = self._nearest_index()
        d2 = ((self.x - self._center[idx][0]) ** 2
              + (self.z - self._center[idx][1]) ** 2)
        if d2 > self._half2:
            raise RaceError(f"off track at t={self.t:.2f}s")
        if idx > self.progress:
            self.progress = idx

        # finish: crossed the z=0 line at the start sector, most waypoints done
        f = self.track["finish_line"]
        if (self.progress > len(self._center) * 0.5
                and old_z < 0 <= self.z
                and f[0][0] <= self.x <= f[1][0]):
            self.finished_at = self.t

    def _nearest_index(self):
        return min(range(len(self._center)),
                   key=lambda i: (self.x - self._center[i][0]) ** 2
                                 + (self.z - self._center[i][1]) ** 2)


class RaceError(Exception):
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", required=True)
    ap.add_argument("--track", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    track = json.load(open(args.track))
    sim = Simulation(track)

    import rc_api
    rc = rc_api.RC(sim)

    result = None
    try:
        code = open(args.code).read()
        exec(compile(code, "player.py", "exec"), {"rc": rc})
        # let the car coast on its last controls until finish or timeout
        while sim.finished_at is None:
            sim._step()
    except RaceError as e:
        result = {"status": "error", "error": str(e)}
    except Exception as e:
        result = {"status": "error", "error": f"{type(e).__name__}: {e}"}

    if result is None:
        result = {"status": "ok",
                  "time_s": round(sim.finished_at, 2),
                  "trajectory": sim.trajectory}
    with open(args.out, "w") as fh:
        json.dump(result, fh)


if __name__ == "__main__":
    main()
