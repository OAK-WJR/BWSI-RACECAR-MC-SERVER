"""The `rc` object handed to player code, mirroring the BWSI RACECAR feel.

Player code sets controls and waits; the simulator integrates the motion.
This module holds no physics — simulate.py owns that.
"""


class RC:
    def __init__(self, sim):
        self._sim = sim

    def set_speed(self, speed, steering_angle=0.0):
        """Speed in m/s (clamped by the simulator), steering in degrees
        (positive turns right, clamped)."""
        self._sim.set_controls(float(speed), float(steering_angle))

    def wait(self, seconds):
        """Hold the current controls for this long."""
        self._sim.advance(float(seconds))
