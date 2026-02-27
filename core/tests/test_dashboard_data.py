import json
import tempfile
import unittest
from pathlib import Path

from cg.dashboard_data import (
    load_event_overview,
    load_policy_overview,
    load_reports_overview,
    load_workspace_overview,
)
from cg.telemetry import append_event


class DashboardDataTests(unittest.TestCase):
    def test_event_workspace_policy_reports_overview(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logs = root / "logs"
            ws = root / "workspace"
            cfg = root / "config"
            ws.mkdir(parents=True, exist_ok=True)
            cfg.mkdir(parents=True, exist_ok=True)
            (ws / "a.py").write_text("print('x')", encoding="utf-8")
            (ws / "b.txt").write_text("hello", encoding="utf-8")
            (ws / "reports" / "ui-snapshots" / "20260101-000000").mkdir(parents=True, exist_ok=True)
            (ws / "reports" / "metrics" / "20260101-000001").mkdir(parents=True, exist_ok=True)

            policy = {
                "execution_limits": {"max_completion_tokens": 700},
                "routing_controls": {"enable_deterministic_routing": True},
                "network_controls": {"allow_outbound_http": True},
                "command_allowlist": ["echo"],
                "command_denylist": ["sudo"],
                "denied_paths": ["/etc"],
            }
            (cfg / "policy.json").write_text(json.dumps(policy), encoding="utf-8")

            append_event(
                logs,
                {
                    "command": "run",
                    "route_mode": "deterministic",
                    "outcome": "success",
                    "duration_ms": 5,
                    "llm_used": False,
                },
            )
            append_event(
                logs,
                {
                    "command": "ask",
                    "route_mode": "llm",
                    "outcome": "success",
                    "duration_ms": 7,
                    "llm_used": True,
                },
            )

            ev = load_event_overview(logs, limit=100)
            self.assertEqual(ev["summary"]["events_total"], 2)
            self.assertEqual(ev["route_distribution"]["deterministic"], 1)
            self.assertEqual(ev["route_distribution"]["llm"], 1)

            wsov = load_workspace_overview(ws)
            self.assertGreaterEqual(wsov["files_total"], 2)

            pov = load_policy_overview(cfg / "policy.json")
            self.assertEqual(pov["command_denylist_count"], 1)

            rov = load_reports_overview(ws)
            self.assertEqual(rov["ui_snapshot_runs_total"], 1)
            self.assertEqual(rov["metrics_runs_total"], 1)


if __name__ == "__main__":
    unittest.main()
