# SAR-Scope — Teleoperated Search & Rescue Rover (DeltaHacks 12)

SAR-Scope is a low-cost, teleoperated search-and-rescue rover designed for **GPS-denied** and **low-visibility** environments (e.g., post-earthquake indoor rubble, smoke-filled rooms, flooded basements). It streams **live video** to an operator while providing **real-time proximity awareness**, a **local risk map**, and optional **victim-beacon + hazard sensing** to help responders navigate safely and make faster decisions.

## Problem
In disaster scenarios, responders often face:
- **Limited visibility** and unknown terrain
- **GPS-unavailable indoor spaces**
- **High-risk navigation** (tight passages, debris, unstable obstacles)
- **Time pressure** to locate victims and avoid hazards

A human operator may be able to drive a robot into these areas—but raw video alone isn’t enough. Operators need additional sensing to avoid collisions and detect signals of life.

## Solution
SAR-Scope combines:
- **Teleoperation + live camera feed**
- **4-way ultrasonic proximity sensing** (front/left/right/rear)
- **Collision-safety gating** (the robot prevents unsafe movements)
- **Real-time operator dashboard** with radar-style proximity visualization and a robot-centric local risk map
- **Optional victim beacon detection** using Wi-Fi/BLE signal strength (phone as a beacon)
- **Optional environmental sensing** (temperature/humidity) for hazard awareness

## What it does
### Operator Experience
From a laptop browser, an operator can:
- Drive the rover using keyboard controls (WASD) or joystick (optional)
- View a **live video stream** from the rover
- Monitor proximity readings and warnings in real time
- See a **local “risk map”** around the robot (robot-centric occupancy view)
- Trigger a **“Locate Victim” scan** (optional): the rover rotates and plots signal strength to suggest the best direction to search
- View hazard readings (temperature/humidity) if enabled

### Robot Behavior
- Continuously reads **ultrasonic distances** in four directions
- Enforces safety thresholds (e.g., blocks forward motion if an obstacle is too close)
- Streams telemetry to the dashboard at a steady update rate
- Logs mission data (telemetry + commands) for analysis/replay

## What we are achieving
Our goals for DeltaHacks 12:
1. **A reliable end-to-end demo**: rover drives through a cardboard “disaster maze” with live video + sensing.
2. **Operator-grade situational awareness**: not just a camera, but real-time proximity + risk indicators.
3. **Actionable intelligence beyond driving**:
   - collision-safe teleop
   - optional victim beacon hinting (RSSI-based)
   - optional hazard sensing (temp/humidity)
4. **A clear social-impact narrative**: faster, safer remote assessment in hazardous conditions.

## How we are doing it (High-level architecture)
### Hardware
- **Raspberry Pi 4B** (Primary compute)
  - Hosts the web dashboard and video stream
  - Bridges control commands to the motor controller
  - Receives telemetry and renders the live UI
  - Performs logging and optional sensor fusion/visualization
- **Arduino Uno/Nano** (Real-time control)
  - Reads 4 ultrasonic sensors reliably (timing-sensitive)
  - Drives motors via motor driver (PWM)
  - Sends distance telemetry to the Pi over serial
  - (Optional) applies local safety gating as a fail-safe
- **ESP32** (Optional: victim beacon module)
  - Scans Wi-Fi / BLE and reports RSSI of a target beacon (e.g., phone hotspot)
  - Streams RSSI readings to the Pi for visualization and “Locate Victim” scan
- **Sensors**
  - 4× Ultrasonic sensors (front/left/right/rear)
  - (Optional) Temp/Humidity sensor (I2C) for hazard indication
- **Camera**
  - Pi Camera module or USB webcam mounted on rover

### Software
- **Pi (Python)**
  - Web server (Flask/FastAPI) for dashboard + control endpoints
  - WebSockets for real-time control and telemetry
  - MJPEG (or similar) low-latency video streaming
  - Telemetry logging (CSV/JSON)
- **Dashboard (HTML/JS)**
  - Live video panel
  - Proximity radar widgets (front/left/right/rear)
  - Robot-centric local risk map (occupancy grid around rover)
  - Beacon strength plot + direction suggestion (optional)
  - Hazard panel (temp/humidity) (optional)
- **Arduino (C/C++)**
  - Non-blocking ultrasonic reads with timeouts + smoothing
  - Motor control (differential drive)
  - Serial protocol for telemetry and motor commands
- **ESP32 (Arduino/ESP-IDF) (Optional)**
  - Wi-Fi/BLE scanning loop
  - RSSI reporting to Pi

## Demo plan
We will build a **cardboard disaster maze** representing rubble/blocked corridors:
1. Operator drives rover into the maze using the live camera feed.
2. Ultrasonic radar prevents collisions and helps navigate tight spaces.
3. Dashboard displays a local risk map as the rover explores.
4. (Optional) “Locate Victim” scan identifies strongest phone beacon direction.
5. Rover reaches a marked “victim zone” and flags detection + logs telemetry.

## Repository structure (suggested)
