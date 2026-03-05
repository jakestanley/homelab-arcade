import importlib
import logging
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


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


if __name__ == "__main__":
    unittest.main()
