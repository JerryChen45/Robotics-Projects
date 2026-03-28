import time
import sys
from motorgo import Plink, ControlMode

LEFT_CHS = [1, 2]
RIGHT_CHS = [3, 4]
POWER = 1

def main():
    p = Plink(frequency=200, timeout=1.0)
    left = []
    right = []

    try:
        print("Connecting...")
        p.connect()
        print("Connected.")

        left = [getattr(p, f"channel{ch}") for ch in LEFT_CHS]
        right = [getattr(p, f"channel{ch}") for ch in RIGHT_CHS]

        for m in left + right:
            m.control_mode = ControlMode.POWER

        print(f"Running at power {POWER:.2f}. Ctrl+C to stop.")
        for m in left:
            m.power_command =POWER
        for m in right:
            m.power_command =-POWER

        while True:
            time.sleep(0.1)

    except KeyboardInterrupt:
        pass

    finally:
        for m in left + right:
            try:
                m.power_command = 0.0
            except Exception:
                pass

        time.sleep(0.2)
        print("Stopped motors. Exiting cleanly.")
        sys.exit(0)

if __name__ == "__main__":
    main()