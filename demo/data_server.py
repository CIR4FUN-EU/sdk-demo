"""Mock data source for the connector demo. Serves static JSON on localhost:4000
so the provider asset (demo/connector.py) has something real to point at.

Run: python -m demo.data_server
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

DEFAULT_DATA = {
    "id": 1,
    "name": "Cir4Fun Oak Dining Chair — Care & Sustainability",
    "certification": "FSC-certified oak, EU Ecolabel",
    "recycled_content_percent": 12,
    "care_instructions": "Wipe with a dry cloth; avoid direct sunlight and moisture.",
    "recyclability": "Disassemble via exposed fixings for material-separated recycling.",
}
DATA = dict(DEFAULT_DATA)

_server = None


def reset() -> None:
    """Restore DATA to DEFAULT_DATA (used by /api/reset)."""
    global DATA
    DATA = dict(DEFAULT_DATA)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(DATA).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # ponytail: quiet by default, drop this override if you need request logs


def start() -> None:
    """Start the server in a background thread, once per process."""
    global _server
    if _server is not None:
        return
    # 0.0.0.0 so the provider container can reach it over the compose network.
    _server = HTTPServer(("0.0.0.0", 4000), Handler)
    threading.Thread(target=_server.serve_forever, daemon=True).start()


if __name__ == "__main__":
    start()
    threading.Event().wait()
