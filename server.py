import csv
import os
import shlex
import socket
import subprocess
import threading
import time
import atexit
import signal
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from rcon.source import Client

try:
    from py.modes import MODES
except Exception:
    MODES = ["deathmatch", "armsrace", "casual", "competitive"]


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
MAPS_FILE = BASE_DIR / "maps.csv"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)


load_env(BASE_DIR / ".env")


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_maps() -> list[dict]:
    maps = []
    if not MAPS_FILE.exists():
        return maps
    with MAPS_FILE.open("r", encoding="utf-8") as csvf:
        for row in csv.DictReader(csvf):
            maps.append(
                {
                    "workshop": row["workshop"] == "yes",
                    "id": row["id"],
                    "name": row["name"],
                    "modes": row["modes"].split("|"),
                }
            )
    return maps


MAPS = load_maps()
DEFAULT_CVARS = [
    "mp_maxmoney 99999",
    "mp_afterroundmoney 99999",
    "mp_startmoney 99999",
    "mp_autoteambalance 0",
]
RESTART_COMMAND = "mp_restartgame 1"


def find_map(map_id_or_name: str) -> dict | None:
    for entry in MAPS:
        if entry["id"] == map_id_or_name or entry["name"] == map_id_or_name:
            return entry
    return None


def cs2_executable() -> Path:
    cs2_path = os.environ.get("CS2_PATH", "").strip()
    if not cs2_path:
        raise RuntimeError("CS2_PATH is not set")
    if os.name == "nt":
        cs2_path = os.path.normpath(cs2_path)
    base = Path(cs2_path).expanduser()
    if os.name == "nt":
        exe = base / "game" / "bin" / "win64" / "cs2.exe"
    else:
        exe = base / "game" / "bin" / "linuxsteamrt64" / "cs2"
    return exe


