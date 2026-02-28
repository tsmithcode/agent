from __future__ import annotations

import json
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

from ..data.paths import Paths

DEFAULT_PLUGINS: Dict[str, bool] = {
    "dashboard": True,
    "eval": True,
    "snapshots": True,
    "metrics": True,
    "tasks": True,
    "fetch_drive": True,
}


@dataclass(frozen=True)
class PluginContract:
    name: str
    description: str
    commands: list[str]
    required_files: list[str]
    required_modules: list[str] | None = None
    depends_on: list[str] | None = None


def plugin_contracts() -> Dict[str, PluginContract]:
    return {
        "dashboard": PluginContract(
            name="dashboard",
            description="Live telemetry dashboard (Streamlit).",
            commands=["dev dashboard"],
            required_files=["core/cg/addons/dashboard_app.py", "core/cg/addons/dashboard_data.py"],
            required_modules=["streamlit", "pandas", "altair"],
        ),
        "eval": PluginContract(
            name="eval",
            description="Native evaluation harness.",
            commands=["dev eval"],
            required_files=["core/cg/addons/eval_harness.py"],
        ),
        "snapshots": PluginContract(
            name="snapshots",
            description="CLI snapshot test runner.",
            commands=["dev snaps"],
            required_files=["core/tests/test_cli_snapshots.py"],
        ),
        "metrics": PluginContract(
            name="metrics",
            description="Telemetry aggregation and reporting.",
            commands=["dev metrics"],
            required_files=["core/cg/telemetry.py"],
        ),
        "tasks": PluginContract(
            name="tasks",
            description="Beginner workflow templates.",
            commands=["tasks list", "tasks run"],
            required_files=["core/cg/cli/command_groups.py"],
        ),
        "fetch_drive": PluginContract(
            name="fetch_drive",
            description="Google Drive folder download workflow.",
            commands=["fetch"],
            required_files=["core/cg/addons/gdrive_fetch.py"],
        ),
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


def any_enabled(plugins: Dict[str, bool], names: Iterable[str]) -> bool:
    return any(plugin_enabled(plugins, n) for n in names)


def resolve_plugins(paths: Paths) -> Dict[str, bool]:
    """Return effective plugin map (config + availability checks)."""
    resolved = load_plugins(paths)
    contracts = plugin_contracts()
    for name, enabled in list(resolved.items()):
        if not enabled:
            continue
        contract = contracts.get(name)
        if contract is None:
            continue
        if any(not (paths.agent_root / req).exists() for req in contract.required_files):
            resolved[name] = False
            continue
        if contract.required_modules and any(importlib.util.find_spec(mod) is None for mod in contract.required_modules):
            resolved[name] = False
    return resolved


def validate_plugin_contracts(paths: Paths, plugins: Dict[str, bool]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    contracts = plugin_contracts()

    for name in plugins:
        if name not in contracts:
            warnings.append(f"Unknown plugin in config: {name}")

    for name, contract in contracts.items():
        enabled = plugin_enabled(plugins, name)
        if not enabled:
            continue
        for req in contract.required_files:
            if not (paths.agent_root / req).exists():
                errors.append(f"Plugin '{name}' missing required file: {req}")
        if contract.required_modules:
            for mod in contract.required_modules:
                if importlib.util.find_spec(mod) is None:
                    errors.append(f"Plugin '{name}' missing required dependency module: {mod}")
        if contract.depends_on:
            for dep in contract.depends_on:
                if not plugin_enabled(plugins, dep):
                    errors.append(f"Plugin '{name}' requires '{dep}' to be enabled.")
    return errors, warnings
