# Disaster-Response Rover (Raspberry Pi 4B)

A Raspberry Pi OS–runnable Python 3 rover stack that:
1) Teleoperates via a simple Flask web dashboard  
2) Scans obstacles using HC-SR04 mounted on an SG90 servo  
3) Builds a local 2D obstacle map (occupancy grid + point overlay)  
4) Estimates “possible human nearby” using Wi-Fi scanning (RSSI / device activity score)

## Critical Pin Constraint (MUST READ)
GPIO12 is shared:
- Servo signal: GPIO12
- TB6612FNG LEFT motor PWMA: GPIO12

This code enforces an explicit PWM ownership lock so:
- Motors are fully stopped and motor PWM is disabled before sonar scanning begins
- Servo PWM exists only during scanning, then is stopped and released
- Motor PWM is re-enabled only after scanning completes
- Servo PWM and motor PWM are never active on GPIO12 at the same time

## Pin Map (BCM) — as implemented
- Servo: GPIO12
- HC-SR04 TRIG: GPIO23
- HC-SR04 ECHO: GPIO24 (must be reduced to 3.3V with a voltage divider)
- TB6612FNG:
  - STBY: GPIO25
  - LEFT: PWMA GPIO12, AIN1 GPIO5, AIN2 GPIO6
  - RIGHT: PWMB GPIO13, BIN1 GPIO20, BIN2 GPIO21

## Installation (Raspberry Pi OS)
1) Update packages:
```bash
sudo apt update
sudo apt install -y python3-pip python3-pil
```
2) install python deps:
```pip3 install flask pillow```

Notes:

RPi.GPIO is typically preinstalled on Raspberry Pi OS.

Wi-Fi scanning via iw dev wlan0 scan usually requires root.

Wiring Notes

HC-SR04 ECHO must go through a voltage divider to 3.3V before connecting to GPIO24.

TB6612FNG requires proper VM motor supply and common ground with Raspberry Pi.

Running

Always run with sudo for Wi-Fi scanning stability:

sudo python3 main.py


Open:
http://<pi-ip>:5000

Troubleshooting

If motors do not move:

Confirm TB6612 STBY is HIGH (code sets it when enabled)

Confirm motor power supply is connected and GND is shared

Confirm AIN/BIN pins match wiring

If servo jitters:

Ensure adequate 5V supply for servo (do not power SG90 from Pi 5V if brownouts occur)

Increase SERVO_SETTLE_S in config.py

If Wi-Fi scan is empty:

Ensure wlan0 exists: ip a

Ensure iw is available: which iw

Run as sudo

File Layout

config.py

controllers/motors.py

sensing/sonar.py

mapping/occupancy_grid.py

signals/wifi_scan.py

ui/webapp.py

main.py

static/map.png (generated at runtime)

Safety

Forward motion is blocked when the latest scan indicates an obstacle <= FRONT_STOP_CM in the forward sector (angles 80..100).

Manual commands disable autonomous mode to prevent PWM contention on GPIO12.


---

# How to run and test in order

1) **Motor test**
```bash
sudo python3 main.py --motor-test


Sonar scan test

sudo python3 main.py --sonar-test


3. Run main dashboard

sudo python3 main.py


Open:
http://<pi-ip>:5000