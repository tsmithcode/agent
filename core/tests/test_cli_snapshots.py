import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from cg import main as main_mod


SNAP_DIR = Path(__file__).resolve().parent / "snapshots"


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\s+$", "", text, flags=re.MULTILINE)
    return text.strip() + "\n"


def _snapshot_text(render_fn) -> str:
    original_console = main_mod.console
    try:
        rec = Console(record=True, width=100, force_terminal=False, color_system=None)
        main_mod.console = rec
        render_fn()
        return _normalize(rec.export_text())
    finally:
        main_mod.console = original_console


class CliSnapshotTests(unittest.TestCase):
    maxDiff = None

    def _assert_snapshot(self, name: str, actual: str) -> None:
        expected_path = SNAP_DIR / f"{name}.txt"
        expected = expected_path.read_text(encoding="utf-8")
        self.assertEqual(_normalize(expected), _normalize(actual), f"Snapshot mismatch: {name}")

    def test_command_required_notice_snapshot(self) -> None:
        text = _snapshot_text(
            lambda: main_mod._print_cli_notice(
                title="Command Required",
                level="warning",
                message="Select a command to continue.",
                usage_line='cg run "<prompt>" [--full-output]  (or: cg ask "<question>")',
                help_line="Run cg --help to see available commands and options.",
                example_line='cg run "summarize workspace"',
            )
        )
        self._assert_snapshot("command_required", text)

    def test_unknown_command_notice_snapshot(self) -> None:
        text = _snapshot_text(
            lambda: main_mod._print_cli_notice(
                title="Unknown Command: bogus",
                level="error",
                message="No such command 'bogus'.",
                help_line="Run cg --help to see available commands and options.",
                example_line='cg run "summarize workspace"',
            )
        )
        self._assert_snapshot("unknown_command", text)

    def test_llm_error_snapshot(self) -> None:
        text = _snapshot_text(
            lambda: main_mod._print_runtime_error(
                "LLM Error",
                Exception("Connection error."),
                "Check OPENAI_API_KEY, internet/DNS, and policy allow_domains settings.",
            )
        )
        self._assert_snapshot("llm_error", text)

    def test_ask_static_question_snapshot(self) -> None:
        question = "What can you tell me about yourself and your policies?"

        class FakeMemory:
            def __init__(self, *args, **kwargs):
                pass

            def query(self, *args, **kwargs):
                return []

            def add(self, *args, **kwargs):
                return None

        class FakeLLM:
            def __init__(self, api_key: str):
                self.api_key = api_key

            def ask(self, *args, **kwargs):
                return type(
                    "Reply",
                    (),
                    {
                        "answer": (
                            "I am CAD Guardian. I support run, ask, doctor, and snapshot-tests. "
                            "My behavior is controlled by policy.json limits and allow/deny rules."
                        ),
                        "plan": [],
                    },
                )()

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "snapshot-test-key"}, clear=False),
            patch.object(main_mod, "LongTermMemory", FakeMemory),
            patch.object(main_mod, "LLM", FakeLLM),
            patch.object(main_mod.Policy, "include_git_status", lambda self: False),
        ):
            text = _snapshot_text(lambda: main_mod._ask_once(question))

        self._assert_snapshot("ask_static_question", text)


if __name__ == "__main__":
    unittest.main()
