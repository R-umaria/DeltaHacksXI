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
        if self._pwm_a is not None:
            self._pwm_a.ChangeDutyCycle(float(left_pct))
        if self._pwm_b is not None:
            self._pwm_b.ChangeDutyCycle(float(right_pct))

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

    def forward(self, speed_pct: int = None):
        if speed_pct is not None:
            self.set_speed(speed_pct)
        with self._lock:
            GPIO.output(config.TB6612_STBY_GPIO, GPIO.HIGH)
            GPIO.output(config.LEFT_AIN1_GPIO, GPIO.LOW)
            GPIO.output(config.LEFT_AIN2_GPIO, GPIO.HIGH)
            GPIO.output(config.RIGHT_BIN1_GPIO, GPIO.HIGH)
            GPIO.output(config.RIGHT_BIN2_GPIO, GPIO.LOW)
            self._apply_speed_locked(self.speed_pct, self.speed_pct)

    def back(self, speed_pct: int = None):
        if speed_pct is not None:
            self.set_speed(speed_pct)
        with self._lock:
            GPIO.output(config.TB6612_STBY_GPIO, GPIO.HIGH)
            GPIO.output(config.LEFT_AIN1_GPIO, GPIO.LOW)
            GPIO.output(config.LEFT_AIN2_GPIO, GPIO.HIGH)
            GPIO.output(config.RIGHT_BIN1_GPIO, GPIO.HIGH)
            GPIO.output(config.RIGHT_BIN2_GPIO, GPIO.LOW)
            self._apply_speed_locked(self.speed_pct, self.speed_pct)

    def left(self, speed_pct: int = None):
        if speed_pct is not None:
            self.set_speed(speed_pct)
        with self._lock:
            GPIO.output(config.TB6612_STBY_GPIO, GPIO.HIGH)
            GPIO.output(config.LEFT_AIN1_GPIO, GPIO.LOW)
            GPIO.output(config.LEFT_AIN2_GPIO, GPIO.HIGH)
            GPIO.output(config.RIGHT_BIN1_GPIO, GPIO.LOW)
            GPIO.output(config.RIGHT_BIN2_GPIO, GPIO.HIGH)
            self._apply_speed_locked(self.speed_pct, self.speed_pct)

    def right(self, speed_pct: int = None):
        if speed_pct is not None:
            self.set_speed(speed_pct)
        with self._lock:
            GPIO.output(config.TB6612_STBY_GPIO, GPIO.HIGH)
            GPIO.output(config.LEFT_AIN1_GPIO, GPIO.HIGH)
            GPIO.output(config.LEFT_AIN2_GPIO, GPIO.LOW)
            GPIO.output(config.RIGHT_BIN1_GPIO, GPIO.HIGH)
            GPIO.output(config.RIGHT_BIN2_GPIO, GPIO.LOW)
            self._apply_speed_locked(self.speed_pct, self.speed_pct)

    def cleanup(self):
        try:
            self.stop(brake=False)
            self.disable()
        except Exception:
            pass

