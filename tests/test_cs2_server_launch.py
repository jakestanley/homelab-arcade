import importlib
import logging
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


class FakeProcess:
    def __init__(self, code: int | None = None, poll_sequence: list[int | None] | None = None, pid: int = 1234):
        self._code = code
        self._poll_sequence = list(poll_sequence or [])
        self.pid = pid
        self.stdout = iter(())

    def poll(self):
        if self._poll_sequence:
            value = self._poll_sequence.pop(0)
            if value is not None:
                self._code = value
            return value
        return self._code

    def terminate(self):
        if self._code is None:
            self._code = 0

    def wait(self, timeout=None):
        if self._code is None:
            self._code = 0
        return self._code

    def kill(self):
        if self._code is None:
            self._code = -9


class ImmediateThread:
    def __init__(self, target=None, daemon=None):
        self._target = target
        self.daemon = daemon

    def start(self):
        if self._target is not None:
            self._target()


def load_cs2_server_module():
    fake_flask = types.ModuleType("flask")

    class FakeFlask:
        def __init__(self, *args, **kwargs) -> None:
            self.logger = logging.getLogger("test.cs2.server")

        def after_request(self, fn):
            return fn

        def get(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

        def post(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

        def route(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

        def run(self, *args, **kwargs):
            return None

    fake_flask.Flask = FakeFlask
    fake_flask.jsonify = lambda *args, **kwargs: {"args": args, "kwargs": kwargs}
    fake_flask.request = types.SimpleNamespace(
        args={},
        headers={},
        method="GET",
        path="/",
        get_json=lambda silent=True: {},
    )
    fake_flask.send_from_directory = lambda *args, **kwargs: {"args": args, "kwargs": kwargs}

    fake_rcon = types.ModuleType("rcon")
    fake_rcon_source = types.ModuleType("rcon.source")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, *parts):
            return "ok"

    fake_rcon_source.Client = FakeClient
    fake_rcon.source = fake_rcon_source

    with mock.patch.dict(
        sys.modules,
        {
            "flask": fake_flask,
            "rcon": fake_rcon,
            "rcon.source": fake_rcon_source,
        },
    ):
        with mock.patch("signal.signal", lambda *args, **kwargs: None):
            sys.modules.pop("cs2.server", None)
            return importlib.import_module("cs2.server")


class Cs2ServerLaunchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = load_cs2_server_module()

    def setUp(self) -> None:
        self._environ = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._environ)

    def test_build_command_prepends_wrapper_when_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cs2_path = Path(tmpdir)
            exe = cs2_path / "game" / "bin" / "linuxsteamrt64" / "cs2"
            exe.parent.mkdir(parents=True, exist_ok=True)
            exe.write_text("", encoding="utf-8")

            os.environ["CS2_PATH"] = str(cs2_path)
            os.environ["RCON_PASSWORD"] = "secret"
            os.environ["CS2_EXEC_WRAPPER"] = "steam-run"

            manager = self.server.ServerManager()
            with mock.patch.object(self.server, "detect_primary_ip", return_value="192.168.1.10"):
                command = manager.build_command({"workshop": False, "id": "de_dust2"}, "competitive")

            self.assertEqual(command[0], "steam-run")
            self.assertEqual(command[1], str(exe))

    def test_build_command_unset_wrapper_keeps_command_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cs2_path = Path(tmpdir)
            exe = cs2_path / "game" / "bin" / "linuxsteamrt64" / "cs2"
            exe.parent.mkdir(parents=True, exist_ok=True)
            exe.write_text("", encoding="utf-8")

            os.environ["CS2_PATH"] = str(cs2_path)
            os.environ["RCON_PASSWORD"] = "secret"
            os.environ.pop("CS2_EXEC_WRAPPER", None)

            manager = self.server.ServerManager()
            with mock.patch.object(self.server, "detect_primary_ip", return_value="192.168.1.10"):
                command = manager.build_command({"workshop": False, "id": "de_dust2"}, "competitive")

            self.assertEqual(command[0], str(exe))

    def test_invalid_wrapper_raises_runtime_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cs2_path = Path(tmpdir)
            exe = cs2_path / "game" / "bin" / "linuxsteamrt64" / "cs2"
            exe.parent.mkdir(parents=True, exist_ok=True)
            exe.write_text("", encoding="utf-8")

            os.environ["CS2_PATH"] = str(cs2_path)
            os.environ["RCON_PASSWORD"] = "secret"
            os.environ["CS2_EXEC_WRAPPER"] = "'broken"

            manager = self.server.ServerManager()
            with mock.patch.object(self.server, "detect_primary_ip", return_value="192.168.1.10"):
                with self.assertRaisesRegex(RuntimeError, "CS2_EXEC_WRAPPER"):
                    manager.build_command({"workshop": False, "id": "de_dust2"}, "competitive")

    def test_build_cs2_child_env_includes_required_library_paths_on_linux(self) -> None:
        env = self.server.build_cs2_child_env(
            Path("/srv/cs2"),
            {"LD_LIBRARY_PATH": "/opt/lib:/usr/lib"},
            is_windows=False,
        )
        self.assertEqual(
            env["LD_LIBRARY_PATH"],
            "/srv/cs2/game/bin/linuxsteamrt64:/srv/cs2/game/csgo/bin/linuxsteamrt64:/opt/lib:/usr/lib",
        )

    def test_build_cs2_child_env_is_unchanged_on_windows(self) -> None:
        env = self.server.build_cs2_child_env(
            Path("C:/cs2"),
            {"LD_LIBRARY_PATH": "C:/existing"},
            is_windows=True,
        )
        self.assertEqual(env["LD_LIBRARY_PATH"], "C:/existing")

    def test_status_reflects_process_exit_promptly(self) -> None:
        manager = self.server.ServerManager()
        manager._process = FakeProcess(code=23)
        manager._ready = True
        manager._paused = True

        status = manager.status()

        self.assertFalse(status["running"])
        self.assertFalse(status["ready"])
        self.assertFalse(status["paused"])
        self.assertEqual(status["exit_code"], 23)
        self.assertIsNotNone(status["last_exit_reason"])
        self.assertIsNotNone(status["last_exit_at"])

    def test_apply_default_cvars_aborts_when_process_dead(self) -> None:
        manager = self.server.ServerManager()
        manager._process = FakeProcess(code=42)
        manager._ready = True
        manager._log_lines = ["line one", "line two"]

        with mock.patch.object(self.server.threading, "Thread", ImmediateThread):
            with mock.patch.object(self.server.time, "sleep", lambda *_args, **_kwargs: None):
                with mock.patch.object(manager, "_run_rcon_with_retry") as run_retry:
                    manager._apply_default_cvars_async(delay_override=0)

        run_retry.assert_not_called()
        status = manager.status()
        self.assertFalse(status["ready"])
        self.assertEqual(status["exit_code"], 42)
        self.assertIsNotNone(status["last_failure_message"])

    def test_rcon_stabilization_retries_then_succeeds(self) -> None:
        manager = self.server.ServerManager()
        manager._process = FakeProcess(code=None)
        os.environ["RCON_STABILIZATION_SECONDS"] = "0"
        os.environ["RCON_STABILIZATION_MAX_ATTEMPTS"] = "3"
        os.environ["RCON_STABILIZATION_RETRY_DELAY"] = "0"

        calls = {"count": 0}

        def fake_run_rcon(_command):
            calls["count"] += 1
            if calls["count"] == 1:
                raise ConnectionRefusedError("refused")
            return "ok"

        with mock.patch.object(self.server, "run_rcon", side_effect=fake_run_rcon):
            with mock.patch.object(self.server.time, "sleep", lambda *_args, **_kwargs: None):
                ok = manager._stabilize_rcon_after_start()

        self.assertTrue(ok)
        self.assertEqual(calls["count"], 2)

    def test_ready_only_after_successful_post_start_operations(self) -> None:
        manager = self.server.ServerManager()
        manager._process = FakeProcess(code=None)
        manager._ready = False

        with mock.patch.object(self.server.threading, "Thread", ImmediateThread):
            with mock.patch.object(self.server.time, "sleep", lambda *_args, **_kwargs: None):
                with mock.patch.object(manager, "_stabilize_rcon_after_start", return_value=True):
                    with mock.patch.object(manager, "_run_rcon_with_retry", return_value="ok"):
                        manager._apply_default_cvars_async(delay_override=0)

        self.assertTrue(manager.status()["ready"])

    def test_ready_stays_false_when_stabilization_fails(self) -> None:
        manager = self.server.ServerManager()
        manager._process = FakeProcess(code=None)
        manager._ready = False

        with mock.patch.object(self.server.threading, "Thread", ImmediateThread):
            with mock.patch.object(self.server.time, "sleep", lambda *_args, **_kwargs: None):
                with mock.patch.object(manager, "_stabilize_rcon_after_start", return_value=False):
                    with mock.patch.object(manager, "_run_rcon_with_retry") as run_retry:
                        manager._apply_default_cvars_async(delay_override=0)

        run_retry.assert_not_called()
        self.assertFalse(manager.status()["ready"])


if __name__ == "__main__":
    unittest.main()
