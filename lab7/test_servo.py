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
TICK = 1

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
        print("Setting initial pulse width...")
        pw = MIN_PW
        direction = 1
        pi.set_servo_pulsewidth(SERVO_PIN, pw)
        print(f"Initial pw set to {pw}")

        print("Claw control ready:")
        print("  S = reverse direction")
        print("  Q = quit")

        tty.setraw(fd)

        while True:
            if select.select([sys.stdin], [], [], TICK)[0]:
                key = sys.stdin.read(1).lower()
                if key == 'q' or key == '\x03':
                    break
                elif key == 's':
                    direction *= -1

            pw = clip(pw + direction * STEP, MIN_PW, MAX_PW)

            if pw == MIN_PW or pw == MAX_PW:
                direction *= -1

            pi.set_servo_pulsewidth(SERVO_PIN, pw)
            print(f"\rpw: {pw}  dir: {'>' if direction > 0 else '<'}    ", end="")

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