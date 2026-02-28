from __future__ import annotations

import sys
from typing import Callable

import typer

from ..safety.capability_manifest import validate_manifest
from ..data.paths import Paths
from ..safety.policy import Policy


_manifest_validated = False


def enforce_runtime_manifest(*, app, print_section, print_cli_notice, console) -> None:
    global _manifest_validated
    if _manifest_validated:
        return
    paths = Paths.resolve()
    policy = Policy.load(str((paths.home / "agent" / "config" / "policy.json").resolve()))
    result = validate_manifest(paths=paths, policy=policy, app=app)
    if result.warnings:
        print_section(console, title="Capability Warnings", body="\n".join(f"- {w}" for w in result.warnings))
    if not result.ok:
        print_cli_notice(
            console,
            title="Capability Manifest Error",
            level="error",
            message="Runtime capability checks failed.",
            help_line="Fix manifest/profile/command mismatches before continuing.",
            example_line="cg doctor --verbose",
        )
        print_section(console, title="Manifest Errors", body="\n".join(f"- {e}" for e in result.errors))
        raise SystemExit(2)
    _manifest_validated = True


def status_recommendations(summary: dict[str, object]) -> list[str]:
    recs: list[str] = []
    total = int(summary.get("events_total", 0) or 0)
    by_outcome = summary.get("by_outcome") or {}
    success = int(by_outcome.get("success", 0) or 0)
    errors = int(by_outcome.get("error", 0) or 0)
    policy_violations = int(by_outcome.get("policy_violation", 0) or 0)
    no_actionable = int(by_outcome.get("no_actionable", 0) or 0)
    llm_rate = float(summary.get("llm_used_rate", 0.0) or 0.0)

    if total == 0:
        return [
            "No telemetry yet. Start with: cg guide --mode starter",
            'Then run: cg do "show files" and cg ask "what can you do?"',
        ]
    if success / max(1, total) < 0.6:
        recs.append("Success rate is low. Run cg doctor and resolve warnings first.")
    if errors > 0:
        recs.append("Errors detected. Use --full on failing commands to capture full diagnostics.")
    if policy_violations > 0:
        recs.append("Policy violations found. Review cg policy show and policy allow/deny settings.")
    if no_actionable > 0:
        recs.append('Several no-actionable runs. Use direct verbs: "list", "show", "count", "create".')
    if llm_rate > 0.8:
        recs.append("LLM usage is high. Use deterministic commands for routine inspections to reduce cost.")
    if llm_rate < 0.2:
        recs.append("LLM usage is very low. Use ask mode for deeper read-only analysis when needed.")
    if not recs:
        recs.append("Health looks strong. Next: cg dev metrics --format json --limit 2000.")
    return recs


def select_do_mode(request: str) -> str:
    q = (request or "").strip().lower()
    if not q:
        return "ask"
    ask_leads = (
        "what",
        "why",
        "how",
        "who",
        "when",
        "where",
        "which",
        "can you",
        "could you",
        "explain",
        "summarize",
        "tell me",
    )
    if q.endswith("?") or q.startswith(ask_leads):
        return "ask"
    return "run"


def interactive_start_menu(*, is_tty: bool, print_section, console, guide_fn: Callable[[], None], ask_fn: Callable[[str], None], workspace_fn: Callable[[], None]) -> None:
    if not is_tty:
        return
    print_section(console, title="Quick Start Menu", body="1) Guided start\n2) Ask a question\n3) Show workspace files\n4) Exit")
    choice = typer.prompt("Choose 1-4", default="1").strip()
    if choice == "1":
        guide_fn()
    elif choice == "2":
        q = typer.prompt("What do you want to ask?")
        ask_fn(q)
    elif choice == "3":
        workspace_fn()
