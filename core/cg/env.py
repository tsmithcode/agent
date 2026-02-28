from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_project_dotenv() -> None:
    """Load .env from common CAD Guardian roots without overriding existing env."""
    here = Path(__file__).resolve()
    core_root = here.parents[1]   # .../agent/core
    agent_root = here.parents[2]  # .../agent

    candidates = [
        Path.cwd() / ".env",
        core_root / ".env",
        agent_root / ".env",
    ]
    seen: set[Path] = set()
    for path in candidates:
        p = path.resolve()
        if p in seen:
            continue
        seen.add(p)
        if p.exists():
            load_dotenv(dotenv_path=p, override=False)


def get_openai_api_key() -> str | None:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    return key or None


def load_and_get_openai_api_key() -> str | None:
    load_project_dotenv()
    return get_openai_api_key()
