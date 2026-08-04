"""Headless racecar_core for batch lap simulation.

Student code written for the real car or RacecarSim runs unchanged: the API
is the same, but instead of talking to a simulator over UDP this drives
sim2d's dynamics in-process and returns as soon as the lap is done. Only the
parts a lap needs are real — camera and controller return neutral values.

    import racecar_core
    rc = racecar_core.create_racecar()
    rc.set_start_update(start, update)
    rc.go()
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim2d"))

import numpy as np

import car_params as P
from dynamics import CarDynamics
from lidar_a1 import LidarA1
from world import World

DT = 1.0 / P.SIM_HZ


class LapDone(Exception):
    """Raised inside the loop to unwind out of student code."""


class _Drive:
    def __init__(self, car):
        self._car = car

    def set_speed_angle(self, speed, angle):
        self._car.set_speed_angle(speed, angle)

    def stop(self):
        self._car.stop()

    def set_max_speed(self, max_speed):
        self._car.set_max_speed(max_speed)


class _Lidar:
    def __init__(self, lidar):
        self._lidar = lidar

    def get_num_samples(self):
        return P.LIDAR_NUM_SAMPLES

    def get_samples(self):
        return np.asarray(self._lidar.samples, dtype=np.float32)

    def get_samples_async(self):
        return self.get_samples()


class _Physics:
    def __init__(self, car, state):
        self._car = car
        self._state = state

    def get_linear_acceleration(self):
        return self._car.imu_linear_acceleration(self._state["realism"])

    def get_angular_velocity(self):
        return self._car.imu_angular_velocity(self._state["realism"])


class _Camera:
    """No camera in the 2D simulator: black frames, right shape."""

    def get_width(self):
        return 640

    def get_height(self):
        return 480

    def get_color_image(self):
        return np.zeros((480, 640, 3), dtype=np.uint8)

    def get_color_image_async(self):
        return self.get_color_image()

    def get_depth_image(self):
        return np.zeros((60, 80), dtype=np.float32)

    def get_depth_image_async(self):
        return self.get_depth_image()


class _Controller:
    """No gamepad in a scored run: everything reads neutral."""

    class Button:
        A = 0
        B = 1
        X = 2
        Y = 3
        LB = 4
        RB = 5
        LJOY = 6
        RJOY = 7

    class Trigger:
        LEFT = 0
        RIGHT = 1

    class Joystick:
        LEFT = 0
        RIGHT = 1

    def is_down(self, button):
        return False

    def was_pressed(self, button):
        return False

    def was_released(self, button):
        return False

    def get_trigger(self, trigger):
        return 0.0

    def get_joystick(self, joystick):
        return (0.0, 0.0)


class _Display:
    def show_color_image(self, image):
        pass

    def show_depth_image(self, image, *args, **kwargs):
        pass

    def create_window(self):
        pass


class Racecar:
    def __init__(self, map_yaml, realism=False, max_time_s=180.0,
                 min_travel_m=25.0, start_radius=1.5):
        self.world = World(map_yaml)
        sx, sy, sth = self.world.start_pose
        self.car = CarDynamics(sx, sy, sth)
        self.state = {"realism": realism}
        self._lidar_sim = LidarA1(self.world, realism=realism, seed=0)

        self.drive = _Drive(self.car)
        self.lidar = _Lidar(self._lidar_sim)
        self.physics = _Physics(self.car, self.state)
        self.camera = _Camera()
        self.controller = _Controller()
        self.display = _Display()

        self._start = None
        self._update = None
        self._update_slow = None

        self.t = 0.0
        self.max_time_s = max_time_s
        self.trajectory = []            # (x, y, theta) in sim metres, one per tick
        self.finished_at = None
        self.error = None

        # a run is one circuit: drive most of the corridor, then come back
        # to the start line. gen_track.py measures the corridor.
        self._start_xy = (sx, sy)
        self._min_travel = min_travel_m
        self._start_radius = start_radius
        self.travelled = 0.0
        self._left_start = False

        margin = 2 * self.world.resolution
        self._collides = lambda x, y, th: self.world.box_collides(
            x, y, th, P.BODY_LENGTH - margin, P.BODY_WIDTH - margin)

    # ------------------------------------------------------------ student API
    def get_delta_time(self):
        return DT

    def set_start_update(self, start, update, update_slow=None):
        self._start = start
        self._update = update
        self._update_slow = update_slow

    def set_update_slow_time(self, time=1.0):
        pass

    def go(self):
        if self._start is not None:
            self._start()
        try:
            while True:
                self._step()
                if self._update is not None:
                    self._update()
        except LapDone:
            pass

    def run(self, start, update, update_slow=None):
        self.set_start_update(start, update, update_slow)
        self.go()

    # ------------------------------------------------------------ simulation
    def _step(self):
        self.car.step(DT, self._collides)
        self.t += DT
        self._lidar_sim.update(self.t, self.car.x, self.car.y, self.car.theta)
        self.trajectory.append((self.car.x, self.car.y, self.car.theta))

        if len(self.trajectory) > 1:
            previous = self.trajectory[-2]
            self.travelled += math.dist((self.car.x, self.car.y), previous[:2])

        home = math.dist((self.car.x, self.car.y), self._start_xy) < self._start_radius
        if not home:
            self._left_start = True
        elif self._left_start and self.travelled >= self._min_travel:
            self.finished_at = self.t
            raise LapDone()
        if self.t > self.max_time_s:
            self.error = f"did not finish within {self.max_time_s:.0f}s"
            raise LapDone()


_current = None


def create_racecar(isSimulation=True):
    """The harness builds the car first; student code just picks it up."""
    if _current is None:
        raise RuntimeError("no simulation running")
    return _current


def _install(racecar):
    global _current
    _current = racecar
