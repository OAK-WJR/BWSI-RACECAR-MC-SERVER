"""
Algorithm-debug overlay for sim2d: mark setpoints/angles from your lab code
and they are drawn directly on the sim window.

    import sys
    sys.path.insert(0, "../../sim2d")     # same style as the racecar_core import
    import debug_draw as dd

    def update():
        ...
        dd.point(best_angle, best_dist)   # chosen target (deg clockwise, cm)
        dd.heading(steer_setpoint_deg)    # desired heading arrow
        dd.text(f"state={state}")

Call every update(); markers expire automatically (~0.4 s). Coordinates use
the lidar convention: angle in degrees, 0 = straight ahead, increasing
clockwise; distance in cm. Colors: "yellow", "cyan", "green", "red", "white", "blue", "magenta".

Fire-and-forget UDP to the sim: on the real car nothing listens and every
call is a safe no-op — fine to leave in your code.
"""

import json
import socket

PORT = 5066
_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_addr = ("127.0.0.1", PORT)


def _send(obj) -> None:
    try:
        _sock.sendto(json.dumps(obj).encode(), _addr)
    except OSError:
        pass


def point(angle_deg: float, dist_cm: float, color: str = "yellow") -> None:
    """Mark a point at lidar polar coordinates (0 = front, clockwise, cm)."""
    _send({"k": "pt", "a": float(angle_deg), "d": float(dist_cm), "c": color})


def heading(angle_deg: float, color: str = "cyan", dist_cm: float = 250.0) -> None:
    """Draw an arrow of length dist_cm from the car at angle_deg (0 = front, cw)."""
    _send({"k": "hd", "a": float(angle_deg), "c": color, "d": float(dist_cm)})


def sector(min_deg: float, max_deg: float, color: str = "green",
           dist_cm: float = 200.0) -> None:
    """Shade the angular sector [min_deg, max_deg] out to dist_cm."""
    _send({"k": "sec", "a0": float(min_deg), "a1": float(max_deg),
           "d": float(dist_cm), "c": color})


def path(points, color: str = "green") -> None:
    """Draw a polyline through body-frame points [(x_m, y_m), ...]
    (x forward, y LEFT, meters). One path per color; expires like other
    markers. Points are rounded to cm so a ~20-point curve fits one packet."""
    _send({"k": "pa", "c": color,
           "p": [[round(float(x), 2), round(float(y), 2)] for x, y in points]})


def text(msg) -> None:
    """Show one line of text under the sim status bar."""
    _send({"k": "tx", "l": str(msg)})
