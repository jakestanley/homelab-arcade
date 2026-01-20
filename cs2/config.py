import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "config.yaml"


def load_config(path: Path | None = None, game: str | None = None) -> None:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return
    raw = config_path.read_text(encoding="utf-8")
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
