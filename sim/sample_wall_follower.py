"""Sample submission: follow the right-hand wall.

The classic two-ray wall follower: work out the angle to the wall on the
right, predict where the car will be a moment from now, and steer to hold a
fixed distance. Ordinary racecar_core code — the same file runs against the
real car, the official simulator, and here. It gets round; it is not fast,
and that is the part left to you.
"""
import math

import racecar_core

rc = racecar_core.create_racecar()

TARGET_CM = 55      # distance to hold from the right-hand wall
THETA = 45          # degrees between the two rays used to find the wall
LOOKAHEAD_CM = 45   # how far ahead the correction is aimed
KP = 0.030
KD = 0.010
SPEED_FAR = 0.4
SPEED_NEAR = 0.2
STUCK_CM = 40
BACKUP_TICKS = 35

state = {"backup": 0, "away": 1.0, "last_error": 0.0}


def ray(scan, degrees):
    """Distance in cm at this bearing, front = 0, clockwise. 0 = no return."""
    return float(scan[int(degrees % 360 / 360 * len(scan))])


def nose_distance(scan):
    values = [ray(scan, d) for d in range(-30, 31, 3)]
    valid = [v for v in values if v > 0]
    return min(valid) if valid else 999.0


def start():
    rc.drive.set_max_speed(1.0)


def update():
    scan = rc.lidar.get_samples()
    nose = nose_distance(scan)

    # A wedged car cannot steer: the bicycle model needs motion to turn, and
    # a head-on collision holds the speed at zero. Reverse out first.
    if state["backup"] == 0 and nose < STUCK_CM:
        left = sum(v for v in (ray(scan, d) for d in range(240, 300, 5)) if v > 0)
        right = sum(v for v in (ray(scan, d) for d in range(60, 120, 5)) if v > 0)
        state["away"] = 1.0 if right > left else -1.0
        state["backup"] = BACKUP_TICKS
    if state["backup"] > 0:
        state["backup"] -= 1
        rc.drive.set_speed_angle(-0.35, -state["away"])
        return

    # two rays onto the right-hand wall: b is perpendicular, a is ahead of it
    b = ray(scan, 90)
    a = ray(scan, 90 - THETA)
    if a <= 0 or b <= 0:
        rc.drive.set_speed_angle(SPEED_NEAR, 0.4)      # lost the wall: curve back
        return

    theta = math.radians(THETA)
    alpha = math.atan2(a * math.cos(theta) - b, a * math.sin(theta))
    distance = b * math.cos(alpha) + LOOKAHEAD_CM * math.sin(alpha)

    error = distance - TARGET_CM
    angle = KP * error + KD * (error - state["last_error"]) * 60
    state["last_error"] = error

    speed = SPEED_FAR if nose > 130 else SPEED_NEAR
    if nose < 70:                                       # corner coming: turn in
        angle -= 0.6
    rc.drive.set_speed_angle(speed, max(-1.0, min(1.0, angle)))


rc.set_start_update(start, update)
rc.go()
