"""
sim2d — BWSI RACECAR Neo 2026 real-car parameters (1:1).

Sources (all measured/official — do not tweak by feel):
- Dynamics: jetson:~/racecar_docker/work/gazebo/dyncal/fit_results.yaml
  (2026-07-20, calibrated against real wheel-speed /encoder/speed,
  bags: best_best_best_best / best_0.2 / best_0.3)
- Geometry: jetson:~/racecar_docker/work/gazebo/racecar.urdf + calibration.yaml
- LIDAR:   RPLidar A1 official spec (slamtec.com/en/lidar/a1spec);
  defect statistics measured from real-car bags (calibration.yaml sensors.lidar)
- IMU:     calibration.yaml sensors + vehicle_dynamics.imu_yaw_bias_rad_s
"""

# ---------------------------------------------------------------- geometry (m)
WHEELBASE = 0.225          # L (confirmed by official Unity twin)
TRACK_WIDTH = 0.21
BODY_LENGTH = 0.28         # collision box (URDF)
BODY_WIDTH = 0.20
WHEEL_RADIUS = 0.042

# ---------------------------------------- longitudinal (real wheel-speed fit)
TOP_SPEED = 4.5            # m/s at full throttle (user setting; calibrated car did 2.90)
SPEED_CAL_U = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
# calibrated steady-state curve [0, 1.252, 1.619, 1.936, 2.658, 2.900], scaled to TOP_SPEED
SPEED_CAL_V = [v * TOP_SPEED / 2.900
               for v in [0.0, 1.252, 1.619, 1.936, 2.658, 2.900]]
SPEED_LIMIT = TOP_SPEED    # hard cap in dynamics
SPEED_TAU_UP = 0.373       # s, first-order lag accelerating
SPEED_TAU_DOWN = 0.247     # s, decelerating
SPEED_DELAY = 0.10         # s, pure delay
# turn_slowdown = 0.0 — real wheel-speed data rejected turn coupling; not modeled

# ---------------------------------------------- lateral / steering (yaw fit)
STEER_CAL_S = [-1.0, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0]
STEER_CAL_DELTA = [-0.369, -0.348, -0.348, -0.162, 0.0, 0.162, 0.348, 0.348, 0.369]
STEER_TAU = 0.10           # s, servo first-order lag
STEER_DELAY = 0.12         # s, pure delay
UNDERSTEER_K = 0.046       # L_eff = L * (1 + K*v^2);  yaw = v*tan(delta)/L_eff

# Sign chain: student API +angle = right turn; real drive_real publishes -angle;
# calibration table +s = left turn (CCW)  =>  sim steer_cmd = -angle

# ---------------------------------------------------------------- command chain
MAX_SPEED_DEFAULT = 0.50   # real-car drive_real.py default (Unity sim uses 0.25)
COMMAND_TIMEOUT = 0.5      # s, official pit.yaml: commands time out to neutral

# ---------------------------------------------------------------- RPLidar A1
LIDAR_RANGE_MIN = 0.15     # m (official)
LIDAR_RANGE_MAX = 12.0     # m (A1M8-R5+ official)
LIDAR_SCAN_HZ = 7.0        # rotations/s (real car measured; A1 official typical 5.5)
LIDAR_SAMPLE_RATE = 8000   # samples/s (official)
LIDAR_BEAMS = int(round(LIDAR_SAMPLE_RATE / LIDAR_SCAN_HZ))  # ~1454 beams/rev
LIDAR_NUM_SAMPLES = 720    # racecar_core output array length (lidar.py _NUM_SAMPLES)
# A1 accuracy: sigma per range band (gaussian), plus measured noise floor
LIDAR_ACC_BANDS = [(3.0, 0.01), (5.0, 0.02), (float("inf"), 0.025)]  # (limit m, pct)
LIDAR_NOISE_FLOOR = 0.02   # m, measured frame-to-frame jitter on static targets

# real-car measured defects (injected in REALISM mode)
LIDAR_NO_RETURN_FRAC = 0.13     # 13% of beams return nothing -> 0.0
LIDAR_JITTER_STD = 0.166        # s, scan-interval jitter std
LIDAR_DROPOUT_MAX = 1.36        # s, longest whole-scan dropout
LIDAR_DROPOUT_PROB = 0.02       # per-scan probability of a dropout event
LIDAR_LATENCY = 0.06            # s, injected latency (measured 235ms incl. recording
                                # overhead is the upper bound; conservative default)

# ---------------------------------------------------------------- IMU (physics)
IMU_YAW_BIAS_MEAN = 0.16   # rad/s, measured realsense gyro bias (straight driving)
IMU_YAW_BIAS_STD = 0.05    # bias drawn per launch: N(mean, std)
IMU_GYRO_NOISE_STD = 0.056 # rad/s (z axis, measured)
IMU_ACCEL_NOISE_STD = 1.0  # m/s^2 (LSM9DS1, measured)
GRAVITY = 9.81

# ---------------------------------------------------------------- simulation
SIM_HZ = 60                # main loop rate (matches Unity sim)
