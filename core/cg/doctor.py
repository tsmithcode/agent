from __future__ import annotations

import os
import shutil
import socket
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from .cli_ui import COLOR_RULES, print_section
from .capability_manifest import validate_manifest
from .command_groups import detect_active_policy_tier, policy_profiles_dir
from .env import get_openai_api_key, load_project_dotenv
from .memory import LongTermMemory
from .paths import Paths
from .policy import Policy
from .tool_registry import list_tools
from .plugins import load_plugins, plugin_enabled


def doctor_once(console: Console, *, verbose: bool = False, app=None) -> dict[str, int]:
    load_project_dotenv()
    rows: list[tuple[str, str, str]] = []
    policy_path: Optional[Path] = None

    api_key = get_openai_api_key()
    rows.append(("OPENAI_API_KEY", "PASS" if api_key else "WARN", "Set" if api_key else "Missing"))

    policy: Optional[Policy] = None
    paths: Optional[Paths] = None
    try:
        paths = Paths.resolve()
        rows.append(("Paths.resolve()", "PASS", str(paths.agent_root)))
    except Exception as e:
        rows.append(("Paths.resolve()", "FAIL", str(e)))

    if paths is not None:
        policy_path = (paths.home / "agent" / "config" / "policy.json").resolve()
        try:
            policy = Policy.load(str(policy_path))
            rows.append(("Policy.load()", "PASS", str(policy_path)))
        except Exception as e:
            rows.append(("Policy.load()", "FAIL", str(e)))

    if paths is not None:
        workspace_exists = paths.workspace.exists()
        rows.append(("Workspace path", "PASS" if workspace_exists else "FAIL", str(paths.workspace)))
        write_ok = os.access(paths.workspace, os.W_OK)
        rows.append(("Workspace writable", "PASS" if write_ok else "FAIL", "yes" if write_ok else "no"))
        read_ok = os.access(paths.workspace, os.R_OK)
        rows.append(("Workspace readable", "PASS" if read_ok else "FAIL", "yes" if read_ok else "no"))

        if verbose:
            tracked_paths: list[tuple[str, Path, bool]] = [
                ("Path: home", paths.home, True),
                ("Path: agent_root", paths.agent_root, True),
                ("Path: workspace", paths.workspace, True),
                ("Path: host_ai", paths.host_ai, True),
                ("Path: memory_root", paths.memory_root, True),
                ("Path: chroma_dir", paths.chroma_dir, True),
                ("Path: logs_dir", paths.logs_dir, True),
                ("Path: artifacts_dir", paths.artifacts_dir, True),
            ]
            if policy_path is not None:
                tracked_paths.append(("Path: policy.json", policy_path, False))
            for label, p, should_be_dir in tracked_paths:
                exists = p.exists()
                status = "PASS" if exists else "FAIL"
                kind = "dir" if should_be_dir else "file"
                details = f"{p} ({kind}, {'exists' if exists else 'missing'})"
                rows.append((label, status, details))

    git_path = shutil.which("git")
    rows.append(("git binary", "PASS" if git_path else "WARN", git_path or "Not found"))

    plugins = load_plugins(paths) if paths is not None else {}
    rows.append(("Plugins file", "PASS" if plugins else "WARN", "config/plugins.json"))
    for name, enabled in plugins.items():
        rows.append((f"Plugin: {name}", "PASS" if enabled else "WARN", "enabled" if enabled else "disabled"))

    try:
        host = socket.gethostbyname("api.openai.com")
        rows.append(("DNS api.openai.com", "PASS", host))
    except Exception as e:
        rows.append(("DNS api.openai.com", "WARN", str(e)))

    if policy is not None:
        rows.append(("Policy tier", "PASS", detect_active_policy_tier(paths) if paths is not None else "unknown"))
        if paths is not None:
            profiles = policy_profiles_dir(paths)
            for name in ("cheap", "base", "max"):
                exists = (profiles / f"{name}.json").exists()
                rows.append((f"Policy profile: {name}", "PASS" if exists else "FAIL", str((profiles / f"{name}.json"))))
        rows.append(("Execution mode", "PASS", policy.execution_mode()))
        rows.append(
            (
                "Cost posture",
                "PASS",
                (
                    f"max_tokens={policy.max_completion_tokens()} | max_output_chars={policy.max_output_chars()} | "
                    f"max_memory_items={policy.max_memory_items()} | max_memory_chars={policy.max_memory_chars()}"
                ),
            )
        )
        rows.append(
            (
                "Safety posture",
                "PASS",
                (
                    f"deny_commands={len(policy.command_denylist)} | deny_paths={len(policy.denied_paths)} | "
                    f"allow_domains={len(policy.allow_domains())}"
                ),
            )
        )
        rows.append(
            (
                "Deterministic routing",
                "PASS" if policy.enable_deterministic_routing() else "WARN",
                f"enabled={policy.enable_deterministic_routing()} threshold={policy.deterministic_confidence_threshold():.2f}",
            )
        )
        rows.append(("LLM model", "PASS", policy.llm_model()))
        rows.append(("Deterministic tools", "PASS", f"registered={len(list_tools())}"))

    if paths is not None and policy is not None and app is not None:
        mv = validate_manifest(paths=paths, policy=policy, app=app)
        rows.append(("Capability manifest", "PASS" if mv.ok else "FAIL", "validated"))
        for w in mv.warnings:
            rows.append(("Capability warning", "WARN", w))
        for e in mv.errors:
            rows.append(("Capability error", "FAIL", e))

    if paths is not None:
        api_key_for_mem = get_openai_api_key()
        try:
            mem = LongTermMemory(
                chroma_dir=str(paths.chroma_dir),
                collection_name="cg_openclaw_memory",
                openai_api_key=api_key_for_mem,
            )
            mem_count = mem.collection.count()
            newest_ts = ""
            if mem_count > 0:
                got = mem.collection.get(include=["metadatas"], limit=min(mem_count, 200))
                metas = got.get("metadatas", []) or []
                ts_values = [str((m or {}).get("ts_utc") or "") for m in metas if (m or {}).get("ts_utc")]
                newest_ts = max(ts_values) if ts_values else ""
            retrieval_mode = "semantic" if mem.embedder is not None else "recent_fallback"
            detail = f"items={mem_count} | retrieval_mode={retrieval_mode}"
            if newest_ts:
                detail += f" | newest_ts={newest_ts}"
            rows.append(("Memory health", "PASS", detail))
        except Exception as e:
            rows.append(("Memory health", "WARN", str(e)))

    passes = warns = fails = 0
    table = Table(title="CAD Guardian Doctor Report")
    table.add_column("Check", style=COLOR_RULES["section_header"], no_wrap=True)
    table.add_column("Status", style=COLOR_RULES["text"], no_wrap=True)
    table.add_column("Detail", style=COLOR_RULES["text"], overflow="fold")
    for name, status, detail in rows:
        if status == "PASS":
            passes += 1
            status_fmt = f"[{COLOR_RULES['success']}]PASS[/{COLOR_RULES['success']}]"
        elif status == "WARN":
            warns += 1
            status_fmt = f"[{COLOR_RULES['warning']}]WARN[/{COLOR_RULES['warning']}]"
        else:
            fails += 1
            status_fmt = f"[{COLOR_RULES['error']}]FAIL[/{COLOR_RULES['error']}]"
        table.add_row(name, status_fmt, detail)

    console.print(table)
    print_section(
        console,
        title="Doctor Summary",
        body=(
            f"checks={len(rows)} | pass={passes} | warn={warns} | fail={fails}\n"
            "Tip: Resolve FAIL first, then WARN for best user experience."
        ),
    )

    if warns or fails:
        fixes: list[str] = []
        check_to_detail = {name: detail for name, _status, detail in rows}
        if "OPENAI_API_KEY" in check_to_detail and "Missing" in check_to_detail["OPENAI_API_KEY"]:
            fixes.append("Set OPENAI_API_KEY to enable LLM ask/run fallback.")
        if "DNS api.openai.com" in check_to_detail and ("not known" in check_to_detail["DNS api.openai.com"]):
            fixes.append("Fix DNS/network connectivity for api.openai.com.")
        if "Workspace writable" in check_to_detail and check_to_detail["Workspace writable"] != "yes":
            fixes.append("Grant write access to workspace path.")
        if fixes:
            print_section(console, title="Doctor Fix Hints", body="\n".join(f"- {f}" for f in fixes))
    return {"checks": len(rows), "pass": passes, "warn": warns, "fail": fails}
