import time
import sys
import tty
import termios
import select
import pigpio

SERVO_PIN = 14
MIN_PW = 500
MAX_PW = 2500
STEP = 50

def clip(x, lo, hi):
    return lo if x < lo else hi if x > hi else x

def main():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    print("Connecting to pigpio...")
    pi = pigpio.pi()
    print(f"Connected: {pi.connected}")

    if not pi.connected:
        print("Could not connect to pigpio daemon. Run: sudo pigpiod")
        sys.exit(1)

    try:
        pw = 1500  # start in the middle
        pi.set_servo_pulsewidth(SERVO_PIN, pw)

        print("Claw control ready:")
        print("  A = open")
        print("  D = close")
        print("  Q = quit")

        tty.setraw(fd)

        while True:
            if select.select([sys.stdin], [], [], 0.05)[0]:
                key = sys.stdin.read(1).lower()
                if key == 'q' or key == '\x03':
                    break
                elif key == 'a':
                    pw = clip(pw - STEP, MIN_PW, MAX_PW)
                    pi.set_servo_pulsewidth(SERVO_PIN, pw)
                elif key == 'd':
                    pw = clip(pw + STEP, MIN_PW, MAX_PW)
                    pi.set_servo_pulsewidth(SERVO_PIN, pw)

            print(f"\rpw: {pw}    ", end="")

    except KeyboardInterrupt:
        pass
    except Exception as e:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print(f"\nError: {e}")

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        try:
            if pi.connected:
                pi.set_servo_pulsewidth(SERVO_PIN, 0)
                pi.stop()
        except Exception:
            pass
        time.sleep(0.2)
        print("\nClaw stopped. Exiting cleanly.")
        sys.exit(0)

if __name__ == "__main__":
    main()