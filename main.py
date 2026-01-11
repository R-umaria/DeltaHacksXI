# main.py

import os
import time
import math
import json
import signal
import threading
import argparse
from typing import Dict, Any, List, Tuple

import RPi.GPIO as GPIO

import config
from controllers.motors import Motors, PWMOwnership
from sensing.sonar import SonarScanner
from mapping.occupancy_grid import OccupancyGrid
from signals.wifi_scan import WifiScanner
from ui.webapp import WebServer


class RoverState:
    def __init__(self):
        self.lock = threading.Lock()

        self.status = "idle"
        self.last_cmd = "none"

        self.auto_enabled = False
        self.speed_pct = config.DEFAULT_SPEED_PCT

        self.front_min_cm = None
        self.forward_blocked = False
        self.last_scan_ts = 0.0

        self.wifi_score = 0
        self.wifi_top = []

        # Pose (cm, cm, radians). theta=0 means facing +y.
        self.x_cm = 0.0
        self.y_cm = 0.0
        self.theta_rad = 0.0

        self.stop_requested = False


class RoverApp:
    def __init__(self):
        os.makedirs(config.STATIC_DIR, exist_ok=True)

        self.stop_event = threading.Event()
        self.state = RoverState()

        self.pwm_owner = PWMOwnership()
        self.motors = Motors(self.pwm_owner)
        self.sonar = SonarScanner(self.pwm_owner)
        self.grid = OccupancyGrid()
        self.wifi = WifiScanner(config.WIFI_INTERFACE)

        # threads
        self.wifi_thread = None
        self.auto_thread = None

        # Ensure initial map exists
        self._render_map()

    def start_background_threads(self):
        self.wifi_thread = threading.Thread(target=self._wifi_loop, daemon=True)
        self.auto_thread = threading.Thread(target=self._auto_loop, daemon=True)
        self.wifi_thread.start()
        self.auto_thread.start()

    def _wifi_loop(self):
        while not self.stop_event.is_set():
            try:
                score, top = self.wifi.scan()
                with self.state.lock:
                    self.state.wifi_score = score
                    self.state.wifi_top = top
            except Exception:
                # never crash loop
                pass
            time.sleep(config.WIFI_SCAN_PERIOD_S)

    def _auto_loop(self):
        while not self.stop_event.is_set():
            enabled = False
            with self.state.lock:
                enabled = self.state.auto_enabled

            if not enabled:
                time.sleep(0.1)
                continue

            # Stop → disable PWM (GPIO12 released) → scan → map update → move burst
            try:
                self._stop_scan_move_cycle()
            except Exception as e:
                with self.state.lock:
                    self.state.status = f"auto error: {e!s}"
                time.sleep(0.5)

    def _stop_scan_move_cycle(self):
        with self.state.lock:
            self.state.status = "auto: stopping motors"
        # ensure motors are stopped and PWM disabled before scan
        try:
            self.motors.stop(brake=False)
            self.motors.disable()
        except Exception:
            # If motors weren't enabled, it's fine
            pass

        time.sleep(0.05)

        with self.state.lock:
            self.state.status = "auto: scanning sonar"

        scan_points = self.sonar.scan()
        now = time.time()

        # Compute front min in forward sector (servo angles 80..100)
        front_min = None
        for p in scan_points:
            a = p["angle_deg"]
            if config.FRONT_SECTOR_MIN_DEG <= a <= config.FRONT_SECTOR_MAX_DEG:
                d = p["distance_cm"]
                if front_min is None or d < front_min:
                    front_min = d

        with self.state.lock:
            self.state.front_min_cm = front_min
            self.state.forward_blocked = (front_min is not None and front_min <= config.FRONT_STOP_CM)
            self.state.last_scan_ts = now

        # Update map with scan points (robot frame endpoints)
        pts_robot = [(p["x_cm"], p["y_cm"]) for p in scan_points]
        pose = self._pose_tuple()
        self.grid.update_with_scan(pose, pts_robot)
        self._render_map()

        # Move burst if safe
        with self.state.lock:
            blocked = self.state.forward_blocked
            self.state.status = "auto: moving burst" if not blocked else "auto: blocked by obstacle"

        if blocked:
            time.sleep(0.2)
            return

        # Enable motors (acquire GPIO12) and move briefly
        if not self.motors.enable():
            with self.state.lock:
                self.state.status = "auto: motor PWM busy (GPIO12)"
            time.sleep(0.2)
            return

        with self.state.lock:
            self.motors.set_speed(self.state.speed_pct)

        self.motors.forward()
        time.sleep(config.MOVE_BURST_S)
        self.motors.stop(brake=False)

        # Update pose estimate
        with self.state.lock:
            step = float(config.STEP_CM)
            th = self.state.theta_rad
            # theta=0 means forward is +y
            self.state.x_cm += step * math.sin(th)
            self.state.y_cm += step * math.cos(th)
            self.state.status = "auto: idle"

        # (Optional) keep motors enabled for manual; but next scan requires disable anyway.
        # To be conservative, disable after burst to reduce risk:
        self.motors.disable()

    def _pose_tuple(self) -> Tuple[float, float, float]:
        with self.state.lock:
            return (self.state.x_cm, self.state.y_cm, self.state.theta_rad)

    def _render_map(self):
        pose = self._pose_tuple()
        self.grid.render_png(pose, config.MAP_IMAGE_PATH)

    # -----------------------
    # Web handlers
    # -----------------------
    def get_status(self) -> Dict[str, Any]:
        with self.state.lock:
            return {
                "status": self.state.status,
                "last_cmd": self.state.last_cmd,
                "auto_enabled": self.state.auto_enabled,
                "speed_pct": self.state.speed_pct,
                "front_min_cm": self.state.front_min_cm,
                "forward_blocked": self.state.forward_blocked,
                "wifi_score": self.state.wifi_score,
                "wifi_top": self.state.wifi_top,
                "pose": {
                    "x_cm": self.state.x_cm,
                    "y_cm": self.state.y_cm,
                    "theta_deg": math.degrees(self.state.theta_rad),
                }
            }

    def toggle_auto(self, enabled: bool) -> Dict[str, Any]:
        with self.state.lock:
            self.state.auto_enabled = bool(enabled)
            self.state.status = "auto enabled" if enabled else "auto disabled"
        # If disabling, stop motors immediately
        if not enabled:
            try:
                self.motors.stop(brake=False)
                self.motors.disable()
            except Exception:
                pass
        return {"ok": True, "auto_enabled": enabled}

    def handle_command(self, cmd: str) -> Dict[str, Any]:
        cmd = (cmd or "").lower().strip()

        valid = {"forward", "back", "left", "right", "stop"}
        if cmd not in valid:
            return {"ok": False, "error": f"invalid cmd: {cmd}"}

        # Manual commands disable auto (prevents contention with scan loop)
        with self.state.lock:
            if self.state.auto_enabled:
                self.state.auto_enabled = False
                self.state.status = "auto disabled (manual override)"

        # Safety block: forward blocked if obstacle close
        if cmd == "forward":
            with self.state.lock:
                if self.state.forward_blocked:
                    self.state.last_cmd = "forward(blocked)"
                    self.state.status = f"blocked: obstacle <= {config.FRONT_STOP_CM}cm"
                    return {"ok": False, "error": "Forward blocked by obstacle safety"}

        # Enable motors (acquire GPIO12) before movement
        if cmd == "stop":
            try:
                self.motors.stop(brake=False)
                self.motors.disable()
            except Exception:
                pass
            with self.state.lock:
                self.state.last_cmd = "stop"
                self.state.status = "stopped"
            return {"ok": True}

        if not self.motors.enable():
            return {"ok": False, "error": "Motor PWM busy (GPIO12 ownership conflict)"}

        with self.state.lock:
            self.motors.set_speed(self.state.speed_pct)

        try:
            if cmd == "forward":
                self.motors.forward()
            elif cmd == "back":
                self.motors.back()
            elif cmd == "left":
                self.motors.left()
            elif cmd == "right":
                self.motors.right()
        except Exception as e:
            return {"ok": False, "error": str(e)}

        with self.state.lock:
            self.state.last_cmd = cmd
            self.state.status = f"manual: {cmd}"
        return {"ok": True}

    # -----------------------
    # CLI tests
    # -----------------------
    def motor_test(self):
        print("[motor_test] Enabling motors...")
        if not self.motors.enable():
            print("[motor_test] ERROR: motor PWM busy (GPIO12).")
            return
        self.motors.set_speed(config.DEFAULT_SPEED_PCT)

        print("[motor_test] Forward 0.5s")
        self.motors.forward()
        time.sleep(0.5)
        self.motors.stop()
        time.sleep(0.2)

        print("[motor_test] Back 0.5s")
        self.motors.back()
        time.sleep(0.5)
        self.motors.stop()
        time.sleep(0.2)

        print("[motor_test] Left spin 0.5s")
        self.motors.left()
        time.sleep(0.5)
        self.motors.stop()
        time.sleep(0.2)

        print("[motor_test] Right spin 0.5s")
        self.motors.right()
        time.sleep(0.5)
        self.motors.stop()
        time.sleep(0.2)

        print("[motor_test] Disabling motors...")
        self.motors.disable()
        print("[motor_test] Done.")

    def sonar_test(self):
        print("[sonar_test] Ensuring motors disabled (GPIO12 free)...")
        try:
            self.motors.stop()
            self.motors.disable()
        except Exception:
            pass

        print("[sonar_test] Running scan...")
        pts = self.sonar.scan()
        print(f"[sonar_test] Got {len(pts)} points.")
        for p in pts[:15]:
            print(f"  angle={p['angle_deg']:.0f} dist={p['distance_cm']:.1f}cm bearing={p['bearing_deg']:+.1f}°")

        # Update map once
        pose = self._pose_tuple()
        pts_robot = [(p["x_cm"], p["y_cm"]) for p in pts]
        self.grid.update_with_scan(pose, pts_robot)
        self._render_map()
        print(f"[sonar_test] Map written to: {config.MAP_IMAGE_PATH}")

    # -----------------------
    # Shutdown / cleanup
    # -----------------------
    def shutdown(self):
        self.stop_event.set()
        with self.state.lock:
            self.state.status = "shutting down"
        try:
            self.motors.stop(brake=False)
            self.motors.disable()
        except Exception:
            pass
        try:
            GPIO.cleanup()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--motor-test", action="store_true", help="Run quick motor test and exit")
    parser.add_argument("--sonar-test", action="store_true", help="Run sonar sweep test and exit")
    args = parser.parse_args()

    app = RoverApp()

    def handle_sigint(sig, frame):
        app.shutdown()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    # CLI tests
    if args.motor_test:
        app.motor_test()
        app.shutdown()
        return

    if args.sonar_test:
        app.sonar_test()
        app.shutdown()
        return

    # Normal operation
    app.start_background_threads()

    server = WebServer(
        state_provider=app.get_status,
        command_handler=app.handle_command,
        toggle_handler=app.toggle_auto
    )

    print(f"[main] Dashboard: http://<pi-ip>:{config.WEB_PORT}")
    print("[main] Run as root for Wi-Fi scanning: sudo python3 main.py")

    try:
        server.app.run(host=config.WEB_HOST, port=config.WEB_PORT, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