def run_rcon(command: str) -> str:
    host = os.environ.get("RCON_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = env_int("RCON_PORT", 27015)
    password = os.environ.get("RCON_PASSWORD", "")
    if not password:
        raise RuntimeError("RCON_PASSWORD is not set")
    parts = shlex.split(command)
    if not parts:
        return ""
    server_ip = os.environ.get("SERVER_IP", "").strip()
    hosts = [host]
    if server_ip and server_ip not in hosts:
        hosts.append(server_ip)
    last_error = None
    for target in hosts:
        try:
            with Client(target, port, passwd=password) as client:
                return client.run(*parts)
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    return ""


def wait_for_port(host: str, port: int, timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def wait_for_rcon(host: str, port: int, password: str, timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with Client(host, port, passwd=password) as client:
                client.run("status")
            return True
        except Exception:
            time.sleep(1)
    return False


class ServerManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._paused = False
        self._last_map = os.environ.get("DEFAULT_MAP", "de_dust2")
        self._last_mode = os.environ.get("DEFAULT_MODE", "competitive")
        self._log_lock = threading.Lock()
        self._log_lines: list[str] = []

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def status(self) -> dict:
        return {
            "running": self.is_running(),
            "pid": None if not self.is_running() else self._process.pid,
            "paused": self._paused,
            "map": self._last_map,
            "mode": self._last_mode,
        }

    def logs(self, limit: int = 200) -> list[str]:
        with self._log_lock:
            return self._log_lines[-limit:]

    def build_command(self, map_entry: dict, mode: str) -> list[str]:
        exe = cs2_executable()
        if not exe.exists():
            raise RuntimeError(f"CS2 executable not found at {exe}")
        server_ip = os.environ.get("SERVER_IP", "0.0.0.0")
        game_port = env_int("GAME_PORT", 27015)
        max_players = env_int("MAX_PLAYERS", 64)
        threads = os.environ.get("THREADS", "").strip()
        workshop_collection = os.environ.get("WORKSHOP_COLLECTION_ID", "").strip()
        rcon_password = os.environ.get("RCON_PASSWORD", "").strip()
        if not rcon_password:
            raise RuntimeError("RCON_PASSWORD is not set")

        args = [
            str(exe),
            "-dedicated",
            "-usercon",
            "-strictportbind",
            "-nomaster",
            "-ip",
            server_ip,
            "-port",
            str(game_port),
            "-maxplayers",
            str(max_players),
            "+game_alias",
            mode,
            "+rcon_password",
            rcon_password,
        ]

        if env_bool("HIGH_PRIORITY", True):
            args.append("-high")

        if threads:
            args.extend(["-threads", threads])

        if workshop_collection:
            args.extend(["+host_workshop_collection", workshop_collection])

        if map_entry.get("workshop"):
            args.extend(["+host_workshop_map", map_entry["id"]])
        else:
            args.extend(["+map", map_entry["id"]])

        extra_args = os.environ.get("EXTRA_ARGS", "").strip()
        if extra_args:
            args.extend(shlex.split(extra_args))

        return args

    def start(self) -> dict:
        with self._lock:
            if self.is_running():
                return self.status()
            default_map = os.environ.get("DEFAULT_MAP", "de_dust2")
            default_mode = os.environ.get("DEFAULT_MODE", "competitive")
            map_entry = find_map(default_map)
            if map_entry is None:
                raise RuntimeError(f"Unknown map '{default_map}'")
            command = self.build_command(map_entry, default_mode)
            cwd = Path(os.environ.get("CS2_PATH", "")).expanduser()
            self._process = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._start_log_stream()
            server_ip = os.environ.get("SERVER_IP", "127.0.0.1").strip() or "127.0.0.1"
            game_port = env_int("GAME_PORT", 27015)
            timeout = env_int("SERVER_STARTUP_TIMEOUT", 20)
            if not wait_for_port(server_ip, game_port, timeout):
                self.stop()
                raise RuntimeError(f"CS2 server did not open {server_ip}:{game_port} within {timeout}s")
            rcon_host = os.environ.get("RCON_HOST", "127.0.0.1").strip() or "127.0.0.1"
            rcon_port = env_int("RCON_PORT", 27015)
            rcon_password = os.environ.get("RCON_PASSWORD", "").strip()
            rcon_timeout = env_int("RCON_STARTUP_TIMEOUT", 10)
            if not wait_for_rcon(rcon_host, rcon_port, rcon_password, rcon_timeout):
                self.stop()
                raise RuntimeError(f"RCON did not respond on {rcon_host}:{rcon_port} within {rcon_timeout}s")
            self._last_map = map_entry["id"]
            self._last_mode = default_mode
            self._paused = False
            self._apply_default_cvars_async()
            return self.status()

    def stop(self) -> dict:
        with self._lock:
            if not self.is_running():
                return self.status()
            try:
                run_rcon("quit")
                self._wait_for_exit(timeout=8)
            except Exception:
                pass
            if self.is_running():
                self._kill_process()
            return self.status()

    def change_map(self, map_entry: dict, mode: str) -> str:
        self._last_map = map_entry["id"]
        self._last_mode = mode
        if map_entry.get("workshop"):
            response = run_rcon(f"game_alias {mode} ; host_workshop_map {map_entry['id']}")
        else:
            response = run_rcon(f"game_alias {mode} ; map {map_entry['id']}")
        self._apply_default_cvars_async()
        return response

    def pause(self, action: str) -> str:
        if action == "pause":
            self._paused = True
            return run_rcon("mp_pause_match")
        if action == "resume":
            self._paused = False
            return run_rcon("mp_unpause_match")
        if self._paused:
            self._paused = False
            return run_rcon("mp_unpause_match")
        self._paused = True
        return run_rcon("mp_pause_match")

    def _apply_default_cvars_async(self) -> None:
        delay = env_int("DEFAULT_CVAR_DELAY", 4)
        post_delay = env_int("POST_RESTART_CVAR_DELAY", 2)

        def worker():
            time.sleep(delay)
            for command in DEFAULT_CVARS:
                try:
                    run_rcon(command)
                except Exception:
                    continue
            try:
                run_rcon(RESTART_COMMAND)
            except Exception:
                return
            time.sleep(post_delay)
            for command in DEFAULT_CVARS:
                try:
                    run_rcon(command)
                except Exception:
                    continue

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

        threading.Thread(target=reader, daemon=True).start()

    def _kill_process(self) -> None:
        proc = self._process
        if proc is None:
            return
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                proc.wait(timeout=5)
                return
            except Exception:
                pass
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass

    def _wait_for_exit(self, timeout: int) -> None:
        proc = self._process
        if proc is None:
            return
        try:
            proc.wait(timeout=timeout)
        except Exception:
            pass


app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")
manager = ServerManager()


def shutdown_server():
    try:
        manager.stop()
    except Exception:
        pass


atexit.register(shutdown_server)


def _force_exit_after(timeout: int) -> None:
    def worker():
        time.sleep(timeout)
        os._exit(1)

    threading.Thread(target=worker, daemon=True).start()


def handle_shutdown(signum, _frame):
    print(f"Shutdown signal received ({signum}). Stopping server...")
    _force_exit_after(env_int("SHUTDOWN_TIMEOUT", 8))
    try:
        manager.stop()
    finally:
        sys.exit(0)


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


def json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


@app.get("/api/status")
def api_status():
    return jsonify({"ok": True, **manager.status()})


@app.get("/api/config")
def api_config():
    return jsonify(
        {
            "ok": True,
            "default_mode": os.environ.get("DEFAULT_MODE", "competitive"),
            "default_map": os.environ.get("DEFAULT_MAP", "de_dust2"),
        }
    )


@app.get("/api/maps")
def api_maps():
    return jsonify({"ok": True, "maps": MAPS})


@app.get("/api/modes")
def api_modes():
    return jsonify({"ok": True, "modes": MODES})


@app.get("/api/logs")
def api_logs():
    limit = env_int("LOG_LIMIT", 200)
    try:
        limit = int(request.args.get("limit", limit))
    except ValueError:
        pass
    return jsonify({"ok": True, "lines": manager.logs(limit)})


@app.post("/api/start")
def api_start():
    try:
        return jsonify({"ok": True, **manager.start()})
    except Exception as exc:
        return json_error(str(exc), 500)


@app.post("/api/stop")
def api_stop():
    try:
        return jsonify({"ok": True, **manager.stop()})
    except Exception as exc:
        return json_error(str(exc), 500)


@app.post("/api/change")
def api_change():
    payload = request.get_json(silent=True) or {}
    map_id = str(payload.get("map_id", "")).strip()
    mode = str(payload.get("mode", "")).strip()
    if not map_id or not mode:
        return json_error("map_id and mode are required")
    if mode not in MODES:
        return json_error("Invalid mode")
    map_entry = find_map(map_id)
    if map_entry is None:
        return json_error("Unknown map")
    try:
        response = manager.change_map(map_entry, mode)
        return jsonify({"ok": True, "response": response})
    except Exception as exc:
        return json_error(str(exc), 500)


@app.post("/api/rcon")
def api_rcon():
    payload = request.get_json(silent=True) or {}
    command = str(payload.get("command", "")).strip()
    if not command:
        return json_error("command is required")
    try:
        response = run_rcon(command)
        return jsonify({"ok": True, "response": response})
    except Exception as exc:
        return json_error(str(exc), 500)


@app.post("/api/pause")
def api_pause():
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action", "toggle")).strip()
    try:
        response = manager.pause(action)
        return jsonify({"ok": True, "response": response, "paused": manager.status()["paused"]})
    except Exception as exc:
        return json_error(str(exc), 500)


@app.route("/", methods=["GET", "POST"])
def index():
    return send_from_directory(str(WEB_DIR), "index.html")


@app.get("/<path:filename>")
def static_files(filename: str):
    return send_from_directory(str(WEB_DIR), filename)


if __name__ == "__main__":
    port = env_int("WEB_PORT", 5000)
    app.run(host="0.0.0.0", port=port, debug=False)
