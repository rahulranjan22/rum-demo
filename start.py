#!/usr/bin/env python3
"""
start.py — single launcher for the Elastic APM RUM Demo tool

Starts two local servers:
  :9210  HTTP server   — serves rum-demo.html in the browser
  :9211  CORS proxy    — forwards browser APM calls server-side (no CORS block)

Usage:
  python3 start.py

Then open: http://localhost:9210/rum-demo.html
Press Ctrl+C to stop both servers.
"""

import http.server
import urllib.request
import urllib.error
import json
import sys
import threading
import webbrowser
import time
import os

HTTP_PORT  = 9210
PROXY_PORT = 9211
SERVE_DIR  = os.path.dirname(os.path.abspath(__file__))

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS, GET",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Target-Url, X-Target-Auth, X-Sim-Ip",
    "Access-Control-Max-Age": "86400",
}


# ── CORS proxy ────────────────────────────────────────────────────────────────

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  [proxy] {fmt % args}")

    def _send_cors(self):
        for k, v in CORS.items():
            self.send_header(k, v)

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self._send_cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"proxy": "rum-cors-proxy", "port": PROXY_PORT}).encode())

    def do_POST(self):
        target_url  = self.headers.get("X-Target-Url", "").strip()
        target_auth = self.headers.get("X-Target-Auth", "").strip()
        sim_ip      = self.headers.get("X-Sim-Ip", "").strip()

        if not target_url:
            self.send_response(400)
            self._send_cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"Missing X-Target-Url header"}')
            return

        path   = self.path
        url    = target_url.rstrip("/") + path
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length) if length else b""
        ct     = self.headers.get("Content-Type", "application/x-ndjson")

        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", ct)
        if target_auth:
            req.add_header("Authorization", target_auth)
        if sim_ip:
            req.add_header("X-Forwarded-For", sim_ip)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                code = resp.status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception as ex:
            code = 0
            print(f"  [proxy] error forwarding to {url}: {ex}")

        print(f"  [proxy] {url} → {code}")
        self.send_response(code if code else 502)
        self._send_cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": code, "target": url}).encode())


# ── Static file server ────────────────────────────────────────────────────────

class QuietFileHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SERVE_DIR, **kwargs)

    def log_message(self, fmt, *args):
        pass  # suppress per-request noise; errors still print


# ── Main ──────────────────────────────────────────────────────────────────────

def serve(server):
    try:
        server.serve_forever()
    except Exception:
        pass


if __name__ == "__main__":
    proxy_server = http.server.HTTPServer(("0.0.0.0", PROXY_PORT), ProxyHandler)
    file_server  = http.server.HTTPServer(("0.0.0.0", HTTP_PORT),  QuietFileHandler)

    threading.Thread(target=serve, args=(proxy_server,), daemon=True).start()
    threading.Thread(target=serve, args=(file_server,),  daemon=True).start()

    url = f"http://localhost:{HTTP_PORT}/rum-demo.html"
    print(f"\n  Elastic APM RUM Demo")
    print(f"  ─────────────────────────────────────")
    print(f"  UI    →  {url}")
    print(f"  Proxy →  http://localhost:{PROXY_PORT}")
    print(f"\n  Opening browser...")
    print(f"  Press Ctrl+C to stop.\n")

    time.sleep(0.4)
    webbrowser.open(url)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Stopped.")
        proxy_server.shutdown()
        file_server.shutdown()
