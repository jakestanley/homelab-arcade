import json
import os
import socket
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cs2.config import DEFAULT_CONFIG_PATH, load_config


def detect_primary_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


class RootRewriteHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, default_file="portal.html", **kwargs):
        self._default_file = default_file
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        if self.path == "/api/host":
            payload = {"host": detect_primary_ip()}
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path in {"", "/"}:
            self.path = f"/{self._default_file}"
        return super().do_GET()


def main() -> None:
    load_config(DEFAULT_CONFIG_PATH)
    web_dir = Path(__file__).resolve().parent / "web"
    port = int(os.environ.get("PORTAL_PORT", "80"))
    handler = partial(RootRewriteHandler, directory=str(web_dir), default_file="portal.html")
    server = ThreadingHTTPServer(("", port), handler)
    print(f"Portal server listening on http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
