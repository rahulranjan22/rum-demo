#!/usr/bin/env python3
"""
Generic RUM CORS proxy — rum-demo.html sends each request here with the real
APM target URL in the X-Target-Url header (and optional X-Target-Auth).
The proxy adds CORS headers and forwards server-side, bypassing browser CORS.

Usage: python3 rum-proxy.py [port]   (default 9211)
"""

import http.server
import urllib.request
import urllib.error
import json, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9211

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS, GET",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Target-Url, X-Target-Auth, X-Sim-Ip",
    "Access-Control-Max-Age": "86400",
}


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[proxy] {fmt % args}")

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
        self.wfile.write(json.dumps({"proxy": "rum-cors-proxy", "port": PORT}).encode())

    def do_POST(self):
        target_url = self.headers.get("X-Target-Url", "").strip()
        target_auth = self.headers.get("X-Target-Auth", "").strip()
        sim_ip = self.headers.get("X-Sim-Ip", "").strip()

        if not target_url:
            self.send_response(400)
            self._send_cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"Missing X-Target-Url header"}')
            return

        path = self.path  # e.g. /intake/v2/events
        url = target_url.rstrip("/") + path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        ct = self.headers.get("Content-Type", "application/x-ndjson")

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
            print(f"  error forwarding to {url}: {ex}")

        print(f"  {url} → {code}")
        self.send_response(code if code else 502)
        self._send_cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": code, "target": url}).encode())


if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", PORT), ProxyHandler)
    print(f"RUM CORS proxy on http://localhost:{PORT}")
    print("Each request must include X-Target-Url header pointing to the real APM server.")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
