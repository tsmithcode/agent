from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set


def _expand_resolve(p: str) -> str:
    return str(Path(os.path.expanduser(p)).resolve())


@dataclass(frozen=True)
class Policy:
    allowed_write_roots: List[str]
    allowed_read_roots: List[str]
    denied_paths: List[str]

    command_allowlist: Set[str]
    command_denylist: Set[str]

    destructive_command_controls: Dict[str, Any]
    git_controls: Dict[str, Any]
    network_controls: Dict[str, Any]
    routing_controls: Dict[str, Any]
    execution_limits: Dict[str, Any]

    @staticmethod
    def load(path: str) -> "Policy":
        p = Path(path).expanduser().resolve()
        data: Dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))

        allowed_write_roots = [_expand_resolve(x) for x in (data.get("allowed_write_roots") or [])]
        allowed_read_roots = [_expand_resolve(x) for x in (data.get("allowed_read_roots") or [])]
        denied_paths = [_expand_resolve(x) for x in (data.get("denied_paths") or [])]
        denied_paths = [x for x in denied_paths if x != "/"]

        command_allowlist = set(data.get("command_allowlist") or [])
        command_denylist = set(data.get("command_denylist") or [])

        destructive_command_controls = dict(data.get("destructive_command_controls") or {})
        git_controls = dict(data.get("git_controls") or {})
        network_controls = dict(data.get("network_controls") or {})
        routing_controls = dict(data.get("routing_controls") or {})
        execution_limits = dict(data.get("execution_limits") or {})

        return Policy(
            allowed_write_roots=allowed_write_roots,
            allowed_read_roots=allowed_read_roots,
            denied_paths=denied_paths,
            command_allowlist=command_allowlist,
            command_denylist=command_denylist,
            destructive_command_controls=destructive_command_controls,
            git_controls=git_controls,
            network_controls=network_controls,
            routing_controls=routing_controls,
            execution_limits=execution_limits,
        )

    def max_runtime_seconds(self) -> int:
        return int(self.execution_limits.get("max_runtime_seconds", 60))

    def max_output_chars(self) -> int:
        return int(self.execution_limits.get("max_output_chars", 2500))

    def max_steps_per_plan(self) -> int:
        return int(self.execution_limits.get("max_steps_per_plan", 5))

    def max_file_write_bytes(self) -> int:
        return int(self.execution_limits.get("max_file_write_bytes", 750000))

    def max_completion_tokens(self) -> int:
        return int(self.execution_limits.get("max_completion_tokens", 700))

    def max_memory_items(self) -> int:
        return int(self.execution_limits.get("max_memory_items", 3))

    def max_memory_chars(self) -> int:
        return int(self.execution_limits.get("max_memory_chars", 3000))

    def max_answer_chars(self) -> int:
        return int(self.execution_limits.get("max_answer_chars", 2500))

    def max_answer_lines(self) -> int:
        return int(self.execution_limits.get("max_answer_lines", 6))

    def max_stdout_lines(self) -> int:
        return int(self.execution_limits.get("max_stdout_lines", 20))

    def max_stderr_lines(self) -> int:
        return int(self.execution_limits.get("max_stderr_lines", 20))

    def max_context_files(self) -> int:
        return int(self.execution_limits.get("max_context_files", 200))

    def max_context_file_chars(self) -> int:
        return int(self.execution_limits.get("max_context_file_chars", 1200))

    def max_context_chars(self) -> int:
        return int(self.execution_limits.get("max_context_chars", 12000))

    def include_git_status(self) -> bool:
        return bool(self.execution_limits.get("include_git_status", True))

    def execution_mode(self) -> str:
        mode = str(self.execution_limits.get("execution_mode", "single_step")).strip()
        return mode if mode in {"single_step", "continue_until_done"} else "single_step"

    def max_actions_per_run(self) -> int:
        return int(self.execution_limits.get("max_actions_per_run", 1))

    def llm_model(self) -> str:
        model = str(self.execution_limits.get("llm_model", "")).strip()
        return model or "gpt-4o-mini"

    def destructive_deny_patterns(self) -> List[str]:
        return [str(x) for x in (self.destructive_command_controls.get("deny_patterns") or [])]

    def rm_rules(self) -> Dict[str, Any]:
        v = self.destructive_command_controls.get("rm_rules")
        if isinstance(v, dict):
            return v
        return {}

    def allow_outbound_http(self) -> bool:
        return bool(self.network_controls.get("allow_outbound_http", False))

    def allow_domains(self) -> List[str]:
        return list(self.network_controls.get("allow_domains") or [])

    def enable_deterministic_routing(self) -> bool:
        return bool(self.routing_controls.get("enable_deterministic_routing", True))

    def deterministic_confidence_threshold(self) -> float:
        v = self.routing_controls.get("deterministic_confidence_threshold", 0.86)
        try:
            f = float(v)
        except Exception:
            return 0.86
        return max(0.0, min(1.0, f))

    def allowed_deterministic_handlers(self) -> List[str]:
        return [str(x) for x in (self.routing_controls.get("allowed_handlers") or [])]

    def force_llm_patterns(self) -> List[str]:
        return [str(x) for x in (self.routing_controls.get("force_llm_patterns") or [])]
