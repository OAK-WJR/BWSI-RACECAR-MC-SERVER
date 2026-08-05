# Race simulator

Players submit racecar code; this directory runs it and returns a lap.

The physics, the lidar and the track come from **sim2d**, the BWSI RACECAR
Neo 2D simulator (https://github.com/BWSI-67/wallfacer, commit e518de8),
whose parameters are calibrated 1:1 against the real car. `sim2d/` is a copy
of its `car_params.py`, `dynamics.py`, `lidar_a1.py`, `world.py`,
`debug_draw.py` and maps. One change: `lidar_a1._raycast` marches in chunks
so beams that hit early stop costing work — the output is bit-identical, it
is just seven times faster, which matters when every submission simulates a
whole lap.

## Writing a submission

Ordinary racecar_core code, unchanged. The same file runs against the real
car, the official RacecarSim, and here — `racecar_core` and `racecar_utils`
are the official API, so `sys.path.insert(0, "../../library")` at the top of
a lab file is harmless and every `rc_utils` helper is available:

```python
import racecar_core

rc = racecar_core.create_racecar()

def start():
    rc.drive.set_max_speed(1.0)

def update():
    scan = rc.lidar.get_samples()          # 720 samples, cm, index 0 = front
    rc.drive.set_speed_angle(0.4, 0.0)     # both in [-1, 1], +angle = right

rc.set_start_update(start, update)
rc.go()
```

`sample_wall_follower.py` is a working example: it completes the course in
about 40 seconds and is deliberately slow.

`racecar_utils.py` is the official file from MITLLRacecar/racecar-student,
with one edit: a stand-in for `nptyping`, which is only used for annotations.

Real here: `rc.drive`, `rc.lidar`, `rc.physics`, `rc.get_delta_time()`,
`start`/`update`/`update_slow`. Stubbed: `rc.camera` returns black frames of
the right shape, `rc.controller` reads neutral, `rc.display` does nothing —
a scored run has no camera, no gamepad and no window.

A run counts when the car has driven most of the corridor and comes back to
the start line, and fails if that takes longer than `max_time_s`.

## Contract

```
python3 simulate.py --code player.py --track track_meta.json --out out.json
```

`out.json`, always written (exit 0 whenever it was — player mistakes are
results, not failures):

```json
{"status": "ok", "time_s": 39.83, "trajectory": [[x, z, yaw_deg, speed], ...]}
{"status": "error", "error": "did not finish within 90s"}
```

The trajectory is in Minecraft world coordinates at 20 Hz, one point per
server tick, ready for the plugin to replay.

`track_meta.json` is generated with the track itself — never edit it by
hand:

```bash
docker build -t bwsi-race-sim sim/
docker run --rm -v /root/minecraft:/mc -w /mc bwsi-race-sim python scripts/gen_track.py
```

Security note: player code runs under `exec()` with no Python-level
sandboxing — the container (no network, read-only, resource limits) is the
boundary. Keep it that way.
