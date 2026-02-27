import tempfile
import unittest
from pathlib import Path

from cg.telemetry import append_event, read_events, summarize_events


class TelemetryTests(unittest.TestCase):
    def test_jsonl_append_read_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            logs = Path(td)
            append_event(
                logs,
                {
                    "command": "run",
                    "route_mode": "deterministic",
                    "outcome": "success",
                    "duration_ms": 100,
                    "llm_used": False,
                },
            )
            append_event(
                logs,
                {
                    "command": "ask",
                    "route_mode": "llm",
                    "outcome": "success",
                    "duration_ms": 200,
                    "llm_used": True,
                },
            )

            events = read_events(logs)
            self.assertEqual(len(events), 2)
            self.assertIn("event_id", events[0])
            self.assertIn("schema_version", events[0])
            summary = summarize_events(events)
            self.assertEqual(summary["events_total"], 2)
            self.assertEqual(summary["by_command"]["ask"], 1)
            self.assertEqual(summary["by_command"]["run"], 1)
            self.assertEqual(summary["by_route_mode"]["deterministic"], 1)
            self.assertEqual(summary["by_route_mode"]["llm"], 1)
            self.assertEqual(summary["by_command_outcome"]["ask"]["success"], 1)
            self.assertEqual(summary["by_command_outcome"]["run"]["success"], 1)


if __name__ == "__main__":
    unittest.main()
