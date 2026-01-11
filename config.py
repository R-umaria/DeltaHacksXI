# config.py
# Central configuration (single place for all parameters)

import os

# ----------------------------
# GPIO PIN MAP (BCM) - DO NOT CHANGE
# ----------------------------
SERVO_GPIO = 12              # Shared with LEFT motor PWMA
SONAR_TRIG_GPIO = 23
SONAR_ECHO_GPIO = 24

TB6612_STBY_GPIO = 25

LEFT_PWMA_GPIO = 12          # Shared with servo
LEFT_AIN1_GPIO = 5
LEFT_AIN2_GPIO = 6

RIGHT_PWMB_GPIO = 13
RIGHT_BIN1_GPIO = 20
RIGHT_BIN2_GPIO = 21

# ----------------------------
# Web
# ----------------------------
WEB_HOST = "0.0.0.0"
WEB_PORT = 5000

# Static map path (served by Flask)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
MAP_IMAGE_PATH = os.path.join(STATIC_DIR, "map.png")

# ----------------------------
# Motor control
# ----------------------------
DEFAULT_SPEED_PCT = 60  # percent 0..100
MOTOR_PWM_HZ = 1000

# Obstacle safety
FRONT_STOP_CM = 30
FRONT_SECTOR_MIN_DEG = 80
FRONT_SECTOR_MAX_DEG = 100

# Autonomous move burst
MOVE_BURST_S = 0.20
STEP_CM = 6.0  # assumed forward step per burst (no encoders)

# ----------------------------
# Sonar + Servo scanning
# ----------------------------
SERVO_PWM_HZ = 50
SERVO_SWEEP_MIN_DEG = 45
SERVO_SWEEP_MAX_DEG = 135
SERVO_SWEEP_STEP_DEG = 5
SERVO_SETTLE_S = 0.10

SONAR_SAMPLES_N = 7
SONAR_INLIER_BAND_CM = 15
SONAR_MAX_JUMP_CM = 30

# HC-SR04 timeouts
SONAR_ECHO_RISE_TIMEOUT_S = 0.020
SONAR_ECHO_FALL_TIMEOUT_S = 0.025
SONAR_INTER_PING_S = 0.010

# Servo calibration / reference
# angle_commanded = clamp(angle + ANGLE_OFFSET_DEG)
ANGLE_OFFSET_DEG = 0.0
SERVO_CENTER_DEG = 90.0
FORWARD_SERVO_DEG = 90.0  # which servo angle corresponds to "forward"

# Duty cycle mapping (typical SG90 ~ 2.5%..12.5% at 50 Hz)
SERVO_DUTY_MIN = 2.5
SERVO_DUTY_MAX = 12.5

# When switching PWM ownership on GPIO12, wait for line settle
PWM_SWITCH_SETTLE_S = 0.10

# ----------------------------
# Mapping (Occupancy Grid)
# ----------------------------
MAP_SIZE_M = 4.0
MAP_RESOLUTION_M = 0.05  # 5cm per cell => 80x80 for 4m x 4m
# Derived:
MAP_CELLS = int(MAP_SIZE_M / MAP_RESOLUTION_M)  # 80
MAP_HALF_CM = (MAP_SIZE_M * 100.0) / 2.0        # 200 cm
CELL_CM = MAP_RESOLUTION_M * 100.0              # 5 cm

# Render scaling (pixels per cell)
RENDER_SCALE = 5  # 80*5=400px

# ----------------------------
# Wi-Fi scanning
# ----------------------------
WIFI_INTERFACE = "wlan0"
WIFI_SCAN_PERIOD_S = 3.0
WIFI_NEW_DEVICE_WINDOW_S = 30.0

# Presence score tuning
WIFI_STRONG_RSSI_DBM = -70
WIFI_SCORE_STRONG_COUNT_WEIGHT = 15.0
WIFI_SCORE_STRONGEST_WEIGHT = 1.5
WIFI_SCORE_NEW_DEVICE_WEIGHT = 10.0

# subprocess timeouts
WIFI_SCAN_CMD_TIMEOUT_S = 8.0
