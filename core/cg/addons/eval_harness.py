from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .paths import Paths


@dataclass(frozen=True)
class EvalCase:
    name: str
    passed: bool
    detail: str


def run_core_eval(
    *,
    select_do_mode: Callable[[str], str],
    decide_route: Callable[[str], object],
    file_count_probe: Callable[[str, Path], tuple[bool, str]],
    expected_handlers: set[str],
) -> list[EvalCase]:
    cases: list[EvalCase] = []

    do_ask = select_do_mode("What is in my workspace?") == "ask"
    cases.append(EvalCase("do-routes-question-to-ask", do_ask, "question should map to ask"))

    do_run = select_do_mode("show files") == "run"
    cases.append(EvalCase("do-routes-action-to-run", do_run, "action should map to run"))

    route = decide_route("show files")
    route_ok = getattr(route, "mode", "") == "deterministic" and str(getattr(route, "handler_id", "")) in expected_handlers
    cases.append(EvalCase("router-deterministic-show-files", route_ok, f"mode={getattr(route, 'mode', '')} handler={getattr(route, 'handler_id', '')}"))

    probe_ok, answer = file_count_probe("how many metrics-summary.csv files?", Paths.resolve().workspace)
    count_ok = probe_ok and "Found" in answer
    cases.append(EvalCase("ask-deterministic-file-count", count_ok, "count probe should return deterministic answer"))

    return cases


def save_eval_report(paths: Paths, *, suite: str, cases: list[EvalCase]) -> Path:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = (paths.workspace / "reports" / "evals" / run_id).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for c in cases if c.passed)
    payload = {
        "suite": suite,
        "generated_ts_utc": datetime.now(timezone.utc).isoformat(),
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "pass_rate": round((passed / len(cases)) * 100.0, 1) if cases else 0.0,
        "cases": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in cases],
    }
    out = out_dir / "eval-summary.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out
