"""Headless racecar_core, API-compatible with the official library.

Student code written for the real car or RacecarSim runs unchanged: same
module names, same methods, same units. Instead of talking to a simulator
over UDP this drives sim2d's dynamics in-process and returns as soon as
the run is over.

    import racecar_core
    import racecar_utils as rc_utils

    rc = racecar_core.create_racecar()
    rc.set_start_update(start, update, update_slow)
    rc.go()

Only what a timed run needs is real: drive, lidar and physics. There is no
camera or gamepad here, so those read black and neutral.
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


class Drive:
    def __init__(self, car):
        self._car = car

    def set_speed_angle(self, speed, angle):
        self._car.set_speed_angle(speed, angle)

    def stop(self):
        self._car.stop()

    def set_max_speed(self, max_speed=0.25):
        self._car.set_max_speed(max_speed)


class Lidar:
    def __init__(self, lidar):
        self._lidar = lidar

    def get_num_samples(self):
        return P.LIDAR_NUM_SAMPLES

    def get_samples(self):
        return np.asarray(self._lidar.samples, dtype=np.float32)

    def get_samples_async(self):
        return self.get_samples()


class Physics:
    def __init__(self, car, state):
        self._car = car
        self._state = state

    def get_linear_acceleration(self):
        return np.array(self._car.imu_linear_acceleration(self._state["realism"]),
                        dtype=np.float32)

    def get_angular_velocity(self):
        return np.array(self._car.imu_angular_velocity(self._state["realism"]),
                        dtype=np.float32)


class Camera:
    """No camera in the 2D simulator: black frames of the right shape."""

    def get_width(self):
        return 640

    def get_height(self):
        return 480

    def get_max_range(self):
        return 1000.0

    def get_color_image(self):
        return np.zeros((480, 640, 3), dtype=np.uint8)

    def get_color_image_no_copy(self):
        return self.get_color_image()

    def get_color_image_async(self):
        return self.get_color_image()

    def get_depth_image(self):
        return np.zeros((480, 640), dtype=np.float32)

    def get_depth_image_async(self):
        return self.get_depth_image()


class Controller:
    """No gamepad in a scored run: everything reads neutral."""

    class Button:
        A, B, X, Y, LB, RB, LJOY, RJOY = range(8)

    class Trigger:
        LEFT, RIGHT = 0, 1

    class Joystick:
        LEFT, RIGHT = 0, 1

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


class Display:
    def create_window(self):
        pass

    def show_color_image(self, image):
        pass

    def show_depth_image(self, image, max_depth=1000, points=[]):
        pass

    def show_lidar(self, samples, radius=128, max_range=1000, highlighted_samples=[]):
        pass


class Racecar:
    def __init__(self, map_yaml, realism=False, max_time_s=180.0,
                 min_travel_m=25.0, start_radius=1.5):
        self.world = World(map_yaml)
        sx, sy, sth = self.world.start_pose
        self.car = CarDynamics(sx, sy, sth)
        self.state = {"realism": realism}
        self._lidar_sim = LidarA1(self.world, realism=realism, seed=0)

        self.drive = Drive(self.car)
        self.lidar = Lidar(self._lidar_sim)
        self.physics = Physics(self.car, self.state)
        self.camera = Camera()
        self.controller = Controller()
        self.display = Display()

        self._start = None
        self._update = None
        self._update_slow = None
        self._slow_time = 1.0
        self._slow_due = 1.0

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
        self._slow_time = time
        self._slow_due = self.t + time

    def go(self):
        if self._start is not None:
            self._start()
        try:
            while True:
                self._step()
                if self._update is not None:
                    self._update()
                if self._update_slow is not None and self.t >= self._slow_due:
                    self._slow_due = self.t + self._slow_time
                    self._update_slow()
        except LapDone:
            pass

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


def create_racecar(isSimulation=None):
    """Same call as the official library. The -s/-d/-h flags it reads are
    ignored here: a scored run is always this simulator, never a window."""
    if _current is None:
        raise RuntimeError("no simulation running")
    return _current


def _install(racecar):
    global _current
    _current = racecar
