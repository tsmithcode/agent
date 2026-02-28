from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _resolve_path(value: str) -> str:
    return str(Path(os.path.expanduser(value)).resolve())


@dataclass(frozen=True)
class Policy:
    allowed_write_roots: list[str]
    allowed_read_roots: list[str]
    denied_paths: list[str]
    command_allowlist: set[str]
    command_denylist: set[str]
    destructive_command_controls: dict[str, Any]
    git_controls: dict[str, Any]
    network_controls: dict[str, Any]
    execution_limits: dict[str, Any]

    @staticmethod
    def load(path: str) -> "Policy":
        data = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
        return Policy(
            allowed_write_roots=[_resolve_path(x) for x in (data.get("allowed_write_roots") or [])],
            allowed_read_roots=[_resolve_path(x) for x in (data.get("allowed_read_roots") or [])],
            denied_paths=[_resolve_path(x) for x in (data.get("denied_paths") or []) if _resolve_path(x) != "/"],
            command_allowlist=set(str(x) for x in (data.get("command_allowlist") or [])),
            command_denylist=set(str(x) for x in (data.get("command_denylist") or [])),
            destructive_command_controls=dict(data.get("destructive_command_controls") or {}),
            git_controls=dict(data.get("git_controls") or {}),
            network_controls=dict(data.get("network_controls") or {}),
            execution_limits=dict(data.get("execution_limits") or {}),
        )

    def _limit(self, key: str, default: int) -> int:
        try:
            return int(self.execution_limits.get(key, default))
        except Exception:
            return default

    def max_runtime_seconds(self) -> int:
        return self._limit("max_runtime_seconds", 60)

    def max_output_chars(self) -> int:
        return self._limit("max_output_chars", 2500)

    def max_steps_per_plan(self) -> int:
        return self._limit("max_steps_per_plan", 3)

    def max_file_write_bytes(self) -> int:
        return self._limit("max_file_write_bytes", 750000)

    def max_completion_tokens(self) -> int:
        return self._limit("max_completion_tokens", 700)

    def max_memory_items(self) -> int:
        return self._limit("max_memory_items", 3)

    def max_memory_chars(self) -> int:
        return self._limit("max_memory_chars", 3000)

    def max_answer_chars(self) -> int:
        return self._limit("max_answer_chars", 2500)

    def max_answer_lines(self) -> int:
        return self._limit("max_answer_lines", 8)

    def max_stdout_lines(self) -> int:
        return self._limit("max_stdout_lines", 20)

    def max_stderr_lines(self) -> int:
        return self._limit("max_stderr_lines", 20)

    def max_context_files(self) -> int:
        return self._limit("max_context_files", 120)

    def max_context_chars(self) -> int:
        return self._limit("max_context_chars", 10000)

    def include_git_status(self) -> bool:
        return bool(self.execution_limits.get("include_git_status", True))

    def execution_mode(self) -> str:
        mode = str(self.execution_limits.get("execution_mode", "single_step")).strip().lower()
        return mode if mode in {"single_step", "continue_until_done"} else "single_step"

    def max_actions_per_run(self) -> int:
        return max(1, self._limit("max_actions_per_run", 1))

    def llm_model(self) -> str:
        model = str(self.execution_limits.get("llm_model", "")).strip()
        return model or "gpt-4o-mini"

    def destructive_deny_patterns(self) -> list[str]:
        return [str(x) for x in (self.destructive_command_controls.get("deny_patterns") or [])]

    def rm_rules(self) -> dict[str, Any]:
        v = self.destructive_command_controls.get("rm_rules")
        return dict(v) if isinstance(v, dict) else {}

    def allow_outbound_http(self) -> bool:
        return bool(self.network_controls.get("allow_outbound_http", False))

    def allow_domains(self) -> list[str]:
        return [str(x).lower() for x in (self.network_controls.get("allow_domains") or [])]
