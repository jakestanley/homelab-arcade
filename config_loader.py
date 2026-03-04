import os
from pathlib import Path

CONFIG_PATH_ENV_VAR = "HOMELAB_ARCADE_CONFIG_PATH"


def resolve_default_config_path(root_dir: Path) -> Path:
    raw = os.environ.get(CONFIG_PATH_ENV_VAR, "").strip()
    if not raw:
        return root_dir / "config.yaml"

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = root_dir / path
    return path


def load_config(path: Path, game: str | None = None) -> None:
    if not path.exists():
        return
    raw = path.read_text(encoding="utf-8")
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
