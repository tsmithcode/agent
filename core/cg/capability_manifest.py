from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import Paths
from .policy import Policy
from .tool_registry import list_tools


@dataclass(frozen=True)
class ManifestValidation:
    ok: bool
    errors: list[str]
    warnings: list[str]


def manifest_path(paths: Paths) -> Path:
    return (paths.agent_root / "config" / "capabilities.manifest.json").resolve()


def load_manifest(paths: Paths) -> dict[str, Any]:
    path = manifest_path(paths)
    if not path.exists():
        raise FileNotFoundError(f"Capability manifest missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _command_names(app) -> set[str]:
    names: set[str] = set()
    for k in app.registered_commands:
        names.add(str(getattr(k, "name", "") or "").strip())
    for g in app.registered_groups:
        gname = str(getattr(g, "name", "") or "").strip()
        grp = getattr(g, "typer_instance", None)
        if not gname or grp is None:
            continue
        for c in grp.registered_commands:
            cname = str(getattr(c, "name", "") or "").strip()
            if cname:
                names.add(f"{gname} {cname}")
    return {n for n in names if n}


def validate_manifest(*, paths: Paths, policy: Policy, app) -> ManifestValidation:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        manifest = load_manifest(paths)
    except Exception as e:
        return ManifestValidation(ok=False, errors=[str(e)], warnings=[])

    required_commands = set(str(x).strip() for x in (manifest.get("required_commands") or []) if str(x).strip())
    actual_commands = _command_names(app)
    missing_cmds = sorted(required_commands - actual_commands)
    if missing_cmds:
        errors.append(f"Missing required CLI commands from manifest: {', '.join(missing_cmds)}")

    required_handlers = set(str(x).strip() for x in (manifest.get("deterministic_handlers") or []) if str(x).strip())
    actual_handlers = {t.handler_id for t in list_tools()}
    missing_handlers = sorted(required_handlers - actual_handlers)
    if missing_handlers:
        errors.append(f"Missing deterministic handlers from registry: {', '.join(missing_handlers)}")

    policy_expect = manifest.get("policy_expectations") or {}
    need_allow = [str(x).strip() for x in (policy_expect.get("command_allowlist_contains") or []) if str(x).strip()]
    allow_miss = [x for x in need_allow if x not in policy.command_allowlist]
    if allow_miss:
        warnings.append(f"Policy allowlist missing recommended commands: {', '.join(allow_miss)}")

    profiles_dir = (paths.agent_root / "config" / "policy.profiles").resolve()
    required_profiles = [str(x).strip() for x in (policy_expect.get("required_profiles") or []) if str(x).strip()]
    for tier in required_profiles:
        if not (profiles_dir / f"{tier}.json").exists():
            errors.append(f"Missing required policy profile: {tier}.json")

    return ManifestValidation(ok=len(errors) == 0, errors=errors, warnings=warnings)
