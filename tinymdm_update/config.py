from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TypedDict

CONFIG_PATH = Path.home() / ".config" / "tinymdm-update" / "config.json"
STORE_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class ConfigError(Exception):
    pass


class AppConfig(TypedDict):
    id: str
    app_type: str
    name: str


class Config(TypedDict, total=False):
    watched_policy_ids: list[str]
    tracked_apps: list[AppConfig]
    update_history: dict[str, str]


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config file is corrupted ({path}): {exc}") from exc


def save_config(cfg: Config, path: Path = CONFIG_PATH) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg, indent=2))
    except OSError as exc:
        raise ConfigError(f"Could not save config to {path}: {exc}") from exc


def parse_store_date(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, STORE_DATE_FORMAT)
    except (ValueError, TypeError):
        return None


def get_last_update(cfg: Config, policy_id: str, app_id: str) -> datetime | None:
    raw = cfg.get("update_history", {}).get(f"{policy_id}:{app_id}")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def record_update(cfg: Config, policy_id: str, app_id: str) -> None:
    cfg.setdefault("update_history", {})[f"{policy_id}:{app_id}"] = datetime.now().isoformat()


def extract_version(app: dict) -> str:
    return (
        app.get("version_name")
        or app.get("version")
        or str(app.get("version_code") or "")
        or "?"
    )
