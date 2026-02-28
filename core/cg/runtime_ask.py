from __future__ import annotations

import os
import subprocess
import time
import uuid
from pathlib import Path

from .env import get_openai_api_key, load_project_dotenv
from .llm import LLM
from .memory import LongTermMemory
from .paths import Paths
from .policy import Policy
from .runtime_common import finish_event, limits_summary, save_memory
from cg_utils import cap_chars, truncate_for_display


def _collect_paths(root: Path, *, max_files: int) -> list[str]:
    out: list[str] = []
    skip_dirs = {".git", "venv", "__pycache__", ".logs", ".pytest_cache"}
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            p = (Path(cur) / name)
            try:
                out.append(str(p.relative_to(root)))
            except Exception:
                out.append(str(p))
            if len(out) >= max_files:
                return out
    return out


def ask_workspace_file_count(question: str, workspace: Path) -> tuple[bool, str]:
    q = (question or "").strip().lower()
    m = __import__("re").search(r"\bhow many\s+([a-z0-9._-]+)\s+files?\b", q)
    if not m:
        return False, ""
    target = m.group(1).strip()
    if not target:
        return False, ""

    count = 0
    samples: list[str] = []
    for cur, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".pytest_cache"}]
        for name in files:
            name_l = name.lower()
            matched = name_l == target
            if target.startswith("."):
                matched = name_l.endswith(target)
            if matched:
                count += 1
                if len(samples) < 5:
                    p = (Path(cur) / name)
                    samples.append(str(p.relative_to(workspace)))

    sample_line = f"\nSample paths:\n- " + "\n- ".join(samples) if samples else ""
    answer = f'Found {count} file(s) matching "{target}" in workspace: {workspace}{sample_line}'
    return True, answer


def _collect_runtime_snapshot(paths: Paths, policy: Policy) -> str:
    max_files = max(20, policy.max_context_files())
    max_chars = max(1500, policy.max_context_chars())
    tree_lines = _collect_paths(paths.agent_root, max_files=max_files)
    blocks = ["Project file sample:\n" + "\n".join(f"- {p}" for p in tree_lines)]

    if policy.include_git_status():
        try:
            proc = subprocess.run(["git", "status", "--short"], cwd=str(paths.agent_root), capture_output=True, text=True, timeout=2)
            status = (proc.stdout or proc.stderr or "").strip() or "(clean or unavailable)"
            blocks.append("Git status:\n" + cap_chars(status, 1200))
        except Exception:
            pass

    return cap_chars("\n\n".join(blocks), max_chars)


def _ask_capability_brief(policy: Policy) -> str:
    allow = ", ".join(sorted(policy.command_allowlist))
    deny = ", ".join(sorted(policy.command_denylist))
    allow_domains = ", ".join(policy.allow_domains())
    return (
        "Agent profile:\n"
        "- Product: CAD Guardian CLI\n"
        "- Modes: run, ask, doctor, inspect, dev\n"
        f"- Execution mode: {policy.execution_mode()} (max_actions_per_run={policy.max_actions_per_run()})\n"
        f"- Limits: max_completion_tokens={policy.max_completion_tokens()}, max_steps_per_plan={policy.max_steps_per_plan()}, max_runtime_seconds={policy.max_runtime_seconds()}\n"
        f"- Allowed commands: {allow}\n"
        f"- Denied commands: {deny}\n"
        f"- Allowed HTTP domains: {allow_domains}\n"
        "- Source of truth for architecture: README.md, docs/README.md, core/cg/*.py, config/policy.json\n"
    )


