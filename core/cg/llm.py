from __future__ import annotations
import json
import re
from dataclasses import dataclass
from typing import List, Optional

from openai import OpenAI


@dataclass
class PlanStep:
    type: str  # "cmd" | "write" | "note"
    value: str
    path: Optional[str] = None


@dataclass
class AgentReply:
    answer: str
    plan: List[PlanStep]


SYSTEM_PROMPT = """You are CAD Guardian (supervised, cost-minimal workstation agent).

PRIMARY OBJECTIVE:
Produce minimal, deterministic output suitable for automated execution.

STRICT OUTPUT CONTRACT:
Return ONE valid JSON object only.
No markdown. No commentary. No prose outside JSON.

Schema:
{
  "answer": "string",
  "plan": [
    {"type":"cmd","value":"..."},
    {"type":"write","path":"relative/path","value":"..."},
    {"type":"note","value":"..."}
  ]
}

BEHAVIOR RULES:

1) Supervised Execution Model
- Always produce a full minimal plan.
- Do not self-iterate.

2) Cost-Minimal Output
- Keep "answer" under 6 lines.
- Do not restate user prompt.
- Do not include reasoning.
- Do not output large file contents.
- Prefer concise diffs over full files.
- Prefer single commands over multiple small commands.

3) Path Contract
- All write paths MUST be strictly relative to workspace root.
- NEVER include "workspace/" in the path.
- Examples:
  - "README.md"
  - "docs/plan.md"

4) Safety
- No sudo.
- No system directories.
- No modification outside workspace.
- No destructive recursive operations unless explicitly requested.

5) Efficiency
- Prefer write steps over echo commands.
- Avoid unnecessary shell chaining.
- Batch related actions into a single minimal command when safe.

If unsure, return a note step instead of guessing.
"""

ASK_SYSTEM_PROMPT = """You are CAD Guardian in read-only analysis mode.

PRIMARY OBJECTIVE:
Answer questions about the CURRENT project state using provided context.

STRICT OUTPUT CONTRACT:
Return ONE valid JSON object only.
No markdown. No commentary. No prose outside JSON.

Schema:
{
  "answer": "string",
  "plan": []
}

BEHAVIOR RULES:
- Read-only mode: do not propose execution steps.
- Use the supplied source/workspace snapshot as ground truth.
- Be explicit when context is missing.
- Keep answer concise and practical.
"""

class LLM:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def _safe_parse(self, raw: str) -> dict:
        raw = raw.strip()

        # Attempt strict parse first
        try:
            return json.loads(raw)
        except Exception:
            pass

        # Fallback: extract first JSON object block
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass

        # Absolute fallback: return empty safe structure
        return {"answer": "(Invalid JSON from model.)", "plan": []}

    def ask(
        self,
        user_text: str,
        retrieved_memory: str,
        *,
        max_completion_tokens: int = 700,
        task_mode: str = "run",
    ) -> AgentReply:
        prompt = f"""User request:
{user_text}

Relevant long-term memory:
{retrieved_memory}
"""
        system_prompt = ASK_SYSTEM_PROMPT if task_mode == "ask" else SYSTEM_PROMPT

        resp = self.client.chat.completions.create(
            model="gpt-4o-mini",
            max_completion_tokens=max_completion_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )

        raw = resp.choices[0].message.content or ""
        obj = self._safe_parse(raw)

        answer = str(obj.get("answer", "")).strip()
        steps_raw = obj.get("plan", []) or []

        steps: List[PlanStep] = []
        for s in steps_raw:
            steps.append(
                PlanStep(
                    type=s.get("type"),
                    value=s.get("value", ""),
                    path=s.get("path"),
                )
            )

        return AgentReply(answer=answer, plan=steps)
