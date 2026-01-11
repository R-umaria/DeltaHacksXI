import time
import threading
import RPi.GPIO as GPIO

import config


class PWMOwnership:
    """
    Explicit ownership mechanism for a shared PWM pin (GPIO12).
    Ensures only one subsystem (motors or servo) can own GPIO12 PWM at a time.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._owner = None  # str or None

    def acquire(self, owner: str, timeout: float = 2.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self._owner is None or self._owner == owner:
                    self._owner = owner
                    return True
            time.sleep(0.01)
        return False

    def release(self, owner: str) -> None:
        with self._lock:
            if self._owner == owner:
                self._owner = None

    def current_owner(self):
        with self._lock:
            return self._owner


class Motors:
    """
    TB6612FNG motor control.
    - PWM objects are created/destroyed explicitly.
    - GPIO12 (PWMA) ownership must be held by 'motors' when PWM is enabled.
    """
    def __init__(self, pwm_owner: PWMOwnership):
        self.pwm_owner = pwm_owner
        self._lock = threading.Lock()

        self.speed_pct = config.DEFAULT_SPEED_PCT

        self._pwm_a = None  # PWM on GPIO12 (shared)
        self._pwm_b = None  # PWM on GPIO13

        self._initialized = False

    def setup(self):
        with self._lock:
            if self._initialized:
                return

            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            GPIO.setup(config.TB6612_STBY_GPIO, GPIO.OUT, initial=GPIO.LOW)

            GPIO.setup(config.LEFT_AIN1_GPIO, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(config.LEFT_AIN2_GPIO, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(config.RIGHT_BIN1_GPIO, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(config.RIGHT_BIN2_GPIO, GPIO.OUT, initial=GPIO.LOW)

            GPIO.setup(config.LEFT_PWMA_GPIO, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(config.RIGHT_PWMB_GPIO, GPIO.OUT, initial=GPIO.LOW)

            self._initialized = True

    def enable(self) -> bool:
        """
        Enable motor driver + PWM. Must acquire ownership of GPIO12.
        """
        self.setup()
        if not self.pwm_owner.acquire("motors", timeout=2.0):
            return False

        with self._lock:
            GPIO.output(config.TB6612_STBY_GPIO, GPIO.HIGH)

            if self._pwm_a is None:
                self._pwm_a = GPIO.PWM(config.LEFT_PWMA_GPIO, config.MOTOR_PWM_HZ)
                self._pwm_a.start(0.0)

            if self._pwm_b is None:
                self._pwm_b = GPIO.PWM(config.RIGHT_PWMB_GPIO, config.MOTOR_PWM_HZ)
                self._pwm_b.start(0.0)

        return True

    def disable(self):
        """
        Disable PWM outputs and release GPIO12 ownership.
        Required before servo scanning begins.
        """
        with self._lock:
            if self._pwm_a is not None:
                try:
                    self._pwm_a.ChangeDutyCycle(0.0)
                    time.sleep(0.02)
                    self._pwm_a.stop()
                except Exception:
                    pass
                self._pwm_a = None
                GPIO.output(config.LEFT_PWMA_GPIO, GPIO.LOW)

            if self._pwm_b is not None:
                try:
                    self._pwm_b.ChangeDutyCycle(0.0)
                    time.sleep(0.02)
                    self._pwm_b.stop()
                except Exception:
                    pass
                self._pwm_b = None
                GPIO.output(config.RIGHT_PWMB_GPIO, GPIO.LOW)

            GPIO.output(config.TB6612_STBY_GPIO, GPIO.LOW)

        time.sleep(config.PWM_SWITCH_SETTLE_S)
        self.pwm_owner.release("motors")

    def set_speed(self, speed_pct: int):
        speed = max(0, min(100, int(speed_pct)))
        with self._lock:
            self.speed_pct = speed
            self._apply_speed_locked(speed, speed)

    def _apply_speed_locked(self, left_pct: int, right_pct: int):
        # Apply trim factors (calibration)
        left = float(left_pct) * float(getattr(config, "LEFT_SPEED_TRIM", 1.0))
        right = float(right_pct) * float(getattr(config, "RIGHT_SPEED_TRIM", 1.0))

        # Clamp 0..100
        left = max(0.0, min(100.0, left))
        right = max(0.0, min(100.0, right))

        if self._pwm_a is not None:
            self._pwm_a.ChangeDutyCycle(left)
        if self._pwm_b is not None:
            self._pwm_b.ChangeDutyCycle(right)

    def _logical_to_physical(self, left_in1: int, left_in2: int, right_in1: int, right_in2: int):
        """
        Takes desired LEFT/RIGHT direction pins (logical rover frame),
        applies optional inversion and side swapping, and returns
        (AIN1, AIN2, BIN1, BIN2) to drive the physical TB6612 channels.
        """
        # Apply direction inversion (swap IN1/IN2) per side if needed
        if getattr(config, "LEFT_DIR_INVERT", False):
            left_in1, left_in2 = left_in2, left_in1
        if getattr(config, "RIGHT_DIR_INVERT", False):
            right_in1, right_in2 = right_in2, right_in1

        # Swap sides if the physical left/right are wired opposite
        if getattr(config, "MOTORS_SWAP_SIDES", False):
            # logical left drives physical right (B), logical right drives physical left (A)
            ain1, ain2 = right_in1, right_in2
            bin1, bin2 = left_in1, left_in2
        else:
            # logical left -> physical left (A), logical right -> physical right (B)
            ain1, ain2 = left_in1, left_in2
            bin1, bin2 = right_in1, right_in2

        return ain1, ain2, bin1, bin2

    def _set_dirs(self, left_in1: int, left_in2: int, right_in1: int, right_in2: int):
        """
        Public helper: set logical rover LEFT/RIGHT, then map to physical pins.
        """
        ain1, ain2, bin1, bin2 = self._logical_to_physical(left_in1, left_in2, right_in1, right_in2)

        GPIO.output(config.LEFT_AIN1_GPIO, GPIO.HIGH if ain1 else GPIO.LOW)
        GPIO.output(config.LEFT_AIN2_GPIO, GPIO.HIGH if ain2 else GPIO.LOW)
        GPIO.output(config.RIGHT_BIN1_GPIO, GPIO.HIGH if bin1 else GPIO.LOW)
        GPIO.output(config.RIGHT_BIN2_GPIO, GPIO.HIGH if bin2 else GPIO.LOW)

    def forward(self, speed_pct: int = None):
        if speed_pct is not None:
            self.set_speed(speed_pct)
        with self._lock:
            GPIO.output(config.TB6612_STBY_GPIO, GPIO.HIGH)
            # Forward: IN1=H, IN2=L on both sides (logical)
            self._set_dirs(left_in1=1, left_in2=0, right_in1=1, right_in2=0)
            self._apply_speed_locked(self.speed_pct, self.speed_pct)

    def back(self, speed_pct: int = None):
        if speed_pct is not None:
            self.set_speed(speed_pct)
        with self._lock:
            GPIO.output(config.TB6612_STBY_GPIO, GPIO.HIGH)
            # Backward: IN1=L, IN2=H on both sides (logical)
            self._set_dirs(left_in1=0, left_in2=1, right_in1=0, right_in2=1)
            self._apply_speed_locked(self.speed_pct, self.speed_pct)

    def left(self, speed_pct: int = None):
        """
        Turn left in-place: left backward, right forward (logical).
        """
        if speed_pct is not None:
            self.set_speed(speed_pct)
        with self._lock:
            GPIO.output(config.TB6612_STBY_GPIO, GPIO.HIGH)
            self._set_dirs(left_in1=0, left_in2=1, right_in1=1, right_in2=0)
            self._apply_speed_locked(self.speed_pct, self.speed_pct)

    def right(self, speed_pct: int = None):
        """
        Turn right in-place: left forward, right backward (logical).
        """
        if speed_pct is not None:
            self.set_speed(speed_pct)
        with self._lock:
            GPIO.output(config.TB6612_STBY_GPIO, GPIO.HIGH)
            self._set_dirs(left_in1=1, left_in2=0, right_in1=0, right_in2=1)
            self._apply_speed_locked(self.speed_pct, self.speed_pct)

    def coast(self):
        with self._lock:
            GPIO.output(config.LEFT_AIN1_GPIO, GPIO.LOW)
            GPIO.output(config.LEFT_AIN2_GPIO, GPIO.LOW)
            GPIO.output(config.RIGHT_BIN1_GPIO, GPIO.LOW)
            GPIO.output(config.RIGHT_BIN2_GPIO, GPIO.LOW)
            self._apply_speed_locked(0, 0)

    def brake(self):
        with self._lock:
            GPIO.output(config.LEFT_AIN1_GPIO, GPIO.HIGH)
            GPIO.output(config.LEFT_AIN2_GPIO, GPIO.HIGH)
            GPIO.output(config.RIGHT_BIN1_GPIO, GPIO.HIGH)
            GPIO.output(config.RIGHT_BIN2_GPIO, GPIO.HIGH)
            self._apply_speed_locked(0, 0)

    def stop(self, brake: bool = False):
        if brake:
            self.brake()
        else:
            self.coast()

    def cleanup(self):
        try:
            self.stop(brake=False)
            self.disable()
        except Exception:
            pass

