import json
import tempfile
import unittest
from pathlib import Path

from cg.safety.policy import Policy
from cg.routing.router import decide_route


def _policy_dict(workspace: Path) -> dict:
    return {
        "allowed_write_roots": [str(workspace)],
        "allowed_read_roots": [str(workspace)],
        "denied_paths": ["/etc", "/proc", "/sys", "/dev", "/run", "/root"],
        "command_allowlist": ["echo", "find", "python3", "git"],
        "command_denylist": [],
        "destructive_command_controls": {},
        "git_controls": {},
        "network_controls": {"allow_outbound_http": True, "allow_domains": ["api.openai.com"]},
        "routing_controls": {
            "enable_deterministic_routing": True,
            "deterministic_confidence_threshold": 0.86,
            "allowed_handlers": [],
            "force_llm_patterns": [],
        },
        "execution_limits": {"max_runtime_seconds": 3},
    }


class RouterTests(unittest.TestCase):
    def _policy(self, mutate: dict | None = None) -> Policy:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            d = _policy_dict(workspace)
            if mutate:
                d.update(mutate)
            p = workspace / "policy.json"
            p.write_text(json.dumps(d), encoding="utf-8")
            return Policy.load(str(p))

    def test_route_workspace_when_obvious(self) -> None:
        policy = self._policy()
        decision = decide_route("show workspace files", policy)
        self.assertEqual(decision.mode, "deterministic")
        self.assertEqual(decision.handler_id, "inspect_workspace")

    def test_route_show_files_when_obvious(self) -> None:
        policy = self._policy()
        decision = decide_route("show files", policy)
        self.assertEqual(decision.mode, "deterministic")
        self.assertEqual(decision.handler_id, "inspect_workspace")

    def test_route_snapshot_when_obvious(self) -> None:
        policy = self._policy()
        decision = decide_route("run snapshot tests", policy)
        self.assertEqual(decision.mode, "deterministic")
        self.assertEqual(decision.handler_id, "dev_snaps")

    def test_route_falls_back_to_llm_for_design_query(self) -> None:
        policy = self._policy()
        decision = decide_route("design a release strategy", policy)
        self.assertEqual(decision.mode, "llm")
        self.assertIsNone(decision.handler_id)

    def test_force_llm_pattern_overrides_deterministic(self) -> None:
        policy = self._policy(
            mutate={"routing_controls": {"enable_deterministic_routing": True, "force_llm_patterns": ["workspace"]}}
        )
        decision = decide_route("show workspace files", policy)
        self.assertEqual(decision.mode, "llm")
        self.assertIsNone(decision.handler_id)


if __name__ == "__main__":
    unittest.main()
