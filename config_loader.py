import os
import logging
from pathlib import Path

CONFIG_PATH_ENV_VAR = "HOMELAB_ARCADE_CONFIG_PATH"
CONFIG_REQUIRED_ENV_VAR = "HOMELAB_ARCADE_CONFIG_REQUIRED"

logger = logging.getLogger("homelab_arcade.config")


def resolve_default_config_path(root_dir: Path) -> Path:
    raw = os.environ.get(CONFIG_PATH_ENV_VAR, "").strip()
    if not raw:
        return root_dir / "config.yaml"

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = root_dir / path
    return path


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_config(path: Path, game: str | None = None) -> None:
    configured_raw = os.environ.get(CONFIG_PATH_ENV_VAR, "").strip()
    strict_required = env_bool(CONFIG_REQUIRED_ENV_VAR, default=False)
    resolved_path = path.expanduser().resolve(strict=False)
    if not path.exists():
        if configured_raw:
            message = f"{CONFIG_PATH_ENV_VAR} resolved to missing path: {resolved_path}"
            if strict_required:
                logger.error(message)
                raise RuntimeError(message)
            logger.warning(message)
        return
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        message = f"Failed to read config file at {resolved_path}: {exc}"
        if configured_raw:
            if strict_required:
                logger.error(message)
                raise RuntimeError(message) from exc
            logger.warning(message)
            return
        if strict_required:
            logger.error(message)
            raise RuntimeError(message) from exc
        return
    if not raw.strip():
        return
    try:
        import yaml
    except Exception as exc:
        raise RuntimeError("PyYAML is required to parse config.yaml. Install pyyaml.") from exc
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        return

    initial_env = set(os.environ.keys())

    def set_env_value(key: str, value, allow_override: bool) -> None:
        if value is None:
            return
        env_key = str(key).strip().upper()
        if env_key in initial_env:
            return
        if not allow_override and env_key in os.environ:
            return
        os.environ[env_key] = str(value)

    for key, value in data.items():
        if isinstance(value, dict):
            continue
        set_env_value(key, value, allow_override=False)

    if game:
        game_config = data.get(game)
        if isinstance(game_config, dict):
            for key, value in game_config.items():
                set_env_value(key, value, allow_override=True)
