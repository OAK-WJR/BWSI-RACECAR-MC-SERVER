"""
sim2d — 1:1 real-car dynamics.

Hammerstein chain: pure delay -> static map -> asymmetric first-order lag ->
bicycle model with speed-dependent understeer. Calibration sources in car_params.py.

Command chain matches the real car:
  student set_speed_angle(speed, angle)
    -> u = speed * max_speed           (drive_real publishes speed*max_speed)
    -> steer_cmd = -angle              (drive_real negates; table +s = left/CCW)
  Commands time out to neutral after 0.5 s (real mux_node behavior).
"""

import math
from collections import deque

import numpy as np

import car_params as P


class _DelayLine:
    """Fixed pure delay: buffer commands by timestamp, pop values older than delay."""

    def __init__(self, delay_s: float, initial: float = 0.0) -> None:
        self.delay = delay_s
        self.buf: deque = deque()  # (t, value)
        self.value = initial

    def push(self, t: float, v: float) -> float:
        self.buf.append((t, v))
        while self.buf and self.buf[0][0] <= t - self.delay:
            self.value = self.buf.popleft()[1]
        return self.value


class CarDynamics:
    def __init__(self, x: float, y: float, theta: float) -> None:
        self.x, self.y, self.theta = x, y, theta
        self.v = 0.0            # signed longitudinal speed (m/s)
        self.delta = 0.0        # front wheel angle (rad, + = left/CCW)
        self.yaw_rate = 0.0     # rad/s
        self.accel = 0.0        # dv/dt (m/s^2)

        self.max_speed = P.MAX_SPEED_DEFAULT
        self._cmd_speed = 0.0   # latest normalized command
        self._cmd_angle = 0.0
        self._last_cmd_time = 0.0
        self._t = 0.0

        self._speed_delay = _DelayLine(P.SPEED_DELAY)
        self._steer_delay = _DelayLine(P.STEER_DELAY)

        # IMU: yaw bias drawn per launch (real realsense measured N(0.16, 0.05))
        self.imu_yaw_bias = np.random.default_rng().normal(
            P.IMU_YAW_BIAS_MEAN, P.IMU_YAW_BIAS_STD)
        self._imu_rng = np.random.default_rng()

    # ------------------------------------------------------------ commands
    def set_speed_angle(self, speed: float, angle: float, t: float = None) -> None:
        self._cmd_speed = float(np.clip(speed, -1, 1))
        self._cmd_angle = float(np.clip(angle, -1, 1))
        self._last_cmd_time = self._t if t is None else t

    def set_max_speed(self, max_speed: float) -> None:
        self.max_speed = float(np.clip(max_speed, 0, 1))

    def respawn(self, x: float, y: float, theta: float) -> None:
        """Reset pose/motion but keep the client-set max_speed: the student
        script's start() only runs once, so a BACKSPACE/drag reset must not
        silently drop the car back to the 0.5 default cap."""
        max_speed = self.max_speed
        self.__init__(x, y, theta)
        self.max_speed = max_speed

    def stop(self) -> None:
        self.set_speed_angle(0.0, 0.0)

    # ------------------------------------------------------------ IMU readings
    def imu_linear_acceleration(self, realism: bool):
        """Unity convention: x=right, y=up, z=forward (m/s^2)."""
        ax = -self.v * self.yaw_rate
        az = self.accel
        if realism:
            n = self._imu_rng.normal(0, P.IMU_ACCEL_NOISE_STD, 3)
            return (ax + n[0], P.GRAVITY + n[1], az + n[2])
        return (ax, 0.0, az)

    def imu_angular_velocity(self, realism: bool):
        """Unity convention: y=yaw (+ = right turn). Real bias+noise injected on y."""
        wy = -self.yaw_rate
        if realism:
            n = self._imu_rng.normal(0, P.IMU_GYRO_NOISE_STD, 3)
            return (n[0], wy + self.imu_yaw_bias + n[1], n[2])
        return (0.0, wy, 0.0)

    # ------------------------------------------------------------ static maps
    @staticmethod
    def _speed_map(u: float) -> float:
        """Normalized command u -> steady-state speed m/s (symmetric in reverse),
        capped at SPEED_LIMIT."""
        v = float(np.interp(abs(u), P.SPEED_CAL_U, P.SPEED_CAL_V))
        return math.copysign(min(v, P.SPEED_LIMIT), u)

    @staticmethod
    def _steer_map(s: float) -> float:
        """Normalized steer s (+ = left/CCW) -> front wheel angle rad."""
        return float(np.interp(s, P.STEER_CAL_S, P.STEER_CAL_DELTA))

    # ------------------------------------------------------------ integration
    def step(self, dt: float, collides=None) -> None:
        """collides: fn(x, y, theta) -> bool; on wall contact v = 0 / slide."""
        self._t += dt
        t = self._t

        # command timeout to neutral (real mux_node)
        u_cmd, s_cmd = self._cmd_speed, self._cmd_angle
        if t - self._last_cmd_time > P.COMMAND_TIMEOUT:
            u_cmd, s_cmd = 0.0, 0.0

        # sign chain: student +angle = right turn -> table s = + left
        u = self._speed_delay.push(t, u_cmd * self.max_speed)
        s = self._steer_delay.push(t, -s_cmd)

        v_ss = self._speed_map(u)
        delta_ss = self._steer_map(s)

        # asymmetric first-order lag (longitudinal)
        tau_v = P.SPEED_TAU_UP if abs(v_ss) > abs(self.v) else P.SPEED_TAU_DOWN
        v_new = self.v + (v_ss - self.v) * (1.0 - math.exp(-dt / tau_v))
        self.accel = (v_new - self.v) / dt if dt > 0 else 0.0
        self.v = v_new

        # servo first-order lag
        self.delta += (delta_ss - self.delta) * (1.0 - math.exp(-dt / P.STEER_TAU))

        # bicycle model + speed-dependent understeer
        l_eff = P.WHEELBASE * (1.0 + P.UNDERSTEER_K * self.v * self.v)
        self.yaw_rate = self.v * math.tan(self.delta) / l_eff

        nx = self.x + self.v * math.cos(self.theta) * dt
        ny = self.y + self.v * math.sin(self.theta) * dt
        ntheta = self.theta + self.yaw_rate * dt

        if collides is not None and collides(nx, ny, ntheta):
            # wall contact: try sliding along the wall (axis-separated), heavy damping
            if not collides(nx, self.y, ntheta):
                self.x, self.theta = nx, ntheta
                self.v *= 0.90
            elif not collides(self.x, ny, ntheta):
                self.y, self.theta = ny, ntheta
                self.v *= 0.90
            else:
                # head-on: stop in place; rotation only if collision-free
                # (otherwise the car slowly grinds a corner into a wall cell
                # and wedges permanently)
                self.v = 0.0
                self.accel = 0.0
                self.yaw_rate = 0.0
                if not collides(self.x, self.y, ntheta):
                    self.theta = ntheta
        else:
            self.x, self.y, self.theta = nx, ny, ntheta
