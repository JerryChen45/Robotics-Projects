import sys
import time
import pigpio

# Pins to test - all usable GPIO pins on the Pi
PINS_TO_TEST = [12, 3, 4, 14, 15, 17, 18, 27, 22, 23, 24, 10, 9, 11, 25, 8, 7, 5, 6, 2, 13, 19, 16, 26, 20, 21]

TEST_PW     = 1500   # center position
WIGGLE_PW1  = 1000   # wiggle one way
WIGGLE_PW2  = 2000   # wiggle the other way
HOLD_TIME   = 0.4    # seconds to hold each position

def test_pin(pi, pin):
    """Sends a wiggle pulse to the pin so you can see/hear the servo move."""
    print(f"  Testing GPIO {pin}...", end=" ", flush=True)
    try:
        pi.set_servo_pulsewidth(pin, TEST_PW)
        time.sleep(HOLD_TIME)
        pi.set_servo_pulsewidth(pin, WIGGLE_PW1)
        time.sleep(HOLD_TIME)
        pi.set_servo_pulsewidth(pin, WIGGLE_PW2)
        time.sleep(HOLD_TIME)
        pi.set_servo_pulsewidth(pin, TEST_PW)
        time.sleep(HOLD_TIME)
        pi.set_servo_pulsewidth(pin, 0)  # turn off pulses
    except Exception as e:
        print(f"SKIP ({e})")
        return

    answer = input("Did the servo move? (y/n): ").strip().lower()
    if answer == 'y':
        return True
    return False

def main():
    print("Connecting to pigpio...")
    pi = pigpio.pi()
    if not pi.connected:
        print("Could not connect. Run: sudo pigpiod")
        sys.exit(1)
    print("Connected.\n")

    print("This script will wiggle the servo on each GPIO pin one at a time.")
    print("Watch/listen for the servo to move and press Y when it does.\n")

    found_pin = None

    for pin in PINS_TO_TEST:
        result = test_pin(pi, pin)
        if result:
            found_pin = pin
            print(f"\n✓ Servo found on GPIO {pin}!")
            break

    # Clean up all pins
    for pin in PINS_TO_TEST:
        try:
            pi.set_servo_pulsewidth(pin, 0)
        except Exception:
            pass

    pi.stop()

    if found_pin:
        print(f"\nSet SERVO_PIN = {found_pin} in your script.")
    else:
        print("\nServo not found on any pin. Check your wiring and power supply.")

if __name__ == "__main__":
    main()