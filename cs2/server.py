import csv
import errno
import os
import re
import shlex
import socket
import subprocess
import threading
import time
import atexit
import signal
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from rcon.source import Client

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
WEB_DIR = BASE_DIR / "web"
SHARED_DIR = ROOT_DIR / "web"
MAPS_FILE = BASE_DIR / "maps.csv"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from cs2.py.modes import MODES
except Exception:
    MODES = ["deathmatch", "armsrace", "casual", "competitive"]

from cs2.config import DEFAULT_CONFIG_PATH, load_config


load_config(DEFAULT_CONFIG_PATH, game="cs2")


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
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
    "mp_autoteambalance 0",
    "mp_autokick 0",
    "mp_tkpunish 0"
]
EXTRA_CVARS = [
    "mp_maxmoney 99999",
    "mp_afterroundmoney 99999",
    "mp_startmoney 99999",
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


def resolve_cs2_exec_wrapper_args(raw: str | None) -> list[str]:
    if raw is None:
        return []
    value = raw.strip()
    if not value:
        return []
    try:
        return shlex.split(value)
    except ValueError as exc:
        raise RuntimeError(f"Invalid CS2_EXEC_WRAPPER value: {value!r}") from exc


def build_cs2_child_env(
    cs2_path: Path,
    base_env: dict[str, str] | None = None,
    *,
    is_windows: bool | None = None,
) -> dict[str, str]:
    env = dict(base_env or os.environ)
    if is_windows is None:
        is_windows = os.name == "nt"
    if is_windows:
        return env

    required_paths = [
        str(cs2_path / "game" / "bin" / "linuxsteamrt64"),
        str(cs2_path / "game" / "csgo" / "bin" / "linuxsteamrt64"),
    ]
    existing = env.get("LD_LIBRARY_PATH", "")
    merged: list[str] = []
    for entry in required_paths + [part for part in existing.split(":") if part]:
        if entry and entry not in merged:
            merged.append(entry)
    env["LD_LIBRARY_PATH"] = ":".join(merged)
    return env


def is_transient_rcon_error(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionRefusedError, ConnectionResetError, TimeoutError, BrokenPipeError)):
        return True
    if isinstance(exc, OSError):
        if exc.errno in {
            errno.ECONNREFUSED,
            errno.ECONNRESET,
            errno.ECONNABORTED,
            errno.ETIMEDOUT,
            errno.EHOSTUNREACH,
            errno.ENETUNREACH,
        }:
            return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "connection refused",
            "connection reset",
            "connection aborted",
            "timed out",
            "timeout",
            "temporarily unavailable",
            "network is unreachable",
            "host is unreachable",
        )
    )


