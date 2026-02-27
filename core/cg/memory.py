from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from chromadb import PersistentClient
from chromadb.utils import embedding_functions


@dataclass
class MemoryItem:
    id: str
    text: str
    metadata: dict


class LongTermMemory:
    """
    Persistent memory store backed by ChromaDB on disk.

    - Primary mode: semantic retrieval via embeddings (OpenAI) when API key is available.
    - Fallback mode: recent-memory retrieval (timestamp-sorted) when embeddings are unavailable.

    Stored at: ~/host_ai/memory/chroma
    """

    def __init__(
        self,
        chroma_dir: str,
        collection_name: str,
        openai_api_key: Optional[str],
        *,
        max_doc_chars: int = 4000,
        max_items: int = 5000,
        prefer_kinds: Optional[List[str]] = None,
    ):
        self.client = PersistentClient(path=chroma_dir)
        self.max_doc_chars = max_doc_chars
        self.max_items = max_items
        self.prefer_kinds = prefer_kinds or ["user_profile", "preferences", "task_result", "interaction"]

        # If you have an API key, use OpenAI embeddings; otherwise fall back to recent-only mode.
        self.embedder = None
        if openai_api_key:
            self.embedder = embedding_functions.OpenAIEmbeddingFunction(
                api_key=openai_api_key,
                model_name="text-embedding-3-small",
            )

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedder,
        )

    def _now_utc_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _cap(self, s: str) -> str:
        if len(s) <= self.max_doc_chars:
            return s
        return s[: self.max_doc_chars] + "...(truncated)"

    def _hash_text(self, s: str) -> str:
        return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()

    def _safe_get(self, d: Dict[str, Any], key: str, default: Any = None) -> Any:
        v = d.get(key, default)
        return default if v is None else v

    def _dedupe_exists(self, content_hash: str) -> bool:
        # Attempt a metadata filter query by hash (fast if supported).
        try:
            res = self.collection.get(where={"content_hash": content_hash}, limit=1)
            return bool(res and res.get("ids") and len(res["ids"]) > 0)
        except Exception:
            return False

    def _prune_if_needed(self) -> None:
        # Keep the collection bounded to avoid unbounded disk/snapshot growth.
        try:
            count = self.collection.count()
            if count <= self.max_items:
                return

            # Fetch a batch of items and delete the oldest by ts_utc if present.
            # Chroma doesn't guarantee server-side sort; we do a client-side sort on a pulled window.
            over = count - self.max_items
            pull = min(max(over * 2, 200), 2000)

            got = self.collection.get(include=["metadatas"], limit=pull)
            ids = got.get("ids", []) or []
            metas = got.get("metadatas", []) or []

            def ts(m: dict) -> str:
                return str(m.get("ts_utc") or "")

            pairs = list(zip(ids, metas))
            pairs.sort(key=lambda p: ts(p[1]) or "")

            to_delete = [pid for pid, _ in pairs[:over]]
            if to_delete:
                self.collection.delete(ids=to_delete)
        except Exception:
            # Never let pruning break the agent.
            return

    def add(self, mem_id: str, text: str, metadata: dict) -> None:
        text_capped = self._cap(text)
        meta = dict(metadata or {})

        # Ensure timestamp for fallback sorting
        meta.setdefault("ts_utc", self._now_utc_iso())

        # Add hash for dedupe
        content_hash = self._hash_text(text_capped)
        meta.setdefault("content_hash", content_hash)

        # Skip if already stored (prevents duplicate “Create README…” spam)
        if self._dedupe_exists(content_hash):
            return

        self.collection.add(
            ids=[mem_id],
            documents=[text_capped],
            metadatas=[meta],
        )

        # Bound DB growth
        self._prune_if_needed()

    def query(
        self,
        text: str,
        n_results: int = 5,
        *,
        kinds: Optional[List[str]] = None,
        allow_interaction_fallback: bool = True,
    ) -> List[MemoryItem]:
        kinds = kinds or self.prefer_kinds

        # 1) Embedding retrieval (preferred)
        if self.embedder is not None:
            # Two-pass: prefer high-signal kinds first, then fill with interactions.
            items: List[MemoryItem] = []

            for k in kinds:
                try:
                    res = self.collection.query(
                        query_texts=[text],
                        n_results=n_results,
                        where={"kind": k},
                    )
                except Exception:
                    continue

                ids = (res.get("ids") or [[]])[0]
                docs = (res.get("documents") or [[]])[0]
                metas = (res.get("metadatas") or [[]])[0]

                for i in range(len(ids)):
                    if len(items) >= n_results:
                        break
                    items.append(MemoryItem(id=ids[i], text=docs[i], metadata=metas[i]))

                if len(items) >= n_results:
                    break

            return items

        # 2) Fallback: recent-memory retrieval without embeddings
        if not allow_interaction_fallback:
            return []

        try:
            got = self.collection.get(include=["documents", "metadatas"], limit=max(n_results * 10, 50))
            ids = got.get("ids", []) or []
            docs = got.get("documents", []) or []
            metas = got.get("metadatas", []) or []

            # Filter to requested kinds if present
            triples = []
            for i in range(len(ids)):
                m = metas[i] or {}
                kind = m.get("kind")
                if kind and kind not in kinds:
                    continue
                triples.append((ids[i], docs[i], m))

            def ts(m: dict) -> str:
                return str(m.get("ts_utc") or "")

            triples.sort(key=lambda t: ts(t[2]), reverse=True)
            triples = triples[:n_results]

            return [MemoryItem(id=a, text=b, metadata=c) for a, b, c in triples]
        except Exception:
            return []