from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class MemoryItem:
    id: str
    text: str
    metadata: dict


class LongTermMemory:
    """Lightweight JSONL memory store.

    This keeps the same public API as the previous memory class while removing
    heavy vector DB dependencies for the core profile.
    """

    def __init__(
        self,
        chroma_dir: str,
        collection_name: str,
        openai_api_key: Optional[str],
        *,
        max_doc_chars: int = 4000,
        max_items: int = 5000,
        prefer_kinds: Optional[list[str]] = None,
    ):
        self.max_doc_chars = max_doc_chars
        self.max_items = max_items
        self.prefer_kinds = prefer_kinds or [
            "user_profile",
            "preferences",
            "workflow_pattern",
            "task_result",
            "interaction",
        ]
        self.embedder = None
        self._file = Path(chroma_dir).resolve() / f"{collection_name}.jsonl"
        self._file.parent.mkdir(parents=True, exist_ok=True)
        if not self._file.exists():
            self._file.write_text("", encoding="utf-8")

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _cap(self, text: str) -> str:
        if len(text) <= self.max_doc_chars:
            return text
        return text[: self.max_doc_chars] + "...(truncated)"

    def _read_all(self) -> list[dict]:
        rows: list[dict] = []
        for line in self._file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
            except Exception:
                continue
        return rows

    def _write_all(self, rows: list[dict]) -> None:
        payload = "\n".join(json.dumps(r, ensure_ascii=True) for r in rows)
        self._file.write_text(payload + ("\n" if payload else ""), encoding="utf-8")

    def add(self, mem_id: str, text: str, metadata: dict) -> None:
        text_capped = self._cap(text)
        content_hash = hashlib.sha256(text_capped.encode("utf-8", errors="ignore")).hexdigest()
        meta = dict(metadata or {})
        meta.setdefault("ts_utc", self._now_iso())
        meta.setdefault("content_hash", content_hash)

        rows = self._read_all()
        if any((r.get("metadata") or {}).get("content_hash") == content_hash for r in rows):
            return

        rows.append({"id": mem_id, "text": text_capped, "metadata": meta})
        if len(rows) > self.max_items:
            rows = sorted(rows, key=lambda r: str((r.get("metadata") or {}).get("ts_utc") or ""), reverse=True)[: self.max_items]
        self._write_all(rows)

    def query(
        self,
        text: str,
        n_results: int = 5,
        *,
        kinds: Optional[list[str]] = None,
        allow_interaction_fallback: bool = True,
    ) -> list[MemoryItem]:
        rows = self._read_all()
        if not rows:
            return []

        wanted = set(kinds or self.prefer_kinds)
        query_tokens = {t for t in text.lower().split() if len(t) >= 3}

        scored: list[tuple[int, str, dict, str]] = []
        for r in rows:
            meta = dict(r.get("metadata") or {})
            kind = str(meta.get("kind") or "")
            if wanted and kind and kind not in wanted and not allow_interaction_fallback:
                continue
            body = str(r.get("text") or "")
            tokens = set(body.lower().split())
            score = len(query_tokens.intersection(tokens))
            ts = str(meta.get("ts_utc") or "")
            scored.append((score, ts, meta, body))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        out: list[MemoryItem] = []
        for idx, (_score, _ts, meta, body) in enumerate(scored[: max(1, n_results)]):
            out.append(MemoryItem(id=str(idx), text=body, metadata=meta))
        return out
