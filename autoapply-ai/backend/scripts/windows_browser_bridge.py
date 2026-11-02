"""
AutoApply AI - Windows Browser Bridge Service.

When the AutoApply AI backend runs inside a Docker Linux container, it has no direct
access to the host Windows desktop display. This lightweight service runs on the host
Windows machine and launches a real, visible Google Chrome window on the user's desktop,
allowing Docker Playwright to connect to it over CDP (Chrome DevTools Protocol).
"""

import os
import sys
import json
import time
import socket
import shutil
import logging
import subprocess
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BrowserBridge")

BRIDGE_PORT = int(os.getenv("BROWSER_BRIDGE_PORT", 9225))
CDP_PORT = int(os.getenv("CDP_PORT", 9222))
_active_proc = None


def find_chrome_executable():
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        shutil.which("chrome"),
        shutil.which("google-chrome"),
    ]
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


class BridgeHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/status" or self.path == "/":
            self._send_json(200, {
                "status": "running",
                "platform": sys.platform,
                "chrome_available": bool(find_chrome_executable()),
                "cdp_port": CDP_PORT,
                "browser_open": _active_proc is not None and _active_proc.poll() is None
            })
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        global _active_proc

        if self.path == "/launch":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                params = json.loads(body.decode("utf-8"))
            except Exception:
                params = {}

            profile_dir = params.get("profile_dir")
            url = params.get("url", "https://www.linkedin.com/login")

            chrome_exe = find_chrome_executable()
            if not chrome_exe:
                self._send_json(500, {
                    "error": "Google Chrome executable not found on Windows host."
                })
                return

            if not profile_dir:
                profile_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "browser_profiles", "default"))
            os.makedirs(profile_dir, exist_ok=True)

            # Terminate previous if any
            if _active_proc and _active_proc.poll() is None:
                try:
                    _active_proc.terminate()
                except Exception:
                    pass

            cmd = [
                chrome_exe,
                f"--user-data-dir={profile_dir}",
                f"--remote-debugging-port={CDP_PORT}",
                "--remote-debugging-address=0.0.0.0",
                "--new-window",
                "--start-maximized",
                "--no-first-run",
                "--no-default-browser-check",
                url
            ]

            logger.info("Launching Chrome: %s", " ".join(cmd))
            try:
                _active_proc = subprocess.Popen(cmd)
            except Exception as e:
                self._send_json(500, {"error": f"Failed to launch Chrome on Windows: {e}"})
                return

            # Verify CDP responds
            verified = False
            for _ in range(16):
                time.sleep(0.5)
                if _active_proc.poll() is not None:
                    break
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=1) as resp:
                        if resp.status == 200:
                            verified = True
                            break
                except Exception:
                    pass

            if verified:
                self._send_json(200, {
                    "status": "launched",
                    "pid": _active_proc.pid,
                    "cdp_port": CDP_PORT,
                    "message": f"Chrome window opened on Windows desktop (PID {_active_proc.pid})."
                })
            else:
                self._send_json(500, {
                    "error": "Chrome started but remote debugging port did not respond in time.",
                    "pid": _active_proc.pid if _active_proc else None
                })

        elif self.path == "/close":
            if _active_proc and _active_proc.poll() is None:
                try:
                    _active_proc.terminate()
                except Exception:
                    pass
            _active_proc = None
            self._send_json(200, {"status": "closed"})
        else:
            self._send_json(404, {"error": "Not Found"})


def run():
    server = HTTPServer(("0.0.0.0", BRIDGE_PORT), BridgeHandler)
    logger.info("AutoApply AI Windows Browser Bridge listening on port %d...", BRIDGE_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Browser Bridge stopped.")


if __name__ == "__main__":
    run()
