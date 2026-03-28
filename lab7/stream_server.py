import cv2
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("Camera not found")
            return

        self.send_response(200)
        self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
        self.end_headers()

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                _, jpg = cv2.imencode('.jpg', frame)
                self.wfile.write(b'--frame\r\n')
                self.wfile.write(b'Content-Type: image/jpeg\r\n\r\n')
                self.wfile.write(jpg.tobytes())
                self.wfile.write(b'\r\n')
        except BrokenPipeError:
            pass
        finally:
            cap.release()

    def log_message(self, format, *args):
        pass

print("Streaming on port 8080...")
HTTPServer(('0.0.0.0', 8080), Handler).serve_forever()