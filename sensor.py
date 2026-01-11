import RPi.GPIO as GPIO
import time
import math
import matplotlib as plt

# ---------------- GPIO SETUP ----------------
GPIO.setmode(GPIO.BCM)

TRIG = 23
ECHO = 24

LEFT_FWD = 5
LEFT_REV = 6
RIGHT_FWD = 13
RIGHT_REV = 19

GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)

for pin in [LEFT_FWD, LEFT_REV, RIGHT_FWD, RIGHT_REV]:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, False)

# ---------------- PARAMETERS ----------------
FULL_ROTATION_TIME = 3.6      # seconds for 360° spin (calibrate!)
SCAN_RESOLUTION = 36          # number of angle samples, turn this shit up for higher resolution
SAFE_DISTANCE = 40            # cm
FORWARD_TIME = 1.0            # seconds to move forward

# ---------------- MOTOR CONTROL ----------------
def stop():
    for pin in [LEFT_FWD, LEFT_REV, RIGHT_FWD, RIGHT_REV]:
        GPIO.output(pin, False)

def spin_left():
    GPIO.output(LEFT_FWD, True)
    GPIO.output(RIGHT_REV, True)

def drive_forward():
    GPIO.output(LEFT_FWD, True)
    GPIO.output(RIGHT_FWD, True)

# ---------------- ULTRASONIC ---------------- # WORKS
def get_distance():
    GPIO.output(TRIG, False)
    time.sleep(0.0002)
    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    start = time.time()
    while GPIO.input(ECHO) == 0:
        start = time.time()  # wait for echo to start

    end = start
    while GPIO.input(ECHO) == 1:
        end = time.time()  # wait for echo to end

    duration = end - start
    distance = (duration * 34300) / 2  # speed of sound in cm/s

    # ---------- LOGGING ----------
    print(f"[DEBUG] Raw duration: {duration:.6f} s, Distance: {distance:.1f} cm")

    return min(distance, 300)  # cap extreme/noisy values


def init_plot():
    plt.ion()
    fig, ax = plt.subplots()
    ax.set_xlim(-400, 400)
    ax.set_ylim(-400, 400)
    ax.set_xlabel("X (cm)")
    ax.set_ylabel("Y (cm)")
    ax.set_title("Live Ultrasonic Map")
    ax.grid(True)
    return fig, ax


def plot_point(ax, x, y):
    ax.scatter(x, y, c="red", s=20)
    plt.pause(0.01)


# ---------------- SCAN ENVIRONMENT ----------------
def scan_environment(ax=None):
    scan = []
    step_time = FULL_ROTATION_TIME / SCAN_RESOLUTION

    spin_left()

    for i in range(SCAN_RESOLUTION):
        time.sleep(step_time)

        distance = get_distance()
        angle = (i / SCAN_RESOLUTION) * 360

        # Polar → Cartesian
        rad = math.radians(angle)
        x = distance * math.cos(rad)
        y = distance * math.sin(rad)

        scan.append((angle, distance))

        # Plot if axis provided
        if ax is not None:
            plot_point(ax, x, y)

    stop()
    return scan

# ---------------- TURN TO ANGLE ----------------
def turn_to_angle(target_angle):
    turn_time = (target_angle / 360) * FULL_ROTATION_TIME
    spin_left()
    time.sleep(turn_time)
    stop()

# ---------------- MAIN LOOP ----------------
'''
try:
    while True:
        get_distance()
        time.sleep(0.5)
finally:
    GPIO.cleanup()
'''


# sudo apt install -y python3-matplotlib - RUN THIS SHIT BEFORE
try:
    fig, ax = init_plot()
    print("Starting scan...")
    scan_data = scan_environment(ax=ax)
    print("Scan complete")

    plt.ioff()
    plt.show()

finally:
    GPIO.cleanup()



'''
try:
    while True:
        print("Scanning...")
        scan = scan_environment()

        direction, clearance = choose_direction(scan)
        print(f"Best direction: {direction}°, clearance: {clearance:.1f}cm")

        if clearance < SAFE_DISTANCE:
            print("No safe path — rotating slowly")
            spin_left()
            time.sleep(0.5)
            stop()
            continue

        print("Turning...")
        turn_to_angle(direction)

        print("Moving forward")
        drive_forward()
        time.sleep(FORWARD_TIME)
        stop()

except KeyboardInterrupt:
    print("Stopping robot")
    stop()
    GPIO.cleanup()
'''

'''
# ---------------- DECISION MAKING ----------------
def choose_direction(scan):
    # Divide into sectors
    sectors = {}
    for angle, dist in scan:
        sector = int(angle // 30) * 30
        if sector not in sectors:
            sectors[sector] = []
        sectors[sector].append(dist)

    # Compute average distance per sector
    best_sector = None
    best_clearance = 0

    for sector, distances in sectors.items():
        avg = sum(distances) / len(distances)
        if avg > best_clearance:
            best_clearance = avg
            best_sector = sector

    return best_sector, best_clearance
'''
