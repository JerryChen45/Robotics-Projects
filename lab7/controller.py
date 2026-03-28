"""
button 0 = A
button 1 = B
button 2 = X
button 3 = Y
button 4 = view
button 5 = xbox
button 6 = menu
button 7 = left stick click
button 8 = right stick click
button 9 = LB
button 10 = RB
button 11 = up
button 12 = down
button 13 = left
button 14 = right

AXIS_LX = 0   # left stick left -1 /right 1
AXIS_LY = 1   # left stick up -1 /down 1
AXIS_RX = 2   # right stick  left -1 /right 1
AXIS_RY = 3   # right stick up -1 /down 1
AXIS_LT = 4   # left trigger, rest=-1.0, pressed=1.0
AXIS_RT = 5   # right trigger, rest=-1.0, pressed=1.0
"""
import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
import time
import sys
import pygame
from motorgo import Plink, ControlMode

LEFT_CHS = [1, 2]
RIGHT_CHS = [3, 4]
AXIS_LX = 0
AXIS_LY = 1
DEADZONE = 0.1

def clip(x, lo, hi):
    return lo if x < lo else hi if x > hi else x

def main():
    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print("No controller detected.")
        sys.exit(1)

    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    print(f"Connected controller: {joystick.get_name()}")

    p = Plink(frequency=200, timeout=1.0)
    left = []
    right = []

    try:
        print("Connecting to motors...")
        p.connect()
        print("Connected.")

        left = [getattr(p, f"channel{ch}") for ch in LEFT_CHS]
        right = [getattr(p, f"channel{ch}") for ch in RIGHT_CHS]

        for m in left + right:
            m.control_mode = ControlMode.POWER

        print("Drive with left joystick. Ctrl+C to stop.")

        while True:
            pygame.event.pump()

            ly = joystick.get_axis(AXIS_LY)
            lx = joystick.get_axis(AXIS_LX)

            if abs(ly) < DEADZONE:
                ly = 0.0
            if abs(lx) < DEADZONE:
                lx = 0.0

            # Joystick up is -1, so negate for forward = positive
            fwd = -ly
            turn = lx

            # Mix: left side slows on right turn, right side slows on left turn
            left_pwr = clip(fwd - turn, -1.0, 1.0)
            right_pwr = clip(fwd + turn, -1.0, 1.0)

            for m in left:
                m.power_command = left_pwr
            for m in right:
                m.power_command = -right_pwr

            print(f"\rL: {left_pwr:+.2f}  R: {right_pwr:+.2f}  ", end="")
            time.sleep(0.02)

    except KeyboardInterrupt:
        pass

    finally:
        for m in left + right:
            try:
                m.power_command = 0.0
            except Exception:
                pass

        time.sleep(0.2)
        pygame.quit()
        print("\nStopped motors. Exiting cleanly.")
        sys.exit(0)

if __name__ == "__main__":
    main()