import json
import os
import socket
from urllib.error import URLError
from urllib.request import Request, urlopen
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


def read_config_data(path: Path) -> dict:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    try:
        import yaml
    except Exception:
        return {}
    try:
        data = yaml.safe_load(raw) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def coerce_port(value) -> int | None:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None
    return port if port > 0 else None


def normalize_variants(raw_variants: list, env: dict) -> list[dict]:
    normalized = []
    for item in raw_variants:
        if not isinstance(item, dict):
            continue
        variant_id = str(item.get("id") or item.get("name") or "").strip()
        if not variant_id:
            continue
        display_name = item.get("display_name") or item.get("displayName") or item.get("name") or variant_id
        description = item.get("description") or ""
        ui_path = item.get("ui_path") or item.get("uiPath") or "/"
        status_path = item.get("status_path") or item.get("statusPath") or "/api/status"
        if not str(ui_path).startswith("/"):
            ui_path = f"/{ui_path}"
        if not str(status_path).startswith("/"):
            status_path = f"/{status_path}"
        port = None
        port_env = item.get("port_env") or item.get("portEnv")
        if port_env:
            port = coerce_port(env.get(str(port_env)) or env.get(str(port_env).upper()))
        if port is None:
            port = coerce_port(item.get("port"))
        if port is None:
            continue
        normalized.append(
            {
                "id": variant_id,
                "display_name": display_name,
                "description": description,
                "port": port,
                "ui_path": ui_path,
                "status_path": status_path,
            }
        )
    return normalized


def load_variant_registry(config_path: Path, env: dict) -> list[dict]:
    data = read_config_data(config_path)
    raw_variants = data.get("variants")
    if isinstance(raw_variants, list):
        variants = normalize_variants(raw_variants, env)
        if variants:
            return variants
    defaults = [
        {
            "id": "cs2",
            "display_name": "Counter-Strike 2",
            "description": "Primary control UI",
            "port_env": "WEB_PORT",
            "port": 5000,
            "status_path": "/api/status",
            "ui_path": "/",
        },
        {
            "id": "dummy",
            "display_name": "Dummy Server",
            "description": "Example secondary server",
            "port_env": "DUMMY_PORT",
            "port": 5001,
            "status_path": "/api/status",
            "ui_path": "/",
        },
    ]
    return normalize_variants(defaults, env)


def probe_variant_status(port: int, status_path: str, timeout: float = 1.5) -> dict:
    url = f"http://127.0.0.1:{port}{status_path}"
    request = Request(url, headers={"User-Agent": "homelab-arcade-portal"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return {"running": True, "ready": True}
        if isinstance(payload, dict):
            running = bool(payload.get("running", True))
            ready = bool(payload.get("ready", running))
            return {"running": running, "ready": ready}
    except (URLError, OSError, TimeoutError):
        return {"running": False, "ready": False}
    return {"running": True, "ready": True}


class RootRewriteHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, default_file="portal.html", **kwargs):
        self._default_file = default_file
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/host":
            payload = {"host": detect_primary_ip()}
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/variants":
            variants = load_variant_registry(DEFAULT_CONFIG_PATH, os.environ)
            payload = []
            for variant in variants:
                status = probe_variant_status(variant["port"], variant["status_path"])
                if not status["running"]:
                    state = "offline"
                elif status["ready"]:
                    state = "live"
                else:
                    state = "starting"
                payload.append(
                    {
                        "id": variant["id"],
                        "display_name": variant["display_name"],
                        "description": variant["description"],
                        "port": variant["port"],
                        "ui_path": variant["ui_path"],
                        "status": {"state": state, **status},
                    }
                )
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
    load_config(DEFAULT_CONFIG_PATH, game="cs2")
    web_dir = Path(__file__).resolve().parent / "web"
    port = int(os.environ.get("PORTAL_PORT", "80"))
    handler = partial(RootRewriteHandler, directory=str(web_dir), default_file="portal.html")
    server = ThreadingHTTPServer(("", port), handler)
    print(f"Portal server listening on http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
