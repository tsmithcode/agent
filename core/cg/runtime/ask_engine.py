from __future__ import annotations

import os
import subprocess
import time
import uuid
from pathlib import Path

from ..data.env import get_openai_api_key, load_project_dotenv
from ..data.memory import LongTermMemory
from ..data.paths import Paths
from ..safety.policy import Policy
from .common import finish_event, limits_summary, save_memory
from .llm import LLM
from cg_utils import cap_chars, truncate_for_display


def _collect_paths(root: Path, *, max_files: int) -> list[str]:
    out: list[str] = []
    skip_dirs = {".git", "venv", "__pycache__", ".logs", ".pytest_cache"}
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            p = Path(cur) / name
            try:
                out.append(str(p.relative_to(root)))
            except Exception:
                out.append(str(p))
            if len(out) >= max_files:
                return out
    return out


def _collect_runtime_snapshot(paths: Paths, policy: Policy) -> str:
    max_files = max(20, policy.max_context_files())
    max_chars = max(2000, policy.max_context_chars())
    blocks = ["Project file sample:\n" + "\n".join(f"- {x}" for x in _collect_paths(paths.agent_root, max_files=max_files))]
    if policy.include_git_status():
        try:
            proc = subprocess.run(["git", "status", "--short"], cwd=str(paths.agent_root), capture_output=True, text=True, timeout=2)
            status = (proc.stdout or proc.stderr or "").strip() or "(clean or unavailable)"
            blocks.append("Git status:\n" + cap_chars(status, 1200))
        except Exception:
            pass
    return cap_chars("\n\n".join(blocks), max_chars)


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
    session_id: str,
    llm_cls=LLM,
    memory_cls=LongTermMemory,
) -> None:
    started = time.perf_counter()
    run_id = str(uuid.uuid4())[:8]
    print_session_boundary(console, command="ask", run_id=run_id, phase="start")
    load_project_dotenv()

    paths = Paths.resolve()
    policy = Policy.load(str((paths.home / "agent" / "config" / "policy.json").resolve()))
    api_key = get_openai_api_key()
    llm_used = False

    def _finish(outcome: str, *, error_type: str = "", error_message: str = "") -> None:
        finish_event(
            paths=paths,
            started=started,
            session_id=session_id,
            command="ask",
            route_mode="llm",
            outcome=outcome,
            llm_used=llm_used,
            executed_steps=0,
            error_type=error_type,
            error_message=error_message,
        )
        print_session_boundary(console, command="ask", run_id=run_id, phase="end")

    if not api_key:
        print_status_line(console, "OPENAI_API_KEY not set. Ask requires LLM in this core profile.", tone="warning")
        _finish("llm_required")
        return

    memory = memory_cls(chroma_dir=str(paths.chroma_dir), collection_name="cg_memory", openai_api_key=api_key)
    retrieved = memory.query(question, n_results=max(1, min(3, policy.max_memory_items())))
    retrieved_text = "\n\n".join(f"- {x.text}" for x in retrieved) or "(none)"
    runtime_snapshot = _collect_runtime_snapshot(paths, policy)
    context_text = (
        "Agent profile:\n"
        "- Product: CAD Guardian Core\n"
        "- Mode: LLM-only ask/run\n"
        f"- Runtime: {limits_summary(policy)}\n"
        "\nRuntime snapshot:\n"
        f"{runtime_snapshot}\n\n"
        "Memory context:\n"
        f"{cap_chars(retrieved_text, policy.max_memory_chars())}"
    )

    if context:
        print_section(console, title="Ask Context", body=cap_chars(context_text, 12000, full_output=full_output))

    print_kv_table(
        console,
        title="CAD Guardian Insight",
        rows=[
            ("Question", question),
            ("Memory", f"retrieved={len(retrieved)}"),
            ("Runtime", limits_summary(policy)),
        ],
    )

    llm = llm_cls(api_key=api_key)
    try:
        llm_used = True
        reply = llm.ask(
            question,
            context_text,
            model=policy.llm_model(),
            max_completion_tokens=max(64, policy.max_completion_tokens()),
            task_mode="ask",
        )
    except Exception as e:
        print_runtime_error(console, "LLM Error", e, "Check OPENAI_API_KEY, network, and model policy settings.")
        _finish("llm_error", error_type=type(e).__name__, error_message=str(e))
        return

    answer, truncated = truncate_for_display(
        reply.answer,
        max_chars=policy.max_answer_chars(),
        max_lines=policy.max_answer_lines(),
        full_output=full_output,
    )
    print_section(console, title="Insight Answer", body=answer)
    if truncated:
        print_status_line(console, "Insight answer truncated. Use --full to expand.", tone="warning")

    print_answer_path(console, "llm", "Ask is LLM-only in the core profile.")
    save_memory(memory, user_text=question, assistant_text=reply.answer, mode="ask")
    _finish("success")
