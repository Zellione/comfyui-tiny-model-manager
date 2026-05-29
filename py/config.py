import os

_ext_dir: str = ""


def init(ext_dir: str):
    global _ext_dir
    _ext_dir = ext_dir
    os.makedirs(data_dir(), exist_ok=True)
    os.makedirs(media_dir(), exist_ok=True)


def data_dir() -> str:
    return os.path.join(_ext_dir, "data")


def media_dir() -> str:
    settings = load_settings()
    custom = settings.get("media_dir", "")
    if custom and os.path.isabs(custom):
        return custom
    return os.path.join(data_dir(), "media")


def db_path() -> str:
    return os.path.join(data_dir(), "models.db")


def settings_path() -> str:
    return os.path.join(data_dir(), "settings.json")


def load_settings() -> dict:
    import json

    path = os.path.join(_ext_dir, "data", "settings.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_settings(data: dict):
    import json

    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
