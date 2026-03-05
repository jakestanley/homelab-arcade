import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import types
import sys

import config_loader


class ConfigLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._environ = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._environ)

    def test_missing_config_path_logs_warning_with_resolved_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            os.environ[config_loader.CONFIG_PATH_ENV_VAR] = "missing/config.yaml"
            os.environ.pop(config_loader.CONFIG_REQUIRED_ENV_VAR, None)
            resolved = config_loader.resolve_default_config_path(root)

            with self.assertLogs("homelab_arcade.config", level="WARNING") as logs:
                config_loader.load_config(resolved)

            combined = "\n".join(logs.output)
            self.assertIn(str((root / "missing" / "config.yaml").resolve()), combined)

    def test_missing_config_path_raises_in_strict_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            os.environ[config_loader.CONFIG_PATH_ENV_VAR] = "missing/config.yaml"
            os.environ[config_loader.CONFIG_REQUIRED_ENV_VAR] = "1"
            resolved = config_loader.resolve_default_config_path(root)

            with self.assertRaisesRegex(RuntimeError, str((root / "missing" / "config.yaml").resolve())):
                config_loader.load_config(resolved)

    def test_unreadable_config_path_raises_in_strict_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.yaml"
            path.write_text("portal_port: 80\n", encoding="utf-8")
            os.environ[config_loader.CONFIG_PATH_ENV_VAR] = str(path)
            os.environ[config_loader.CONFIG_REQUIRED_ENV_VAR] = "1"

            with mock.patch.object(Path, "read_text", side_effect=PermissionError("permission denied")):
                with self.assertRaisesRegex(RuntimeError, str(path.resolve())):
                    config_loader.load_config(path)

    def test_load_config_still_applies_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.yaml"
            path.write_text(
                "portal_port: 8080\n"
                "cs2:\n"
                "  web_port: 5000\n",
                encoding="utf-8",
            )
            os.environ.pop("PORTAL_PORT", None)
            os.environ.pop("WEB_PORT", None)

            fake_yaml = types.SimpleNamespace(
                safe_load=lambda _raw: {"portal_port": 8080, "cs2": {"web_port": 5000}}
            )
            with mock.patch.dict(sys.modules, {"yaml": fake_yaml}):
                config_loader.load_config(path, game="cs2")

            self.assertEqual(os.environ.get("PORTAL_PORT"), "8080")
            self.assertEqual(os.environ.get("WEB_PORT"), "5000")


if __name__ == "__main__":
    unittest.main()
