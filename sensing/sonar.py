# sensing/sonar.py

import time
import math
import statistics
from typing import List, Dict, Optional

import RPi.GPIO as GPIO

import config
from controllers.motors import PWMOwnership


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


class SonarScanner:
    """
    HC-SR04 + SG90 on shared GPIO12.
    Creates/owns servo PWM only during scanning, then stops and releases ownership.
    """
    def __init__(self, pwm_owner: PWMOwnership):
        self.pwm_owner = pwm_owner
        self._servo_pwm = None
        self._initialized = False

        # last accepted distance for continuity gate
        self._last_accepted_cm = None

    def setup(self):
        if self._initialized:
            return
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        GPIO.setup(config.SONAR_TRIG_GPIO, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(config.SONAR_ECHO_GPIO, GPIO.IN)

        # Do NOT setup servo PWM here; only when scanning begins and ownership acquired.
        self._initialized = True

    def _servo_pwm_start(self):
        """
        Acquire GPIO12 ownership and create servo PWM.
        """
        if not self.pwm_owner.acquire("servo", timeout=2.0):
            raise RuntimeError(f"GPIO12 ownership busy (current owner={self.pwm_owner.current_owner()})")

        GPIO.setup(config.SERVO_GPIO, GPIO.OUT, initial=GPIO.LOW)
        self._servo_pwm = GPIO.PWM(config.SERVO_GPIO, config.SERVO_PWM_HZ)
        self._servo_pwm.start(0.0)
        time.sleep(0.05)

    def _servo_pwm_stop(self):
        """
        Stop servo PWM and release GPIO12 ownership.
        """
        if self._servo_pwm is not None:
            try:
                # stop signal: duty to 0 then stop
                self._servo_pwm.ChangeDutyCycle(0.0)
                time.sleep(0.02)
                self._servo_pwm.stop()
            except Exception:
                pass
            self._servo_pwm = None
            GPIO.output(config.SERVO_GPIO, GPIO.LOW)

        time.sleep(config.PWM_SWITCH_SETTLE_S)
        self.pwm_owner.release("servo")

    def _angle_to_duty(self, angle_deg: float) -> float:
        # Map 0..180 to SERVO_DUTY_MIN..SERVO_DUTY_MAX
        a = clamp(angle_deg, 0.0, 180.0)
        return config.SERVO_DUTY_MIN + (a / 180.0) * (config.SERVO_DUTY_MAX - config.SERVO_DUTY_MIN)

    def set_servo_angle(self, angle_deg: float):
        if self._servo_pwm is None:
            return

        angle_cmd = clamp(angle_deg + config.ANGLE_OFFSET_DEG, 0.0, 180.0)
        duty = self._angle_to_duty(angle_cmd)
        self._servo_pwm.ChangeDutyCycle(duty)

    def _ping_distance_cm(self) -> Optional[float]:
        """
        Single HC-SR04 ping; returns distance in cm or None on timeout.
        """
        # Trigger pulse 10us
        GPIO.output(config.SONAR_TRIG_GPIO, GPIO.LOW)
        time.sleep(0.0002)
        GPIO.output(config.SONAR_TRIG_GPIO, GPIO.HIGH)
        time.sleep(0.00001)
        GPIO.output(config.SONAR_TRIG_GPIO, GPIO.LOW)

        # Wait for echo rise
        t0 = time.perf_counter()
        while GPIO.input(config.SONAR_ECHO_GPIO) == 0:
            if (time.perf_counter() - t0) > config.SONAR_ECHO_RISE_TIMEOUT_S:
                return None

        start = time.perf_counter()

        # Wait for echo fall
        while GPIO.input(config.SONAR_ECHO_GPIO) == 1:
            if (time.perf_counter() - start) > config.SONAR_ECHO_FALL_TIMEOUT_S:
                return None

        end = time.perf_counter()
        duration = end - start

        # Speed of sound ~34300 cm/s; distance = (duration * 34300) / 2
        dist_cm = duration * 17150.0
        if dist_cm <= 0:
            return None
        return dist_cm

    def _robust_distance_at_angle(self) -> Optional[float]:
        """
        Robust distance estimate:
        - take N samples (drop None)
        - median
        - inlier band +/- SONAR_INLIER_BAND_CM around median
        - output median(inliers)
        """
        samples = []
        for _ in range(config.SONAR_SAMPLES_N):
            d = self._ping_distance_cm()
            if d is not None and 1.0 <= d <= 450.0:
                samples.append(d)
            time.sleep(config.SONAR_INTER_PING_S)

        if len(samples) < 3:
            return None

        med = statistics.median(samples)
        inliers = [x for x in samples if abs(x - med) <= config.SONAR_INLIER_BAND_CM]
        if len(inliers) < 2:
            return None

        return float(statistics.median(inliers))

    def scan(self) -> List[Dict]:
        """
        Sweep servo and measure distances.
        Returns a list of dicts: {angle_deg, bearing_deg, distance_cm, x_cm, y_cm}
        bearing_deg: 0 is forward, negative left, positive right (relative to rover)
        """
        self.setup()
        self._last_accepted_cm = None

        points = []
        self._servo_pwm_start()
        try:
            sweep = list(range(
                int(config.SERVO_SWEEP_MIN_DEG),
                int(config.SERVO_SWEEP_MAX_DEG) + 1,
                int(config.SERVO_SWEEP_STEP_DEG)
            ))

            for angle in sweep:
                self.set_servo_angle(angle)
                time.sleep(config.SERVO_SETTLE_S)

                d = self._robust_distance_at_angle()
                if d is None:
                    continue

                # Continuity gate vs last accepted angle
                if self._last_accepted_cm is not None:
                    if abs(d - self._last_accepted_cm) > config.SONAR_MAX_JUMP_CM:
                        # rejected jump
                        continue

                self._last_accepted_cm = d

                bearing_deg = float(angle) - float(config.FORWARD_SERVO_DEG)
                br = math.radians(bearing_deg)

                # Robot frame: x right, y forward
                x_cm = d * math.sin(br)
                y_cm = d * math.cos(br)

                points.append({
                    "angle_deg": float(angle),
                    "bearing_deg": bearing_deg,
                    "distance_cm": float(d),
                    "x_cm": float(x_cm),
                    "y_cm": float(y_cm),
                })

        finally:
            self._servo_pwm_stop()

        return points
