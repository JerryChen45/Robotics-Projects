import time
import sys
from motorgo import Plink, ControlMode

LEFT_CH = 1
RIGHT_CH = 3
POWER = 0.9

def main():
    p = Plink(frequency=200, timeout=1.0)
    left = None
    right = None

    try:
        print("Connecting...")
        p.connect()
        print("Connected.")

        left = getattr(p, f"channel{LEFT_CH}")
        right = getattr(p, f"channel{RIGHT_CH}")

        left.control_mode = ControlMode.POWER
        right.control_mode = ControlMode.POWER

        left.power_command = -POWER
        right.power_command = POWER

        print(f"Running at {POWER} power. Ctrl+C to stop.")

        while True:
            time.sleep(0.1)

    except KeyboardInterrupt:
        pass

    finally:
        try:
            if left is not None:
                left.power_command = 0.0
            if right is not None:
                right.power_command = 0.0
        except Exception:
            pass
        time.sleep(0.2)
        print("\nStopped motors. Exiting cleanly.")
        sys.exit(0)

if __name__ == "__main__":
    main()