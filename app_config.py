from pathlib import Path

from config_loader import load_config as _load_config, resolve_default_config_path

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = resolve_default_config_path(ROOT_DIR)


def load_config(path: Path | None = None, game: str | None = None) -> None:
    _load_config(path or DEFAULT_CONFIG_PATH, game=game)