def ask_once(
    *,
    question: str,
    full_output: bool,
    context: bool,
    console,
    print_session_boundary,
    print_kv_table,
    print_section,
    print_answer_path,
    print_status_line,
    print_runtime_error,
    get_openai_api_key_fn=get_openai_api_key,
    session_id: str,
    llm_cls=LLM,
    memory_cls=LongTermMemory,
) -> None:
    started = time.perf_counter()
    run_id = str(uuid.uuid4())[:8]
    print_session_boundary(console, command="ask", run_id=run_id, phase="start")
    load_project_dotenv()

    paths = Paths.resolve()
    policy_path = (paths.home / "agent" / "config" / "policy.json").resolve()
    policy = Policy.load(str(policy_path))

    max_response_chars = policy.max_answer_chars()
    max_summary_lines = policy.max_answer_lines()
    max_completion_tokens = max(64, policy.max_completion_tokens())
    llm_used = False
    ask_route_mode = "llm"
    ask_handler_id = ""

    def _finish(outcome: str, *, error_type: str = "", error_message: str = "") -> None:
        finish_event(
            paths=paths,
            started=started,
            session_id=session_id,
            command="ask",
            route_mode=ask_route_mode,
            handler_id=ask_handler_id,
            outcome=outcome,
            llm_used=llm_used,
            actionable_steps=0,
            executed_steps=0,
            error_type=error_type,
            error_message=error_message,
        )
        print_session_boundary(console, command="ask", run_id=run_id, phase="end")

    matched_count, count_answer = ask_workspace_file_count(question, paths.workspace)
    if matched_count:
        ask_route_mode = "deterministic"
        ask_handler_id = "count_files_by_name"
        print_kv_table(console, title="CAD Guardian Insight", rows=[("Question", question), ("Context", "deterministic_workspace_scan=true"), ("Runtime", limits_summary(policy))])
        answer_display, answer_truncated = truncate_for_display(count_answer, max_chars=max_response_chars, max_lines=max_summary_lines, full_output=full_output)
        print_section(console, title="Insight Answer", body=answer_display)
        print_answer_path(console, "command", "deterministic ask handler scanned workspace files")
        if answer_truncated:
            print_status_line(console, "Insight answer truncated. Use --full for full response.", tone="warning")
        save_memory(memory_cls(chroma_dir=str(paths.chroma_dir), collection_name="cg_openclaw_memory", openai_api_key=get_openai_api_key_fn()), user_text=question, assistant_text=count_answer, mode="ask", kind_override="task_result", extra_metadata={"route_mode": "deterministic", "handler_id": "count_files_by_name"})
        _finish("success")
        return

    api_key = get_openai_api_key_fn()
    if not api_key:
        print_status_line(console, "OPENAI_API_KEY not set. LLM call skipped.", tone="warning")
        _finish("llm_required")
        return

    memory = memory_cls(chroma_dir=str(paths.chroma_dir), collection_name="cg_openclaw_memory", openai_api_key=api_key)
    ask_memory_items = min(2, max(1, policy.max_memory_items()))
    ask_memory_chars = min(800, policy.max_memory_chars())
    retrieved_items = memory.query(question, n_results=ask_memory_items)
    retrieved_count = len(retrieved_items)
    retrieved_text_full = "\n\n".join([f"- {it.text} (kind={str((it.metadata or {}).get('kind', ''))})" for it in retrieved_items]) or "(none)"
    retrieved_text = cap_chars(retrieved_text_full, ask_memory_chars)
    snapshot_text = _collect_runtime_snapshot(paths, policy)
    capability_text = _ask_capability_brief(policy)
    context_text = f"{capability_text}\nRuntime/source snapshot (primary):\n{snapshot_text}\n\nMemory context (secondary):\n{retrieved_text}"

    if context:
        preview = cap_chars(context_text, 12000, full_output=full_output)
        print_section(console, title="Ask Context", body=preview)

    print_kv_table(console, title="CAD Guardian Insight", rows=[("Question", question), ("Context", f"memory_items={retrieved_count} (secondary) | context_chars={len(context_text)}"), ("Runtime", limits_summary(policy))])

    llm = llm_cls(api_key=api_key)
    try:
        llm_used = True
        reply = llm.ask(question, context_text, model=policy.llm_model(), max_completion_tokens=max_completion_tokens, task_mode="ask")
    except Exception as e:
        print_runtime_error(console, "LLM Error", e, "Check OPENAI_API_KEY, internet/DNS, and policy allow_domains settings.")
        _finish("llm_error", error_type=type(e).__name__, error_message=str(e))
        return

    answer_display, answer_truncated = truncate_for_display(reply.answer, max_chars=max_response_chars, max_lines=max_summary_lines, full_output=full_output)
    print_section(console, title="Insight Answer", body=answer_display)
    print_answer_path(console, "llm", "ask mode is read-only and uses LLM over runtime snapshot context")
    if answer_truncated:
        print_status_line(console, "Insight answer truncated. Use --full for full response.", tone="warning")

    save_memory(memory, user_text=question, assistant_text=reply.answer, mode="ask")
    _finish("success")