def run_rcon(command: str) -> str:
    host = os.environ.get("RCON_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = env_int("RCON_PORT", 27015)
    password = os.environ.get("RCON_PASSWORD", "")
    if not password:
        raise RuntimeError("RCON_PASSWORD is not set")
    parts = shlex.split(command)
    if not parts:
        return ""
    server_ip = detect_primary_ip()
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
    server_ip = detect_primary_ip()
    hosts = [host]
    if server_ip and server_ip not in hosts:
        hosts.append(server_ip)
    deadline = time.time() + timeout
    while time.time() < deadline:
        for target in hosts:
            try:
                with Client(target, port, passwd=password) as client:
                    client.run("status")
                return True
            except Exception:
                continue
        time.sleep(1)
    return False


class ServerManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._paused = False
        self._ready = False
        self._extra_cvars_enabled = False
        self._last_map = os.environ.get("DEFAULT_MAP", "de_dust2")
        self._last_mode = os.environ.get("DEFAULT_MODE", "competitive")
        self._last_exit_code: int | None = None
        self._last_exit_reason: str | None = None
        self._last_exit_at: str | None = None
        self._last_failure_message: str | None = None
        self._log_lock = threading.Lock()
        self._log_lines: list[str] = []

    def _sync_process_state(self, reason: str = "CS2 process exited") -> None:
        with self._lock:
            proc = self._process
            if proc is None:
                return
            return_code = proc.poll()
            if return_code is None:
                return
            self._process = None
            self._ready = False
            self._paused = False
            self._last_exit_code = return_code
            self._last_exit_reason = reason
            self._last_exit_at = datetime.now(timezone.utc).isoformat()
            if not self._last_failure_message:
                self._last_failure_message = f"{reason}; exit code={return_code}"

    def is_running(self) -> bool:
        self._sync_process_state()
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def status(self) -> dict:
        self._sync_process_state()
        with self._lock:
            running = self._process is not None and self._process.poll() is None
            return {
                "running": running,
                "pid": None if not running else self._process.pid,
                "paused": self._paused,
                "ready": self._ready,
                "map": self._last_map,
                "mode": self._last_mode,
                "exit_code": self._last_exit_code,
                "last_exit_reason": self._last_exit_reason,
                "last_exit_at": self._last_exit_at,
                "last_failure_message": self._last_failure_message,
            }

    def startup_diagnostics(self, limit: int | None = None) -> dict:
        self._sync_process_state()
        tail_limit = limit if limit is not None else max(env_int("STARTUP_LOG_TAIL_LINES", 40), 1)
        info = self.status()
        info["log_tail_lines"] = self.logs(tail_limit)
        return info

    def logs(self, limit: int = 200) -> list[str]:
        with self._log_lock:
            return self._log_lines[-limit:]

    def clear_logs(self) -> None:
        with self._log_lock:
            self._log_lines = []

    def _terminate_process(self, timeout: int = 8) -> None:
        self._sync_process_state()
        proc = self._process
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
        finally:
            self._sync_process_state(reason="CS2 process terminated during shutdown")

    def _is_process_alive(self) -> bool:
        self._sync_process_state()
        return self._process is not None and self._process.poll() is None

    def _mark_process_exited(self, context: str) -> str:
        self._sync_process_state(reason=f"CS2 process exited while {context}")
        message = self._startup_failure_message(stage=context)
        self._last_failure_message = message
        self._ready = False
        self._paused = False
        app.logger.error(
            "event=cs2_process_dead context=%s exit_code=%s last_exit_at=%s details=%s",
            context,
            self._last_exit_code,
            self._last_exit_at,
            message,
        )
        return message

    def _startup_failure_message(self, stage: str, timeout: int | None = None) -> str:
        self._sync_process_state(reason=f"CS2 process exited while {stage}")
        proc = self._process
        return_code = self._last_exit_code if proc is None else proc.poll()
        tail_limit = max(env_int("STARTUP_LOG_TAIL_LINES", 40), 1)
        tail_lines = self.logs(tail_limit)
        if timeout is None:
            reason = f"CS2 process exited while {stage}"
        else:
            reason = f"CS2 startup timed out while {stage} after {timeout}s"
        details = [reason]
        if return_code is not None:
            details.append(f"exit code={return_code}")
        if self._last_exit_at:
            details.append(f"exit_at={self._last_exit_at}")
        if tail_lines:
            details.append(f"last {len(tail_lines)} CS2 log lines:\n" + "\n".join(tail_lines))
        else:
            details.append("no CS2 log lines captured yet; check /api/logs for buffered output")
        return "; ".join(details)

    def _wait_for_port_or_exit(self, host: str, port: int, timeout: int) -> tuple[bool, str]:
        proc = self._process
        if proc is None:
            return False, "CS2 process handle is unavailable during startup"
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._sync_process_state(reason=f"CS2 process exited while opening port {host}:{port}")
            if proc.poll() is not None:
                return False, self._startup_failure_message(stage=f"opening port {host}:{port}")
            try:
                with socket.create_connection((host, port), timeout=1):
                    return True, ""
            except OSError:
                time.sleep(0.5)
        if proc.poll() is not None:
            return False, self._startup_failure_message(stage=f"opening port {host}:{port}")
        return False, self._startup_failure_message(stage=f"opening port {host}:{port}", timeout=timeout)

    def _wait_for_rcon_or_exit(self, host: str, port: int, password: str, timeout: int) -> tuple[bool, str]:
        proc = self._process
        if proc is None:
            return False, "CS2 process handle is unavailable while waiting for RCON"
        server_ip = detect_primary_ip()
        hosts = [host]
        if server_ip and server_ip not in hosts:
            hosts.append(server_ip)
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._sync_process_state(reason=f"CS2 process exited while accepting RCON on {host}:{port}")
            if proc.poll() is not None:
                return False, self._startup_failure_message(stage=f"accepting RCON on {host}:{port}")
            for target in hosts:
                try:
                    with Client(target, port, passwd=password) as client:
                        client.run("status")
                    return True, ""
                except Exception:
                    continue
            time.sleep(1)
        if proc.poll() is not None:
            return False, self._startup_failure_message(stage=f"accepting RCON on {host}:{port}")
        return False, self._startup_failure_message(stage=f"accepting RCON on {host}:{port}", timeout=timeout)

    def _run_rcon_with_retry(self, command: str) -> str:
        attempts = max(env_int("RCON_EARLY_RETRY_ATTEMPTS", 5), 1)
        base_delay = max(env_float("RCON_EARLY_RETRY_BASE_DELAY", 0.5), 0.05)
        for attempt in range(1, attempts + 1):
            if not self._is_process_alive():
                raise RuntimeError(self._mark_process_exited(context=f"running post-start RCON '{command}'"))
            try:
                return run_rcon(command)
            except Exception as exc:
                if attempt >= attempts or not is_transient_rcon_error(exc):
                    raise
                sleep_for = base_delay * (2 ** (attempt - 1))
                app.logger.warning(
                    "Transient RCON error for '%s' (attempt %s/%s): %s; retrying in %.2fs",
                    command,
                    attempt,
                    attempts,
                    exc,
                    sleep_for,
                )
                time.sleep(sleep_for)
        raise RuntimeError(f"Failed to run RCON command after retries: {command}")

    def _stabilize_rcon_after_start(self) -> bool:
        stabilization_seconds = max(env_float("RCON_STABILIZATION_SECONDS", 1.0), 0.0)
        max_attempts = max(env_int("RCON_STABILIZATION_MAX_ATTEMPTS", 6), 1)
        retry_delay = max(env_float("RCON_STABILIZATION_RETRY_DELAY", 0.5), 0.05)

        if stabilization_seconds > 0:
            app.logger.info(
                "RCON stabilization delay %.2fs before post-start cvars.",
                stabilization_seconds,
            )
            time.sleep(stabilization_seconds)

        for attempt in range(1, max_attempts + 1):
            if not self._is_process_alive():
                self._mark_process_exited(context="RCON stabilization")
                return False
            try:
                run_rcon("status")
                app.logger.info("RCON stabilization probe succeeded on attempt %s/%s.", attempt, max_attempts)
                return True
            except Exception as exc:
                if not is_transient_rcon_error(exc):
                    self._last_failure_message = f"RCON stabilization failed: {exc}"
                    app.logger.exception("RCON stabilization failed with non-transient error.")
                    return False
                if attempt >= max_attempts:
                    self._last_failure_message = (
                        f"RCON stabilization exhausted after {max_attempts} attempts: {exc}"
                    )
                    app.logger.error("%s", self._last_failure_message)
                    return False
                app.logger.warning(
                    "Transient RCON stabilization error (attempt %s/%s): %s; retrying in %.2fs",
                    attempt,
                    max_attempts,
                    exc,
                    retry_delay,
                )
                time.sleep(retry_delay)
        return False

    def build_command(self, map_entry: dict, mode: str) -> list[str]:
        exe = cs2_executable()
        if not exe.exists():
            raise RuntimeError(f"CS2 executable not found at {exe}")
        wrapper_args = resolve_cs2_exec_wrapper_args(os.environ.get("CS2_EXEC_WRAPPER"))
        server_ip = detect_primary_ip()
        game_port = env_int("GAME_PORT", 27015)
        max_players = env_int("MAX_PLAYERS", 64)
        threads = os.environ.get("THREADS", "").strip()
        workshop_collection = os.environ.get("WORKSHOP_COLLECTION_ID", "").strip()
        rcon_password = os.environ.get("RCON_PASSWORD", "").strip()
        gslt_token = os.environ.get("GSLT_TOKEN", "").strip()
        if not rcon_password:
            raise RuntimeError("RCON_PASSWORD is not set")

        args = wrapper_args + [
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

        if gslt_token:
            args.extend(["+sv_setsteamaccount", gslt_token])

        if map_entry.get("workshop"):
            args.extend(["+host_workshop_map", map_entry["id"]])
        else:
            args.extend(["+map", map_entry["id"]])

        extra_args = os.environ.get("EXTRA_ARGS", "").strip()
        if extra_args:
            args.extend(shlex.split(extra_args))

        return args

    def start(self, extra_cvars_enabled: bool | None = None) -> dict:
        with self._lock:
            if self.is_running():
                app.logger.info("Start requested but server is already running.")
                return self.status()
            self._ready = False
            self._paused = False
            self._last_failure_message = None
            self._last_exit_code = None
            self._last_exit_reason = None
            self._last_exit_at = None
            if extra_cvars_enabled is not None:
                self._extra_cvars_enabled = bool(extra_cvars_enabled)
            default_map = self._last_map or os.environ.get("DEFAULT_MAP", "de_dust2")
            default_mode = self._last_mode or os.environ.get("DEFAULT_MODE", "competitive")
            map_entry = find_map(default_map)
            if map_entry is None:
                raise RuntimeError(f"Unknown map '{default_map}'")
            command = self.build_command(map_entry, default_mode)
            cwd = Path(os.environ.get("CS2_PATH", "")).expanduser()
            child_env = build_cs2_child_env(cwd, os.environ)
            app.logger.info("CS2 startup phase=spawn command-prepared")
            app.logger.info("Command: %s", " ".join(command))
            self._process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            app.logger.info(
                "CS2 startup phase=spawned pid=%s cwd=%s",
                self._process.pid,
                cwd,
            )
            self._start_log_stream()
            server_ip = detect_primary_ip()
            game_port = env_int("GAME_PORT", 27015)
            timeout = env_int("SERVER_STARTUP_TIMEOUT", 20)
            app.logger.info("Waiting for server port %s:%s.", server_ip, game_port)
            port_ready, port_error = self._wait_for_port_or_exit(server_ip, game_port, timeout)
            if not port_ready:
                self._ready = False
                self._terminate_process()
                raise RuntimeError(port_error)
            app.logger.info("CS2 startup phase=port-open host=%s port=%s", server_ip, game_port)
            rcon_host = os.environ.get("RCON_HOST", "127.0.0.1").strip() or "127.0.0.1"
            rcon_port = env_int("RCON_PORT", 27015)
            rcon_password = os.environ.get("RCON_PASSWORD", "").strip()
            rcon_timeout = env_int("RCON_STARTUP_TIMEOUT", 10)
            app.logger.info("Waiting for RCON %s:%s.", rcon_host, rcon_port)
            rcon_ready, rcon_error = self._wait_for_rcon_or_exit(rcon_host, rcon_port, rcon_password, rcon_timeout)
            if not rcon_ready:
                self._ready = False
                self._terminate_process()
                raise RuntimeError(rcon_error)
            app.logger.info("CS2 startup phase=rcon-probe-passed host=%s port=%s", rcon_host, rcon_port)
            self._last_map = map_entry["id"]
            self._last_mode = default_mode
            self._paused = False
            app.logger.info("CS2 startup phase=post-start-cvars-scheduled ready=false")
            self._apply_default_cvars_async()
            return self.status()

    def stop(self) -> dict:
        with self._lock:
            self._sync_process_state(reason="CS2 process exited before stop")
            self._ready = False
            self._paused = False
            if not self._is_process_alive():
                return self.status()
            run_rcon("quit")
            return self.status()

    def change_map(self, map_entry: dict, mode: str) -> str:
        self._last_map = map_entry["id"]
        self._last_mode = mode
        self._ready = False
        if not self.is_running():
            return f"staged {map_entry['id']} ({mode})"
        run_rcon(f"game_alias {mode}")
        if map_entry.get("workshop"):
            response = run_rcon(f"host_workshop_map {map_entry['id']}")
        else:
            response = run_rcon(f"changelevel {map_entry['id']}")
        change_delay = max(env_int("DEFAULT_CVAR_DELAY", 4), 6)
        self._apply_default_cvars_async(delay_override=change_delay)
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

    def _apply_default_cvars_async(self, delay_override: int | None = None) -> None:
        delay = delay_override if delay_override is not None else env_int("DEFAULT_CVAR_DELAY", 4)
        post_delay = env_int("POST_RESTART_CVAR_DELAY", 2)

        def worker():
            app.logger.info("CS2 startup phase=post-start-cvars-begin")
            time.sleep(delay)
            if not self._is_process_alive():
                self._mark_process_exited(context="starting post-start cvar workflow")
                return
            if not self._stabilize_rcon_after_start():
                self._ready = False
                return
            cvars = list(DEFAULT_CVARS)
            if self._extra_cvars_enabled:
                cvars.extend(EXTRA_CVARS)
            post_start_success = False
            for command in cvars:
                if not self._is_process_alive():
                    self._mark_process_exited(context=f"applying cvar '{command}'")
                    return
                try:
                    self._run_rcon_with_retry(command)
                    post_start_success = True
                except Exception:
                    app.logger.exception("Failed to apply cvar: %s", command)
                    continue
            if not self._is_process_alive():
                self._mark_process_exited(context=f"issuing restart command '{RESTART_COMMAND}'")
                return
            try:
                self._run_rcon_with_retry(RESTART_COMMAND)
                post_start_success = True
            except Exception:
                app.logger.exception("Failed to issue restart command.")
                self._last_failure_message = "Failed to issue restart command during post-start cvars."
                return
            app.logger.info("CS2 startup phase=post-start-cvars-restart-issued")
            time.sleep(post_delay)
            for command in cvars:
                if not self._is_process_alive():
                    self._mark_process_exited(context=f"applying post-restart cvar '{command}'")
                    return
                try:
                    self._run_rcon_with_retry(command)
                    post_start_success = True
                except Exception:
                    app.logger.exception("Failed to apply post-restart cvar: %s", command)
                    continue
            if post_start_success and self._is_process_alive():
                self._ready = True
                app.logger.info("CS2 startup phase=ready ready=true")
            else:
                self._ready = False
                if not self._last_failure_message:
                    self._last_failure_message = (
                        "Post-start cvar workflow completed without successful RCON operations."
                    )
                app.logger.error("CS2 startup phase=ready ready=false reason=%s", self._last_failure_message)

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
            self._sync_process_state(reason="CS2 stdout stream ended")

        threading.Thread(target=reader, daemon=True).start()


app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")
manager = ServerManager()
api_logger = logging.getLogger("cs2control")
rcon_log_lock = threading.Lock()
rcon_log_lines: list[str] = []


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


class ApiLogHandler(logging.Handler):
    def __init__(self, limit: int = 500) -> None:
        super().__init__()
        self._limit = limit
        self._lock = threading.Lock()
        self._lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        with self._lock:
            self._lines.append(message)
            if len(self._lines) > self._limit:
                self._lines = self._lines[-self._limit :]

    def lines(self, limit: int = 200) -> list[str]:
        with self._lock:
            return self._lines[-limit:]

    def clear(self) -> None:
        with self._lock:
            self._lines = []


api_log_handler = ApiLogHandler(limit=env_int("API_LOG_BUFFER", 500))
api_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
app.logger.setLevel(logging.INFO)
app.logger.addHandler(api_log_handler)
werkzeug_logger = logging.getLogger("werkzeug")
werkzeug_logger.setLevel(logging.INFO)
werkzeug_logger.addHandler(api_log_handler)
api_logger.setLevel(logging.INFO)
api_logger.addHandler(api_log_handler)


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


def append_rcon_log(line: str) -> None:
    if not line:
        return
    with rcon_log_lock:
        rcon_log_lines.append(line)
        if len(rcon_log_lines) > 1000:
            rcon_log_lines[:] = rcon_log_lines[-800:]


def parse_bot_quota(raw: str) -> int | None:
    match = re.search(r"bot_quota\s*=\s*(\d+)", raw, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)", raw)
    if match:
        return int(match.group(1))
    return None


def parse_bot_quota_mode(raw: str) -> str | None:
    match = re.search(r"bot_quota_mode\s*=\s*(\w+)", raw, re.IGNORECASE)
    if match:
        mode = match.group(1).lower()
        if mode in {"fill", "normal"}:
            return mode
    lower = raw.lower()
    if "fill" in lower:
        return "fill"
    if "normal" in lower:
        return "normal"
    return None


def parse_bot_controllable(raw: str) -> bool | None:
    match = re.search(r"bot_controllable\s*=\s*(\d+)", raw, re.IGNORECASE)
    if match:
        return match.group(1) == "1"
    match = re.search(r"\b(0|1)\b", raw)
    if match:
        return match.group(1) == "1"
    lower = raw.lower()
    if "true" in lower:
        return True
    if "false" in lower:
        return False
    return None


@app.get("/api/status")
def api_status():
    return jsonify({"ok": True, **manager.status()})


@app.get("/api/startup-diagnostics")
def api_startup_diagnostics():
    limit = max(env_int("STARTUP_LOG_TAIL_LINES", 40), 1)
    try:
        limit = int(request.args.get("limit", limit))
    except ValueError:
        pass
    return jsonify({"ok": True, **manager.startup_diagnostics(limit=limit)})


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


@app.post("/api/logs/clear")
def api_logs_clear():
    manager.clear_logs()
    return jsonify({"ok": True})


@app.get("/api/flask-logs")
def api_flask_logs():
    limit = env_int("API_LOG_LIMIT", 200)
    try:
        limit = int(request.args.get("limit", limit))
    except ValueError:
        pass
    return jsonify({"ok": True, "lines": api_log_handler.lines(limit)})


@app.post("/api/flask-logs/clear")
def api_flask_logs_clear():
    api_log_handler.clear()
    return jsonify({"ok": True})


@app.get("/api/rcon-logs")
def api_rcon_logs():
    limit = env_int("LOG_LIMIT", 200)
    try:
        limit = int(request.args.get("limit", limit))
    except ValueError:
        pass
    with rcon_log_lock:
        lines = rcon_log_lines[-limit:]
    return jsonify({"ok": True, "lines": lines})


@app.post("/api/rcon-logs/clear")
def api_rcon_logs_clear():
    with rcon_log_lock:
        rcon_log_lines.clear()
    return jsonify({"ok": True})


@app.get("/api/bot-settings")
def api_bot_settings():
    try:
        append_rcon_log("> bot_quota")
        quota_raw = run_rcon("bot_quota")
        for line in quota_raw.split("\n"):
            if line.strip():
                append_rcon_log(line)
        append_rcon_log("> bot_quota_mode")
        mode_raw = run_rcon("bot_quota_mode")
        for line in mode_raw.split("\n"):
            if line.strip():
                append_rcon_log(line)
        append_rcon_log("> bot_controllable")
        controllable_raw = run_rcon("bot_controllable")
        for line in controllable_raw.split("\n"):
            if line.strip():
                append_rcon_log(line)
        quota = parse_bot_quota(quota_raw)
        mode = parse_bot_quota_mode(mode_raw)
        controllable = parse_bot_controllable(controllable_raw)
        if quota is None:
            return json_error("Failed to parse bot_quota response.", 500)
        if mode is None:
            return json_error("Failed to parse bot_quota_mode response.", 500)
        if controllable is None:
            return json_error("Failed to parse bot_controllable response.", 500)
        return jsonify({"ok": True, "quota": quota, "mode": mode, "controllable": controllable})
    except Exception as exc:
        append_rcon_log(f"! {exc}")
        return json_error(str(exc), 500)


@app.post("/api/start")
def api_start():
    try:
        app.logger.info("Start requested via API.")
        payload = request.get_json(silent=True) or {}
        extra_cvars_enabled = payload.get("extra_cvars_enabled")
        return jsonify({"ok": True, **manager.start(extra_cvars_enabled)})
    except Exception as exc:
        app.logger.exception("Start failed: %s", exc)
        return json_error(str(exc), 500)


@app.post("/api/stop")
def api_stop():
    try:
        app.logger.info("Stop requested via API.")
        response = run_rcon("quit")
        return jsonify({"ok": True, "response": response})
    except Exception as exc:
        app.logger.exception("Stop failed: %s", exc)
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
        append_rcon_log(f"> {command}")
        response = run_rcon(command)
        for line in response.split("\n"):
            if line.strip():
                append_rcon_log(line)
        return jsonify({"ok": True, "response": response})
    except Exception as exc:
        append_rcon_log(f"! {exc}")
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


@app.get("/shared.css")
def shared_css():
    return send_from_directory(str(SHARED_DIR), "shared.css")


@app.route("/", methods=["GET", "POST"])
def index():
    return send_from_directory(str(WEB_DIR), "index.html")


@app.get("/<path:filename>")
def static_files(filename: str):
    return send_from_directory(str(WEB_DIR), filename)


if __name__ == "__main__":
    port = env_int("WEB_PORT", 5000)
    app.run(host="0.0.0.0", port=port, debug=False)
