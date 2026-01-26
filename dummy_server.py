import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cs2.config import DEFAULT_CONFIG_PATH, load_config


class RootRewriteHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, default_file="dummy.html", **kwargs):
        self._default_file = default_file
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/status":
            payload = {"running": True, "ready": True}
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/portal":
            port = int(os.environ.get("PORTAL_PORT", "80"))
            payload = {"port": port}
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in {"", "/"}:
            self.path = f"/{self._default_file}"
        return super().do_GET()


def main() -> None:
    load_config(DEFAULT_CONFIG_PATH)
    web_dir = Path(__file__).resolve().parent / "web"
    port = int(os.environ.get("DUMMY_PORT", "5001"))
    handler = partial(RootRewriteHandler, directory=str(web_dir), default_file="dummy.html")
    server = ThreadingHTTPServer(("", port), handler)
    print(f"Dummy server listening on http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
