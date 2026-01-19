import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class RootRewriteHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, default_file="dummy.html", **kwargs):
        self._default_file = default_file
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        if self.path in {"", "/"}:
            self.path = f"/{self._default_file}"
        return super().do_GET()


def main() -> None:
    web_dir = Path(__file__).resolve().parent / "web"
    port = int(os.environ.get("DUMMY_PORT", "5001"))
    handler = partial(RootRewriteHandler, directory=str(web_dir), default_file="dummy.html")
    server = ThreadingHTTPServer(("", port), handler)
    print(f"Dummy server listening on http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
