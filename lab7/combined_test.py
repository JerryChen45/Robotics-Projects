"""
combined_test.py  –  runs ON THE PI
  • Captures camera, runs arrow + ball detection, controls motors
  • Open  http://172.26.230.193:8081  in your browser to:
      – watch the live annotated feed
      – drive with WASD keys
      – press O/P to toggle CV overlay
      – press I to toggle auto-drive mode

Auto-drive state machine (activated with 'i'):
  IDLE    → detects blue arrow → TURNING (toward arrow direction)
  TURNING → turns until red ball is centred in frame → DRIVING
  DRIVING → drives forward toward ball (stops if ball is lost)
"""

import cv2
import numpy as np
import time
import sys
import tty
import termios
import select
import threading
import queue
import pigpio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from motorgo import Plink, ControlMode

# ── Config ─────────────────────────────────────────────────────────────────────
STREAM_PORT = 8080

# Servo
SERVO_PIN   = 17
MIN_PW      = 500
MAX_PW      = 2500
RAMP_STEPS  = 10
MIN_STEP    = 10
MAX_STEP    = 150
STEP_DELAY  = 0.02
MOVE_AMOUNT = 100  # ~9 degrees per press

LEFT_CHS   = [1, 2]
RIGHT_CHS  = [3, 4]
LEFT_DIRS  = [-1, 1]
RIGHT_DIRS = [1, 1]
POWER      = 1.0
TICK       = 0.05

# Blue arrow detection (HSV)
ARROW_HSV_LO = np.array([95, 100, 100])
ARROW_HSV_HI = np.array([115, 255, 255])
ARROW_MIN_PX = 300          # minimum pixel count to count as a detection

# Red ball detection (HSV — red wraps around 0/180)
BALL_HSV_LO1 = np.array([0,   120, 60])
BALL_HSV_HI1 = np.array([10,  255, 255])
BALL_HSV_LO2 = np.array([170, 120, 60])
BALL_HSV_HI2 = np.array([180, 255, 255])
BALL_MIN_AREA = 400         # minimum contour area to count as ball

# Auto-drive tuning
TURN_POWER    = 0.45        # power while rotating to centre ball
DRIVE_POWER   = 0.5         # power while driving toward ball
CENTER_BAND   = 0.15        # fraction of frame width = "centred"

# ── Servo helpers ──────────────────────────────────────────────────────────────
def clip(x, lo, hi):
    return max(lo, min(hi, x))

