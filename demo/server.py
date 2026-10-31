"""Máy chủ HTTP cục bộ phục vụ file mẫu cho demo/test (hỗ trợ Range, có thể làm chậm).

python demo/server.py --port 8765 --delay 0.02
Đường dẫn đặc biệt: /norange/<file> (bỏ qua Range), /forbidden (403).
"""
import argparse
import http.server
import os
import re
import threading
import time

SAMPLES = {
    "phim-mau.mp4": 3 * 1024 * 1024,
    "bai-hat.mp3": 2 * 1024 * 1024,
    "anh-chup.png": 512 * 1024,
    "tai-lieu.pdf": 1024 * 1024,
    "ma-nguon.zip": 1536 * 1024,
    "ghi-chu.xyz": 64 * 1024,
}


def sample_bytes(name):
    size = SAMPLES[name]
    seed = (name.encode() * 64)[:251]
    return (seed * (size // len(seed) + 1))[:size]


def make_handler(delay=0.0):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/forbidden":
                self.send_error(403, "Forbidden")
                return
            norange = path.startswith("/norange/")
            name = os.path.basename(path)
            if name not in SAMPLES:
                self.send_error(404)
                return
            data = sample_bytes(name)
            start = 0
            m = re.match(r"bytes=(\d+)-$", self.headers.get("Range", ""))
            if m and not norange:
                start = int(m.group(1))
                if start >= len(data):
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{len(data)}")
                    self.end_headers()
                    return
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{len(data)-1}/{len(data)}")
            else:
                self.send_response(200)
            if not norange:
                self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(len(data) - start))
            self.end_headers()
            try:
                for i in range(start, len(data), 32 * 1024):
                    self.wfile.write(data[i:i + 32 * 1024])
                    if delay:
                        time.sleep(delay)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return H


def serve(port=0, delay=0.0):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(delay))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--delay", type=float, default=0.02)
    a = ap.parse_args()
    srv = serve(a.port, a.delay)
    print(f"Máy chủ mẫu: http://127.0.0.1:{a.port}/  (Ctrl+C để dừng)")
    for n in SAMPLES:
        print(f"  http://127.0.0.1:{a.port}/{n}")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()
