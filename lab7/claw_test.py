import time
import sys
import tty
import termios
import select
from motorgo import Plink, ControlMode

CLAW_CH = 4
CLAW_POWER = 0.95

def main():
    p = Plink(frequency=200, timeout=1.0)
    claw = None
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        print("Connecting...")
        p.connect()
        print("Connected.")

        claw = getattr(p, f"channel{CLAW_CH}")
        claw.control_mode = ControlMode.POWER

        print("Claw control ready:")
        print("  Hold W = open")
        print("  Hold S = close")
        print("  Release = stop")
        print("  Q = quit")

        tty.setraw(fd)

        while True:
            if select.select([sys.stdin], [], [], 0.05)[0]:
                key = sys.stdin.read(1).lower()
                if key == 'q' or key == '\x03':
                    break
                elif key == 'w':
                    claw.power_command = -CLAW_POWER
                elif key == 's':
                    claw.power_command = CLAW_POWER
            else:
                claw.power_command = 0.0

    except KeyboardInterrupt:
        pass

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        if claw is not None:
            try:
                claw.power_command = 0.0
            except Exception:
                pass

        time.sleep(0.2)
        print("\nClaw stopped. Exiting cleanly.")
        sys.exit(0)

if __name__ == "__main__":
    main()