def trapezoid_move(pi, current_pw, target_pw):
    if current_pw == target_pw:
        return current_pw
    distance  = abs(target_pw - current_pw)
    direction = 1 if target_pw > current_pw else -1
    ramp_up   = [MIN_STEP + (MAX_STEP - MIN_STEP) * i // RAMP_STEPS for i in range(RAMP_STEPS)]
    ramp_down = list(reversed(ramp_up))
    profile   = ramp_up + [MAX_STEP] * max(0, (distance - sum(ramp_up) - sum(ramp_down)) // MAX_STEP) + ramp_down
    pw = current_pw
    for step in profile:
        if direction > 0:
            pw = clip(pw + step, MIN_PW, target_pw)
        else:
            pw = clip(pw - step, target_pw, MAX_PW)
        pi.set_servo_pulsewidth(SERVO_PIN, pw)
        time.sleep(STEP_DELAY)
        if pw == target_pw or pw == MIN_PW or pw == MAX_PW:
            break
    return pw

# ── Shared state ───────────────────────────────────────────────────────────────
latest_jpg = None
frame_lock = threading.Lock()

current_key = ""
key_lock    = threading.Lock()

running   = True
cv_active = False

# Servo
servo_pw    = 1500
servo_lock  = threading.Lock()
servo_queue = queue.Queue()

# Auto-drive
auto_lock      = threading.Lock()
auto_mode      = False          # toggled by 'i'
auto_state     = "idle"         # "idle" | "turning" | "driving"
turn_dir       = "right"        # "left" | "right"
ball_cx        = -1             # x-centre of detected red ball (-1 = none)
frame_w        = 640            # updated by camera thread
last_arrow_dir = None           # last detected arrow direction ("left" | "right")

# ── HTML page ──────────────────────────────────────────────────────────────────
HTML = b"""<!DOCTYPE html>
<html>
<head>
  <title>Robot Control</title>
  <style>
    body { background:#111; color:#eee; font-family:monospace;
           display:flex; flex-direction:column; align-items:center; margin:0; padding:20px; }
    h2   { margin-bottom:10px; }
    img  { border:2px solid #444; max-width:100%; }
    #keys { display:grid; grid-template-columns:repeat(3,60px);
            grid-template-rows:repeat(2,60px); gap:6px; margin-top:16px; }
    .key { display:flex; align-items:center; justify-content:center;
           background:#333; border:2px solid #555; border-radius:8px;
           font-size:1.4rem; cursor:default; user-select:none; }
    .key.active { background:#4caf50; border-color:#81c784; }
    #servo-controls { display:flex; gap:10px; margin-top:12px; align-items:center; }
    .servo-btn { display:flex; align-items:center; justify-content:center;
                 width:60px; height:60px; background:#333; border:2px solid #555;
                 border-radius:8px; font-size:1.4rem; cursor:pointer; user-select:none; }
    .servo-btn:active { background:#e65100; border-color:#ff8a65; }
    #servo-label { font-size:0.85rem; color:#aaa; }
    .badges { display:flex; gap:10px; margin-top:10px; }
    .badge { font-size:0.9rem; padding:4px 12px; border-radius:6px;
             background:#333; border:2px solid #555; }
    #cv-status.on   { background:#1565c0; border-color:#42a5f5; color:#fff; }
    #auto-status.on { background:#6a1b9a; border-color:#ce93d8; color:#fff; }
    #status { margin-top:8px; font-size:0.85rem; color:#aaa; }
  </style>
</head>
<body>
  <h2>Robot Camera Feed</h2>
  <img src="/stream" />
  <div id="keys">
    <div></div>
    <div class="key" id="kW">W</div>
    <div></div>
    <div class="key" id="kA">A</div>
    <div class="key" id="kS">S</div>
    <div class="key" id="kD">D</div>
  </div>
  <div id="servo-controls">
    <div class="servo-btn" id="sBtn1" onmousedown="servoPress('1')" ontouchstart="servoPress('1')">1</div>
    <span id="servo-label">Servo</span>
    <div class="servo-btn" id="sBtn2" onmousedown="servoPress('2')" ontouchstart="servoPress('2')">2</div>
  </div>
  <div class="badges">
    <div class="badge" id="cv-status">CV: OFF</div>
    <div class="badge" id="auto-status">AUTO: OFF</div>
    <div class="badge" id="confirm-btn" style="cursor:pointer;" onclick="confirmArrow()">C: Confirm Arrow</div>
  </div>
  <div id="status">WASD to drive &nbsp;|&nbsp; O/P toggle CV &nbsp;|&nbsp; I toggle auto-drive &nbsp;|&nbsp; C confirm arrow</div>
  <script>
    const MAP = { w:'kW', a:'kA', s:'kS', d:'kD' };
    const held = new Set();

    function sendKey(k) {
      fetch('/key?k=' + encodeURIComponent(k)).catch(()=>{});
    }
    function setCv(on) {
      fetch('/cv?on=' + (on ? '1' : '0')).catch(()=>{});
      const el = document.getElementById('cv-status');
      el.textContent = 'CV: ' + (on ? 'ON' : 'OFF');
      el.classList.toggle('on', on);
    }
    function toggleAuto() {
      fetch('/auto').then(r => r.json()).then(d => {
        const el = document.getElementById('auto-status');
        el.textContent = 'AUTO: ' + (d.auto ? 'ON' : 'OFF');
        el.classList.toggle('on', d.auto);
      }).catch(()=>{});
    }

    function confirmArrow() {
      fetch('/confirm').then(r => r.json()).then(d => {
        const el = document.getElementById('confirm-btn');
        el.textContent = d.ok ? 'Turning: ' + d.dir.toUpperCase() : 'No arrow!';
        setTimeout(() => { el.textContent = 'C: Confirm Arrow'; }, 2000);
      }).catch(()=>{});
    }

    function servoPress(k) {
      fetch('/key?k=' + k).catch(()=>{});
    }

    document.addEventListener('keydown', e => {
      if (e.key === '1') { servoPress('1'); return; }
      if (e.key === '2') { servoPress('2'); return; }
      if (e.key.toLowerCase() === 'c') { confirmArrow(); return; }
      const k = e.key.toLowerCase();
      if (k === 'o') { e.preventDefault(); setCv(true);   return; }
      if (k === 'p') { e.preventDefault(); setCv(false);  return; }
      if (k === 'i') { e.preventDefault(); toggleAuto();  return; }
      if (!(k in MAP) || held.has(k)) return;
      e.preventDefault();
      held.add(k);
      document.getElementById(MAP[k]).classList.add('active');
      sendKey(k);
    });

    document.addEventListener('keyup', e => {
      const k = e.key.toLowerCase();
      if (!(k in MAP)) return;
      e.preventDefault();
      held.delete(k);
      document.getElementById(MAP[k]).classList.remove('active');
      sendKey('');
    });
  </script>
</body>
</html>
"""

# ── HTTP handler ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML)

        elif parsed.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type",
                             "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while running:
                    with frame_lock:
                        jpg = latest_jpg
                    if jpg is not None:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n")
                        self.wfile.write(jpg)
                        self.wfile.write(b"\r\n")
                    time.sleep(0.033)
            except (BrokenPipeError, ConnectionResetError):
                pass

        elif parsed.path == "/key":
            k = parse_qs(parsed.query).get("k", [""])[0].lower()
            if k in ('1', '2'):
                with servo_lock:
                    current = servo_pw
                target = clip(current + MOVE_AMOUNT, MIN_PW, MAX_PW) if k == '1' \
                    else clip(current - MOVE_AMOUNT, MIN_PW, MAX_PW)
                servo_queue.put(target)
            else:
                with key_lock:
                    global current_key
                    current_key = k
            self.send_response(204)
            self.end_headers()

        elif parsed.path == "/confirm":
            import json
            global auto_mode, auto_state, turn_dir
            with auto_lock:
                if last_arrow_dir:
                    turn_dir   = last_arrow_dir
                    auto_mode  = True
                    auto_state = "turning"
                    result = {"ok": True, "dir": last_arrow_dir}
                else:
                    result = {"ok": False}
            body = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif parsed.path == "/cv":
            global cv_active
            cv_active = parse_qs(parsed.query).get("on", ["0"])[0] == "1"
            self.send_response(204)
            self.end_headers()

        elif parsed.path == "/auto":
            global auto_mode, auto_state
            with auto_lock:
                auto_mode = not auto_mode
                if not auto_mode:
                    auto_state = "idle"
                state = auto_mode
            import json
            body = json.dumps({"auto": state}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_):
        pass


# ── Servo thread ───────────────────────────────────────────────────────────────
def servo_loop(pi):
    global servo_pw
    while running:
        try:
            target = servo_queue.get(timeout=0.1)
            with servo_lock:
                current = servo_pw
            new_pw = trapezoid_move(pi, current, target)
            with servo_lock:
                servo_pw = new_pw
        except queue.Empty:
            pass

# ── Camera thread ──────────────────────────────────────────────────────────────
def camera_loop(cap):
    global latest_jpg, frame_w, auto_state, turn_dir, ball_cx, last_arrow_dir

    while running:
        ret, frame = cap.read()
        if not ret:
            continue

        h, w = frame.shape[:2]
        frame_w = w

        if cv_active:
            blurred = cv2.GaussianBlur(frame, (7, 7), 0)
            hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

            # ── Blue arrow detection ──────────────────────────────────────────
            arrow_mask = cv2.inRange(hsv, ARROW_HSV_LO, ARROW_HSV_HI)
            arrow_contours, _ = cv2.findContours(arrow_mask, cv2.RETR_EXTERNAL,
                                                 cv2.CHAIN_APPROX_SIMPLE)
            detected_dir = None
            if arrow_contours:
                largest = max(arrow_contours, key=cv2.contourArea)
                if cv2.contourArea(largest) > ARROW_MIN_PX:
                    x_min = largest[:, :, 0].min()
                    x_max = largest[:, :, 0].max()
                    y_min = largest[:, :, 1].min()
                    y_max = largest[:, :, 1].max()

                    cropped = arrow_mask[y_min:y_max, x_min:x_max]
                    cw = cropped.shape[1]
                    left_px  = cv2.countNonZero(cropped[:, :cw // 2])
                    right_px = cv2.countNonZero(cropped[:, cw // 2:])
                    detected_dir = "LEFT" if left_px > right_px else "RIGHT"

                    cv2.rectangle(frame, (x_min, y_min), (x_max, y_max),
                                  (255, 180, 0), 2)
                    cv2.putText(frame, f"ARROW: {detected_dir}", (10, 30),
                                cv2.FONT_HERSHEY_PLAIN, 2, (255, 180, 0), 3)

                    with auto_lock:
                        last_arrow_dir = detected_dir.lower()
                        if auto_mode and auto_state == "idle":
                            turn_dir   = detected_dir.lower()
                            auto_state = "turning"

            # ── Red ball detection ────────────────────────────────────────────
            ball_mask = cv2.bitwise_or(
                cv2.inRange(hsv, BALL_HSV_LO1, BALL_HSV_HI1),
                cv2.inRange(hsv, BALL_HSV_LO2, BALL_HSV_HI2),
            )
            ball_mask = cv2.erode(ball_mask,  None, iterations=2)
            ball_mask = cv2.dilate(ball_mask, None, iterations=2)

            contours, _ = cv2.findContours(ball_mask, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
            detected_cx = -1
            valid = [c for c in contours if cv2.contourArea(c) >= BALL_MIN_AREA]
            top2  = sorted(valid, key=cv2.contourArea, reverse=True)[:2]

            centroids = []
            for i, c in enumerate(top2):
                M = cv2.moments(c)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    centroids.append((cx, cy))
                    cv2.circle(frame, (cx, cy), 8, (0, 0, 255), -1)
                    cv2.putText(frame, f"BALL{i+1}", (cx + 10, cy),
                                cv2.FONT_HERSHEY_PLAIN, 1.5, (0, 0, 255), 2)

            # Use the largest ball's centroid for auto-drive steering
            if centroids:
                detected_cx = centroids[0][0]

            with auto_lock:
                ball_cx = detected_cx

            # Centre-line guide
            cv2.line(frame, (w//2, 0), (w//2, h), (100, 100, 100), 1)

        _, jpg = cv2.imencode(".jpg", frame)
        with frame_lock:
            latest_jpg = jpg.tobytes()


# ── Motor thread ───────────────────────────────────────────────────────────────
def motor_loop(set_motors):
    global auto_state

    while running:
        with auto_lock:
            am     = auto_mode
            state  = auto_state
            bcx    = ball_cx
            fw     = frame_w
            td     = turn_dir

        if am:
            if state == "turning":
                # Check if ball is centred enough to switch to driving
                if bcx != -1 and abs(bcx - fw / 2) < fw * CENTER_BAND:
                    with auto_lock:
                        auto_state = "driving"
                    set_motors(0.0, 0.0)
                elif td == "right":
                    set_motors(-TURN_POWER, TURN_POWER)
                else:
                    set_motors(TURN_POWER, -TURN_POWER)

            elif state == "driving":
                if bcx == -1:
                    # Lost the ball — stop and go back to idle
                    with auto_lock:
                        auto_state = "idle"
                    set_motors(0.0, 0.0)
                else:
                    set_motors(DRIVE_POWER, DRIVE_POWER)

            else:  # idle
                set_motors(0.0, 0.0)

        else:
            # Manual control
            with key_lock:
                key = current_key

            if key == 'w':
                set_motors(POWER, POWER)
            elif key == 's':
                set_motors( -POWER,  -POWER)
            elif key == 'a':
                set_motors( POWER, -POWER)
            elif key == 'd':
                set_motors(-POWER,  POWER)
            else:
                set_motors(0.0, 0.0)

        time.sleep(TICK)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    global running, current_key, cv_active, auto_mode, auto_state

    print("Connecting to pigpio...")
    pi = pigpio.pi()
    if not pi.connected:
        print("Warning: pigpio not connected. Run: sudo pigpiod")
        pi = None
    else:
        try:
            pw_read = pi.get_servo_pulsewidth(SERVO_PIN)
            if pw_read > 0:
                global servo_pw
                servo_pw = pw_read
        except pigpio.error:
            pass  # pin not yet used for servo, keep default 1500
        threading.Thread(target=servo_loop, args=(pi,), daemon=True).start()
        print("Servo ready.")

    print("Connecting to motors...")
    p = Plink(frequency=200, timeout=1.0)
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

    cap = cv2.VideoCapture("/dev/video0", cv2.CAP_V4L2)
    if not cap.isOpened():
        cap = cv2.VideoCapture("/dev/video1", cv2.CAP_V4L2)
    if not cap.isOpened():
        print("Cannot open camera")
        return

    threading.Thread(target=camera_loop, args=(cap,),       daemon=True).start()
    threading.Thread(target=motor_loop,  args=(set_motors,), daemon=True).start()

    server = ThreadingHTTPServer(("0.0.0.0", STREAM_PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Open in browser → http://172.26.230.193:{STREAM_PORT}")

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    print("WASD to drive | O/P toggle CV | I toggle auto | 1/2 servo | Q quit\n")

    try:
        tty.setraw(fd)
        while True:
            if select.select([sys.stdin], [], [], 0.05)[0]:
                ch = sys.stdin.read(1).lower()
                if ch in ('q', '\x03'):
                    break
                elif ch == 'o':
                    cv_active = True
                    print("\r[CV] Arrow/ball detection ON ")
                elif ch == 'p':
                    cv_active = False
                    print("\r[CV] Arrow/ball detection OFF")
                elif ch == 'i':
                    with auto_lock:
                        auto_mode = not auto_mode
                        if not auto_mode:
                            auto_state = "idle"
                        state = auto_mode
                    print(f"\r[AUTO] {'ON' if state else 'OFF'}           ")
                elif ch == 'c':
                    with auto_lock:
                        if last_arrow_dir:
                            turn_dir   = last_arrow_dir
                            auto_mode  = True
                            auto_state = "turning"
                            print(f"\r[CONFIRM] Turning {last_arrow_dir.upper()}    ")
                        else:
                            print("\r[CONFIRM] No arrow detected yet              ")
                elif ch == '1':
                    with servo_lock:
                        current = servo_pw
                    servo_queue.put(clip(current + MOVE_AMOUNT, MIN_PW, MAX_PW))
                elif ch == '2':
                    with servo_lock:
                        current = servo_pw
                    servo_queue.put(clip(current - MOVE_AMOUNT, MIN_PW, MAX_PW))
                elif ch in ('w', 'a', 's', 'd'):
                    with key_lock:
                        current_key = ch
                else:
                    with key_lock:
                        current_key = ''
    except KeyboardInterrupt:
        pass
    finally:
        running = False
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        set_motors(0.0, 0.0)
        if pi and pi.connected:
            pi.set_servo_pulsewidth(SERVO_PIN, 0)
            pi.stop()
        time.sleep(0.2)
        cap.release()
        print("\nStopped. Exiting cleanly.")


if __name__ == "__main__":
    main()
