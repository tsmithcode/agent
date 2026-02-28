from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .paths import Paths

DEFAULT_PLUGINS: Dict[str, bool] = {
    "dashboard": True,
    "eval": True,
    "snapshots": True,
    "metrics": True,
    "tasks": True,
    "fetch_drive": True,
}


def plugins_path(paths: Paths) -> Path:
    return (paths.agent_root / "config" / "plugins.json").resolve()


def load_plugins(paths: Paths) -> Dict[str, bool]:
    path = plugins_path(paths)
    if not path.exists():
        return DEFAULT_PLUGINS.copy()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return DEFAULT_PLUGINS.copy()
    merged = DEFAULT_PLUGINS.copy()
    for k, v in data.items():
        merged[str(k)] = bool(v)
    return merged


def plugin_enabled(plugins: Dict[str, bool], name: str) -> bool:
    return bool(plugins.get(name, False))
