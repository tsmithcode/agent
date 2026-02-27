from __future__ import annotations
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .policy import Policy


@dataclass
class ExecResult:
    ok: bool
    command: str
    exit_code: int
    stdout: str
    stderr: str


class PolicyViolation(Exception):
    def __init__(self, message: str, *, rule: str = ""):
        super().__init__(message)
        self.rule = (rule or "").strip()


def _violation(message: str, *, rule: str) -> PolicyViolation:
    return PolicyViolation(message, rule=rule)


class Executor:
    def __init__(self, policy: Policy, workspace: Path):
        self.policy = policy
        self.workspace = workspace.resolve()

    def _is_denied_path(self, p: Path) -> bool:
        p = p.resolve()
        for d in self.policy.denied_paths:
            try:
                if p.is_relative_to(Path(d).expanduser().resolve()):
                    return True
            except Exception:
                # py<3.9 compatibility not needed, but keep safe.
                if str(p).startswith(str(Path(d).expanduser().resolve())):
                    return True
        return False

    def _is_allowed_write(self, p: Path) -> bool:
        p = p.resolve()
        for root in self.policy.allowed_write_roots:
            r = Path(root).expanduser().resolve()
            try:
                if p.is_relative_to(r):
                    return True
            except Exception:
                if str(p).startswith(str(r)):
                    return True
        return False

    def _is_allowed_read(self, p: Path) -> bool:
        p = p.resolve()
        if not self.policy.allowed_read_roots:
            return True
        for root in self.policy.allowed_read_roots:
            r = Path(root).expanduser().resolve()
            try:
                if p.is_relative_to(r):
                    return True
            except Exception:
                if str(p).startswith(str(r)):
                    return True
        return False

    def _enforce_write_size_limit(self, content: str) -> None:
        size = len(content.encode("utf-8"))
        if size > self.policy.max_file_write_bytes():
            raise _violation(
                f"Write exceeds max_file_write_bytes: {size} > {self.policy.max_file_write_bytes()}",
                rule="execution_limits.max_file_write_bytes",
            )

    def _enforce_destructive_patterns(self, command: str) -> None:
        deny_patterns = self.policy.destructive_deny_patterns()
        cmd_norm = " ".join(command.strip().split())
        for pat in deny_patterns:
            if cmd_norm == " ".join(str(pat).strip().split()):
                raise _violation(
                    f"Command matches denied destructive pattern: {pat}",
                    rule="destructive_command_controls.deny_patterns",
                )

    def _resolve_cli_path(self, path_arg: str, cwd: Path) -> Path:
        p = Path(path_arg).expanduser()
        if not p.is_absolute():
            p = (cwd / p)
        return p.resolve()

    def _enforce_rm_rules(self, parts: list[str], cwd: Path) -> None:
        if not parts or parts[0] != "rm":
            return

        rm_rules = self.policy.rm_rules()
        deny_recursive = bool(rm_rules.get("deny_recursive", False))
        allow_recursive_roots = [Path(p).expanduser().resolve() for p in (rm_rules.get("allow_recursive_only_under") or [])]

        has_recursive = any(flag in parts for flag in ("-r", "-rf", "-fr", "--recursive"))
        if has_recursive and deny_recursive:
            raise _violation(
                "Recursive rm is denied by policy.",
                rule="destructive_command_controls.rm_rules.deny_recursive",
            )

        if has_recursive and allow_recursive_roots:
            targets: list[Path] = []
            for arg in parts[1:]:
                if arg.startswith("-"):
                    continue
                target = self._resolve_cli_path(arg, cwd)
                targets.append(target)
            for target in targets:
                allowed = False
                for root in allow_recursive_roots:
                    try:
                        if target.is_relative_to(root):
                            allowed = True
                            break
                    except Exception:
                        if str(target).startswith(str(root)):
                            allowed = True
                            break
                if not allowed:
                    raise _violation(
                        f"Recursive rm target outside allowed roots: {target}",
                        rule="destructive_command_controls.rm_rules.allow_recursive_only_under",
                    )

    def _enforce_git_controls(self, parts: list[str]) -> None:
        if not parts or parts[0] != "git":
            return

        deny_force = bool(self.policy.git_controls.get("deny_force", False))
        deny_push = bool(self.policy.git_controls.get("deny_push", False))
        deny_remote_add = bool(self.policy.git_controls.get("deny_remote_add", False))
        subcmd = parts[1] if len(parts) > 1 else ""

        if deny_push and subcmd == "push":
            raise _violation("git push is denied by policy.", rule="git_controls.deny_push")
        if deny_remote_add and subcmd == "remote" and len(parts) > 2 and parts[2] == "add":
            raise _violation("git remote add is denied by policy.", rule="git_controls.deny_remote_add")
        if deny_force and any(p == "--force" or p.startswith("-f") for p in parts[1:]):
            raise _violation("Forced git operations are denied by policy.", rule="git_controls.deny_force")

    def _enforce_network_controls(self, parts: list[str]) -> None:
        if not parts:
            return
        exe = parts[0]
        if exe not in {"curl", "wget"}:
            return

        if not self.policy.allow_outbound_http():
            raise _violation("Outbound HTTP is denied by policy.", rule="network_controls.allow_outbound_http")

        allowed = set(self.policy.allow_domains())
        if not allowed:
            return

        urls = [p for p in parts[1:] if p.startswith("http://") or p.startswith("https://")]
        for u in urls:
            host = (urlparse(u).hostname or "").lower()
            if host not in allowed:
                raise _violation(f"Domain not allowed by policy: {host}", rule="network_controls.allow_domains")

    def write_file(self, rel_path: str, content: str) -> Path:
        target = (self.workspace / rel_path).resolve()

        if self._is_denied_path(target):
            raise _violation(f"Denied path: {target}", rule="denied_paths")

        if not self._is_allowed_write(target):
            raise _violation(f"Write outside allowed roots: {target}", rule="allowed_write_roots")

        self._enforce_write_size_limit(content)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def run(self, command: str, cwd: Optional[Path] = None, timeout_s: int = 60) -> ExecResult:
        parts = shlex.split(command)
        if not parts:
            raise _violation("Empty command", rule="command_allowlist")

        exe = parts[0]
        if exe not in self.policy.command_allowlist:
            raise _violation(f"Command not in allowlist: {exe}", rule="command_allowlist")
        if exe in self.policy.command_denylist:
            raise _violation(f"Command is explicitly denied by policy: {exe}", rule="command_denylist")

        run_cwd = (cwd or self.workspace).resolve()

        if self._is_denied_path(run_cwd):
            raise _violation(f"Denied cwd: {run_cwd}", rule="denied_paths")
        if not self._is_allowed_read(run_cwd):
            raise _violation(f"CWD outside allowed read roots: {run_cwd}", rule="allowed_read_roots")

        self._enforce_destructive_patterns(command)
        self._enforce_rm_rules(parts, run_cwd)
        self._enforce_git_controls(parts)
        self._enforce_network_controls(parts)

        proc = subprocess.run(
            parts,
            cwd=str(run_cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=os.environ.copy(),
        )

        return ExecResult(
            ok=(proc.returncode == 0),
            command=command,
            exit_code=proc.returncode,
            stdout=proc.stdout[-12000:],
            stderr=proc.stderr[-12000:],
        )
