"""
combined.py  –  runs ON THE PI
  • Captures camera, runs arrow detection, controls motors
  • Open  http://172.26.230.193:8081  in your laptop browser to:
      – watch the live annotated feed
      – drive with WASD keys in the browser
"""

import cv2
import numpy as np
import time
import sys
import tty
import termios
import select
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from motorgo import Plink, ControlMode

# ── Config ─────────────────────────────────────────────────────────────────────
STREAM_PORT = 8081
LOWER_BGR   = np.array([64,  19,  19])
UPPER_BGR   = np.array([118, 150, 80])

LEFT_CHS    = [1, 2]
RIGHT_CHS   = [3, 4]
LEFT_DIRS   = [-1, 1]
RIGHT_DIRS  = [1, 1]
POWER       = 1
TICK        = 0.05

# ── Shared state ───────────────────────────────────────────────────────────────
latest_jpg = None
frame_lock = threading.Lock()

current_key = ""          # letter held right now  ('' = stop)
key_lock    = threading.Lock()

running   = True          # set False to stop all threads
cv_active = False         # set True by 'o', False by 'p'

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
    #status { margin-top:10px; font-size:0.9rem; color:#aaa; }
    #cv-status { margin-top:8px; font-size:0.9rem; padding:4px 12px;
                 border-radius:6px; background:#333; border:2px solid #555; }
    #cv-status.on { background:#1565c0; border-color:#42a5f5; color:#fff; }
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
  <div id="status">Click the page then hold WASD to drive.</div>
  <div id="cv-status">CV: OFF</div>
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

    document.addEventListener('keydown', e => {
      const k = e.key.toLowerCase();
      if (k === 'o') { e.preventDefault(); setCv(true);  return; }
      if (k === 'p') { e.preventDefault(); setCv(false); return; }
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
            with key_lock:
                global current_key
                current_key = k
            self.send_response(204)
            self.end_headers()

        elif parsed.path == "/cv":
            global cv_active
            cv_active = parse_qs(parsed.query).get("on", ["0"])[0] == "1"
            self.send_response(204)
            self.end_headers()

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_):
        pass


# ── Camera thread ──────────────────────────────────────────────────────────────
def camera_loop(cap):
    global latest_jpg, cv_active
    while running:
        ret, frame = cap.read()
        if not ret:
            continue

        if cv_active:
            w = frame.shape[1]
            arrow_mask = cv2.inRange(frame, LOWER_BGR, UPPER_BGR)
            left_px  = np.sum(np.any(arrow_mask[:, :w//2] > 0, axis=1))
            right_px = np.sum(np.any(arrow_mask[:, w//2:] > 0, axis=1))
            if left_px + right_px > 20:
                direction = "RIGHT" if right_px > left_px else "LEFT"
                cv2.putText(frame, direction, (10, 30),
                            cv2.FONT_HERSHEY_PLAIN, 2, (0, 255, 0), 3)

        _, jpg = cv2.imencode(".jpg", frame)
        with frame_lock:
            latest_jpg = jpg.tobytes()


# ── Motor thread ───────────────────────────────────────────────────────────────
def motor_loop(set_motors):
    while running:
        with key_lock:
            key = current_key

        if key == 'w':
            set_motors(-POWER, -POWER)
        elif key == 's':
            set_motors( POWER,  POWER)
        elif key == 'a':
            set_motors( POWER, -POWER)
        elif key == 'd':
            set_motors(-POWER,  POWER)
        else:
            set_motors(0.0, 0.0)

        time.sleep(TICK)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    global running, current_key, cv_active

    # Motors
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

    # Camera
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Cannot open camera")
        return

    # Start threads
    threading.Thread(target=camera_loop, args=(cap,), daemon=True).start()
    threading.Thread(target=motor_loop,  args=(set_motors,), daemon=True).start()

    server = ThreadingHTTPServer(("0.0.0.0", STREAM_PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Open in browser → http://172.26.230.193:{STREAM_PORT}")

    # Terminal keyboard (optional — Q to quit)
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    print("Hold WASD in the browser to drive. Press Q here to quit.\n")

    try:
        tty.setraw(fd)
        while True:
            if select.select([sys.stdin], [], [], 0.05)[0]:
                ch = sys.stdin.read(1).lower()
                if ch in ('q', '\x03'):
                    break
                if ch == 'o':
                    cv_active = True
                    print("\r[CV] Arrow detection ON ")
                elif ch == 'p':
                    cv_active = False
                    print("\r[CV] Arrow detection OFF")
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
        time.sleep(0.2)
        cap.release()
        print("\nStopped. Exiting cleanly.")


if __name__ == "__main__":
    main()
