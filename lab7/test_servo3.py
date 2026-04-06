import sys
import tty
import termios
import select
import time
import pigpio

SERVO_PIN = 17
MIN_PW = 500
MAX_PW = 2500
TICK = 0.02

# Trapezoid profile settings
RAMP_STEPS  = 10      # how many steps to ramp up/down over
MIN_STEP    = 10      # smallest step size (start/end of move)
MAX_STEP    = 150     # largest step size (middle of move)
STEP_DELAY  = 0.02    # seconds between each step

def clip(x, lo, hi):
    return max(lo, min(hi, x))

def trapezoid_move(pi, current_pw, target_pw):
    """Move servo from current_pw to target_pw with trapezoid velocity profile."""
    if current_pw == target_pw:
        return current_pw

    distance = abs(target_pw - current_pw)
    direction = 1 if target_pw > current_pw else -1

    # Build the ramp profile: ramp up, cruise, ramp down
    # Each entry is a step size
    ramp_up   = [MIN_STEP + (MAX_STEP - MIN_STEP) * i // RAMP_STEPS for i in range(RAMP_STEPS)]
    ramp_down = list(reversed(ramp_up))
    cruise    = [MAX_STEP]

    # Full trapezoid step profile
    profile = ramp_up + cruise * max(0, (distance - sum(ramp_up) - sum(ramp_down)) // MAX_STEP) + ramp_down

    pw = current_pw
    for step in profile:
        if direction > 0:
            pw = clip(pw + step, MIN_PW, target_pw)
        else:
            pw = clip(pw - step, target_pw, MAX_PW)
        pi.set_servo_pulsewidth(SERVO_PIN, pw)
        print(f"\rpw: {pw}  ", end="", flush=True)
        time.sleep(STEP_DELAY)
        if pw == target_pw or pw == MIN_PW or pw == MAX_PW:
            break

    return pw

def main():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    print("Connecting to pigpio...")
    pi = pigpio.pi()
    if not pi.connected:
        print("Could not connect. Run: sudo pigpiod")
        sys.exit(1)
    print("Connected.")

    try:
        pw = pi.get_servo_pulsewidth(SERVO_PIN)
        if pw <= 0:
            pw = 1500
    except pigpio.error:
        pw = 1500
    print("1 = +25deg (trapezoid) | 2 = -25deg (trapezoid) | Q = quit")
    print(f"\rpw: {pw}    ", end="", flush=True)

    MOVE_AMOUNT = 100  # ~9 degrees per press

    try:
        tty.setraw(fd)

        while True:
            if select.select([sys.stdin], [], [], TICK)[0]:
                key = sys.stdin.read(1).lower()
                if key in ('q', '\x03'):
                    break
                elif key == '1':
                    target = clip(pw + MOVE_AMOUNT, MIN_PW, MAX_PW)
                    pw = trapezoid_move(pi, pw, target)
                elif key == '2':
                    target = clip(pw - MOVE_AMOUNT, MIN_PW, MAX_PW)
                    pw = trapezoid_move(pi, pw, target)

    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        pi.set_servo_pulsewidth(SERVO_PIN, 0)
        pi.stop()
        time.sleep(0.2)
        print("\nServo stopped. Exiting.")
        sys.exit(0)

if __name__ == "__main__":
    main()
