import atexit
import logging
import os
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
WEB_DIR = BASE_DIR / "web"
SHARED_DIR = ROOT_DIR / "web"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app_config import DEFAULT_CONFIG_PATH, load_config


load_config(DEFAULT_CONFIG_PATH, game="sandstorm")


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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


def resolve_executable() -> Path:
    raw = os.environ.get("SANDSTORM_PATH", "").strip()
    if not raw:
        raise RuntimeError("SANDSTORM_PATH is not set")
    base = Path(os.path.normpath(raw)).expanduser()
    if base.is_file():
        return base
    return base / "InsurgencyServer.exe"


class ServerManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._log_lines: list[str] = []
        self._ready = False
        self._last_map = os.environ.get("SANDSTORM_DEFAULT_MAP", "Farmhouse")
        self._last_scenario = os.environ.get(
            "SANDSTORM_DEFAULT_SCENARIO",
            "Scenario_Farmhouse_Checkpoint_Security",
        )

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def status(self) -> dict:
        return {
            "running": self.is_running(),
            "ready": self._ready and self.is_running(),
            "pid": None if not self.is_running() else self._process.pid,
            "map": self._last_map,
            "scenario": self._last_scenario,
        }

    def logs(self, limit: int = 200) -> list[str]:
        with self._log_lock:
            return self._log_lines[-limit:]

    def clear_logs(self) -> None:
        with self._log_lock:
            self._log_lines = []

    def build_command(self) -> list[str]:
        exe = resolve_executable()
        if not exe.exists():
            raise RuntimeError(f"InsurgencyServer.exe not found at {exe}")

        host_ip = detect_primary_ip()
        game_port = env_int("SANDSTORM_GAME_PORT", 27102)
        query_port = env_int("SANDSTORM_QUERY_PORT", 27131)
        max_players = env_int("SANDSTORM_MAX_PLAYERS", 28)
        hostname = os.environ.get("SANDSTORM_HOSTNAME", "Homelab Sandstorm").strip() or "Homelab Sandstorm"

        travel = f"{self._last_map}?Scenario={self._last_scenario}?MaxPlayers={max_players}"
        args = [
            str(exe),
            travel,
            "-log",
            f"-Port={game_port}",
            f"-QueryPort={query_port}",
            f"-multihome={host_ip}",
            f"-hostname={hostname}",
        ]

        if env_bool("SANDSTORM_NO_EAC", True):
            args.append("-NoEAC")

        extra_args = os.environ.get("SANDSTORM_EXTRA_ARGS", "").strip()
        if extra_args:
            args.extend(shlex.split(extra_args))

        return args

    def start(self) -> dict:
        with self._lock:
            if self.is_running():
                app.logger.info("Start requested but Sandstorm is already running.")
                return self.status()

            command = self.build_command()
            cwd = resolve_executable().parent
            app.logger.info("Starting Insurgency: Sandstorm server.")
            app.logger.info("Command: %s", " ".join(command))
            self._ready = False
            self._process = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._start_log_stream()
            self._mark_ready_async()
            return self.status()

    def stop(self) -> dict:
        with self._lock:
            self._ready = False
            proc = self._process
            if proc is None or proc.poll() is not None:
                self._process = None
                return self.status()

            app.logger.info("Stopping Insurgency: Sandstorm server.")
            proc.terminate()
            timeout = env_int("SANDSTORM_SHUTDOWN_TIMEOUT", 8)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                app.logger.warning("Sandstorm did not stop within %ss; killing process.", timeout)
                proc.kill()
                proc.wait(timeout=5)
            finally:
                self._process = None
            return self.status()

    def _mark_ready_async(self) -> None:
        grace = env_int("SANDSTORM_STARTUP_GRACE_SECONDS", 8)

        def worker():
            time.sleep(max(grace, 1))
            with self._lock:
                self._ready = self.is_running()

        threading.Thread(target=worker, daemon=True).start()

    def _start_log_stream(self) -> None:
        proc = self._process
        if proc is None or proc.stdout is None:
            return

        with self._log_lock:
            self._log_lines = []

        def reader():
            for line in proc.stdout:
                with self._log_lock:
                    self._log_lines.append(line.rstrip())
                    if len(self._log_lines) > 1000:
                        self._log_lines = self._log_lines[-800:]
            with self._lock:
                if self._process is proc:
                    self._ready = False
                    self._process = None

        threading.Thread(target=reader, daemon=True).start()


OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Homelab Arcade Sandstorm API",
        "version": "0.1.0",
        "description": "Minimal Insurgency: Sandstorm control API for start, stop, and status.",
    },
    "paths": {
        "/health": {"get": {"summary": "Health check", "responses": {"200": {"description": "Healthy"}}}},
        "/openapi.json": {"get": {"summary": "OpenAPI document", "responses": {"200": {"description": "Spec"}}}},
        "/api/status": {"get": {"summary": "Current status", "responses": {"200": {"description": "Status"}}}},
        "/api/config": {"get": {"summary": "Effective config", "responses": {"200": {"description": "Config"}}}},
        "/api/logs": {"get": {"summary": "Buffered logs", "responses": {"200": {"description": "Logs"}}}},
        "/api/logs/clear": {"post": {"summary": "Clear logs", "responses": {"200": {"description": "Cleared"}}}},
        "/api/start": {"post": {"summary": "Start server", "responses": {"200": {"description": "Started"}}}},
        "/api/stop": {"post": {"summary": "Stop server", "responses": {"200": {"description": "Stopped"}}}},
    },
}


app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")
manager = ServerManager()
api_logger = logging.getLogger("sandstorm")


@app.before_request
def before_request() -> None:
    g.request_started = time.time()
    g.request_id = request.headers.get("X-Request-Id", "").strip() or str(uuid.uuid4())


@app.after_request
def after_request(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["X-Request-Id"] = g.get("request_id", "")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        latency_ms = int((time.time() - g.get("request_started", time.time())) * 1000)
        api_logger.info(
            "method=%s path=%s status=%s latency_ms=%s request_id=%s",
            request.method,
            request.path,
            response.status_code,
            latency_ms,
            g.get("request_id", ""),
        )
    return response


def json_ok(payload: dict | None = None, status: int = 200):
    body = {"ok": True, "request_id": g.get("request_id", "")}
    if payload:
        body.update(payload)
    return jsonify(body), status


def json_error(code: str, message: str, status: int = 400, details=None):
    return (
        jsonify(
            {
                "error": code,
                "message": message,
                "details": details,
                "request_id": g.get("request_id", ""),
            }
        ),
        status,
    )


def shutdown_server() -> None:
    try:
        manager.stop()
    except Exception:
        pass


atexit.register(shutdown_server)


def handle_shutdown(signum, _frame):
    print(f"Shutdown signal received ({signum}). Stopping Sandstorm server...")
    try:
        manager.stop()
    finally:
        sys.exit(0)


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


@app.get("/health")
def health():
    return json_ok()


@app.get("/openapi.json")
def openapi():
    return jsonify(OPENAPI_SPEC)


@app.get("/api/status")
def api_status():
    return json_ok(manager.status())


@app.get("/api/config")
def api_config():
    return json_ok(
        {
            "sandstorm_path": os.environ.get("SANDSTORM_PATH", ""),
            "default_map": os.environ.get("SANDSTORM_DEFAULT_MAP", "Farmhouse"),
            "default_scenario": os.environ.get(
                "SANDSTORM_DEFAULT_SCENARIO",
                "Scenario_Farmhouse_Checkpoint_Security",
            ),
            "game_port": env_int("SANDSTORM_GAME_PORT", 27102),
            "query_port": env_int("SANDSTORM_QUERY_PORT", 27131),
            "max_players": env_int("SANDSTORM_MAX_PLAYERS", 28),
            "web_port": env_int("SANDSTORM_WEB_PORT", 5002),
        }
    )


@app.get("/api/logs")
def api_logs():
    limit = env_int("SANDSTORM_LOG_LIMIT", 200)
    try:
        limit = int(request.args.get("limit", limit))
    except (TypeError, ValueError):
        pass
    return json_ok({"lines": manager.logs(limit)})


@app.post("/api/logs/clear")
def api_logs_clear():
    manager.clear_logs()
    return json_ok()


@app.post("/api/start")
def api_start():
    try:
        app.logger.info("Sandstorm start requested via API.")
        return json_ok(manager.start())
    except Exception as exc:
        app.logger.exception("Sandstorm start failed: %s", exc)
        return json_error("start_failed", str(exc), 500)


@app.post("/api/stop")
def api_stop():
    try:
        app.logger.info("Sandstorm stop requested via API.")
        return json_ok(manager.stop())
    except Exception as exc:
        app.logger.exception("Sandstorm stop failed: %s", exc)
        return json_error("stop_failed", str(exc), 500)


@app.get("/shared.css")
def shared_css():
    return send_from_directory(str(SHARED_DIR), "shared.css")


@app.route("/", methods=["GET"])
def index():
    return send_from_directory(str(WEB_DIR), "index.html")


@app.get("/<path:filename>")
def static_files(filename: str):
    return send_from_directory(str(WEB_DIR), filename)


if __name__ == "__main__":
    app.logger.setLevel(logging.INFO)
    api_logger.setLevel(logging.INFO)
    port = env_int("SANDSTORM_WEB_PORT", 5002)
    app.run(host="0.0.0.0", port=port, debug=False)
