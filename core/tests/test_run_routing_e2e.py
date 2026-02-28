import os
import unittest
from unittest.mock import patch

from cg import main as main_mod
from cg.routing.router import RouteDecision


class _FakeMemory:
    def __init__(self, *args, **kwargs):
        pass

    def query(self, *args, **kwargs):
        return []

    def add(self, *args, **kwargs):
        return None


class RunRoutingE2ETests(unittest.TestCase):
    def test_deterministic_route_uses_command_path_and_skips_llm(self) -> None:
        with (
            patch.object(main_mod, "LongTermMemory", _FakeMemory),
            patch.object(
                main_mod,
                "decide_route",
                return_value=RouteDecision("deterministic", "inspect_workspace", 1.0, "workspace phrase"),
            ),
            patch.object(main_mod, "_execute_deterministic_handler", return_value=(True, "ok")) as exec_handler,
            patch.object(main_mod, "LLM") as llm_cls,
        ):
            main_mod._run_once("show workspace files")
            exec_handler.assert_called_once()
            llm_cls.assert_not_called()

    def test_llm_route_executes_actionable_step(self) -> None:
        class FakeLLM:
            def __init__(self, api_key: str):
                self.api_key = api_key

            def ask(self, *args, **kwargs):
                step = type("Step", (), {"type": "cmd", "value": "echo ok"})()
                return type("Reply", (), {"answer": "Will run command", "plan": [step]})()

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "snapshot-test-key"}, clear=False),
            patch.object(main_mod, "LongTermMemory", _FakeMemory),
            patch.object(main_mod, "LLM", FakeLLM),
            patch.object(main_mod, "decide_route", return_value=RouteDecision("llm", None, 0.2, "below threshold")),
            patch.object(main_mod, "_execute_step", return_value=True) as execute_step,
        ):
            main_mod._run_once("run a quick check command")
            execute_step.assert_called_once()

    def test_apply_style_llm_plan_requires_confirmation(self) -> None:
        class FakeLLM:
            def __init__(self, api_key: str):
                self.api_key = api_key

            def ask(self, *args, **kwargs):
                step = type("Step", (), {"type": "write", "path": "a.txt", "value": "x"})()
                return type("Reply", (), {"answer": "Applying rename plan", "plan": [step]})()

        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "snapshot-test-key"}, clear=False),
            patch.object(main_mod, "LongTermMemory", _FakeMemory),
            patch.object(main_mod, "LLM", FakeLLM),
            patch.object(main_mod, "decide_route", return_value=RouteDecision("llm", None, 0.2, "below threshold")),
            patch.object(main_mod, "_execute_step", return_value=True) as execute_step,
        ):
            main_mod._run_once("rename files in batch")
            execute_step.assert_not_called()


if __name__ == "__main__":
    unittest.main()
