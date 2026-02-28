from __future__ import annotations

import os
import shutil
import socket
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..data.env import get_openai_api_key, load_project_dotenv
from ..data.memory import LongTermMemory
from ..data.paths import Paths
from ..safety.policy import Policy


STATUS_STYLE = {
    "PASS": "bold green",
    "WARN": "bold yellow",
    "FAIL": "bold red",
}


def _status_cell(status: str) -> str:
    tone = STATUS_STYLE.get(status, "white")
    return f"[{tone}]{status}[/{tone}]"


def doctor_once(console: Console, *, verbose: bool = False) -> dict[str, int]:
    load_project_dotenv()
    rows: list[tuple[str, str, str]] = []

    api_key = get_openai_api_key()
    rows.append(("OPENAI_API_KEY", "PASS" if api_key else "WARN", "set" if api_key else "missing"))

    try:
        paths = Paths.resolve()
        rows.append(("Paths.resolve", "PASS", str(paths.agent_root)))
    except Exception as e:
        paths = None
        rows.append(("Paths.resolve", "FAIL", str(e)))

    if paths is not None:
        policy_path = (paths.home / "agent" / "config" / "policy.json").resolve()
        try:
            policy = Policy.load(str(policy_path))
            rows.append(("Policy.load", "PASS", str(policy_path)))
            rows.append(("LLM model", "PASS", policy.llm_model()))
            rows.append(("Execution mode", "PASS", policy.execution_mode()))
        except Exception as e:
            policy = None
            rows.append(("Policy.load", "FAIL", str(e)))

        rows.append(("Workspace exists", "PASS" if paths.workspace.exists() else "FAIL", str(paths.workspace)))
        rows.append(("Workspace readable", "PASS" if os.access(paths.workspace, os.R_OK) else "FAIL", "yes" if os.access(paths.workspace, os.R_OK) else "no"))
        rows.append(("Workspace writable", "PASS" if os.access(paths.workspace, os.W_OK) else "FAIL", "yes" if os.access(paths.workspace, os.W_OK) else "no"))

        if verbose:
            for label, value in (
                ("home", paths.home),
                ("agent_root", paths.agent_root),
                ("workspace", paths.workspace),
                ("logs_dir", paths.logs_dir),
                ("artifacts_dir", paths.artifacts_dir),
                ("chroma_dir", paths.chroma_dir),
            ):
                p = Path(value)
                rows.append((f"Path: {label}", "PASS" if p.exists() else "FAIL", str(p)))

        try:
            mem = LongTermMemory(chroma_dir=str(paths.chroma_dir), collection_name="cg_memory", openai_api_key=api_key)
            count = len(mem._read_all())
            rows.append(("Memory health", "PASS", f"items={count}"))
        except Exception as e:
            rows.append(("Memory health", "WARN", str(e)))

    git_path = shutil.which("git")
    rows.append(("git binary", "PASS" if git_path else "WARN", git_path or "not found"))

    try:
        host = socket.gethostbyname("api.openai.com")
        rows.append(("DNS api.openai.com", "PASS", host))
    except Exception as e:
        rows.append(("DNS api.openai.com", "WARN", str(e)))

    pass_count = warn_count = fail_count = 0
    table = Table(title="CAD Guardian Doctor Report")
    table.add_column("Check", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Detail", overflow="fold")

    for name, status, detail in rows:
        if status == "PASS":
            pass_count += 1
        elif status == "WARN":
            warn_count += 1
        else:
            fail_count += 1
        table.add_row(name, _status_cell(status), detail)

    console.print(table)
    console.print(
        f"\nchecks={len(rows)} pass={pass_count} warn={warn_count} fail={fail_count}\n"
        "Resolve FAIL first, then WARN."
    )

    return {"checks": len(rows), "pass": pass_count, "warn": warn_count, "fail": fail_count}
