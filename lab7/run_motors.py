import time
import sys
import tty
import termios
import select
from motorgo import Plink, ControlMode

LEFT_CHS   = [1, 2]
RIGHT_CHS  = [3, 4]
LEFT_DIRS  = [-1, 1]
RIGHT_DIRS = [1, 1]  # flip whichever motor is reversed: try [1, -1] if still wrong
POWER = 1
TICK = 0.05

def main():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    p = Plink(frequency=200, timeout=1.0)
    left = []
    right = []

    try:
        print("Connecting...")
        p.connect()
        print("Connected.")

        left  = [getattr(p, f"channel{ch}") for ch in LEFT_CHS]
        right = [getattr(p, f"channel{ch}") for ch in RIGHT_CHS]

        for m in left + right:
            m.control_mode = ControlMode.POWER

        def set_motors(l_pwr, r_pwr):
            for m, d in zip(left, LEFT_DIRS):
                m.power_command = l_pwr * d
            for m, d in zip(right, RIGHT_DIRS):
                m.power_command = r_pwr * d

        print("Controls (hold to move, release to stop):")
        print("  W = forward")
        print("  S = backward")
        print("  A = turn left")
        print("  D = turn right")
        print("  Q = quit")

        tty.setraw(fd)

        while True:
            last_key = None

            # drain all buffered keys, keep only the last one
            while select.select([sys.stdin], [], [], 0)[0]:
                last_key = sys.stdin.read(1).lower()

            if last_key == 'q' or last_key == '\x03':
                break
            elif last_key == 'w':
                set_motors(-POWER, -POWER)
            elif last_key == 's':
                set_motors(POWER, POWER)
            elif last_key == 'a':
                set_motors(POWER, -POWER)
            elif last_key == 'd':
                set_motors(-POWER, POWER)
            else:
                set_motors(0.0, 0.0)

            time.sleep(TICK)

    except KeyboardInterrupt:
        pass

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        for m in left + right:
            try:
                m.power_command = 0.0
            except Exception:
                pass
        time.sleep(0.2)
        print("\nStopped motors. Exiting cleanly.")
        sys.exit(0)

if __name__ == "__main__":
    main()