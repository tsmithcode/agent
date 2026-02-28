import json
import tempfile
import unittest
from pathlib import Path

from cg.safety.executor import Executor, PolicyViolation
from cg.safety.policy import Policy


def _policy_dict(workspace: Path) -> dict:
    return {
        "allowed_write_roots": [str(workspace)],
        "allowed_read_roots": [str(workspace)],
        "denied_paths": ["/etc", "/proc", "/sys", "/dev", "/run", "/root"],
        "command_allowlist": ["echo", "rm", "curl", "git"],
        "command_denylist": [],
        "destructive_command_controls": {
            "deny_patterns": [],
            "rm_rules": {
                "deny_recursive": False,
                "allow_recursive_only_under": [str(workspace / "safe")],
            },
        },
        "git_controls": {"deny_push": True, "deny_force": True, "deny_remote_add": True},
        "network_controls": {
            "allow_outbound_http": True,
            "allow_domains": ["api.openai.com"],
        },
        "execution_limits": {
            "max_runtime_seconds": 3,
            "max_output_chars": 2000,
            "max_file_write_bytes": 16,
            "max_steps_per_plan": 3,
        },
    }


class PolicyEnforcementTests(unittest.TestCase):
    def _executor(self, workspace: Path, mutate: dict | None = None) -> Executor:
        policy_json = _policy_dict(workspace)
        if mutate:
            policy_json.update(mutate)
        policy_path = workspace / "policy.json"
        policy_path.write_text(json.dumps(policy_json), encoding="utf-8")
        policy = Policy.load(str(policy_path))
        return Executor(policy=policy, workspace=workspace)

    def test_command_denylist_overrides_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            executor = self._executor(workspace, mutate={"command_denylist": ["echo"]})
            with self.assertRaises(PolicyViolation) as ctx:
                executor.run("echo hello")
            self.assertEqual(ctx.exception.rule, "command_denylist")

    def test_recursive_rm_outside_allowed_root_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / "safe").mkdir()
            executor = self._executor(workspace)
            with self.assertRaises(PolicyViolation):
                executor.run("rm -rf ../outside")

    def test_write_size_limit_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            executor = self._executor(workspace)
            with self.assertRaises(PolicyViolation):
                executor.write_file("big.txt", "0123456789" * 4)

    def test_network_domain_restriction_for_curl(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            executor = self._executor(workspace)
            with self.assertRaises(PolicyViolation):
                executor.run("curl https://example.com")


if __name__ == "__main__":
    unittest.main()
