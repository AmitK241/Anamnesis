"""
Anamnesis Memory Store
======================

Stores every schema fix, incident resolution, and agent decision as a
structured memory record that future agents can query and reason over.

Memory records are persisted to DataHub as custom metadata (structured
properties) attached to the relevant Dataset, DataJob, or Dashboard entity.

Memory Types:
  - SCHEMA_FIX   : a schema break was detected and resolved
  - INCIDENT      : a data quality / pipeline incident was triaged
  - DECISION      : an agent made a significant routing / remediation decision
  - LESSON        : a generalised pattern extracted from one or more incidents
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemoryType(str, Enum):
    SCHEMA_FIX = "SCHEMA_FIX"
    INCIDENT = "INCIDENT"
    DECISION = "DECISION"
    LESSON = "LESSON"


@dataclass
class MemoryRecord:
    """A single unit of institutional memory."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: MemoryType = MemoryType.INCIDENT
    entity_urn: str = ""          # DataHub URN of the entity this is about
    title: str = ""
    summary: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    severity: str = "LOW"         # LOW | MEDIUM | HIGH | CRITICAL
    resolved: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    agent_id: str = "anamnesis"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryRecord":
        data = dict(data)
        data["type"] = MemoryType(data.get("type", "INCIDENT"))
        return cls(**data)


class MemoryStore:
    """
    Abstraction over the persistence layer.

    In early development (Day 1-2) this stores memories in a local JSON
    file at ``ANAMNESIS_MEMORY_PATH`` (default: ``./memory_store.json``).
    Once DataHub is running we upgrade to DataHub custom properties.
    """

    def __init__(self, path: Optional[str] = None):
        self._path = path or os.getenv(
            "ANAMNESIS_MEMORY_PATH",
            os.path.join(os.path.dirname(__file__), "..", "..", "memory_store.json"),
        )
        self._records: Dict[str, MemoryRecord] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                self._records = {
                    k: MemoryRecord.from_dict(v) for k, v in raw.items()
                }
                logger.info("Loaded %d memory records from %s", len(self._records), self._path)
            except Exception as exc:
                logger.error("Failed to load memory store: %s", exc)

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(
                    {k: v.to_dict() for k, v in self._records.items()},
                    fh,
                    indent=2,
                    default=str,
                )
        except Exception as exc:
            logger.error("Failed to save memory store: %s", exc)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add(self, record: MemoryRecord) -> MemoryRecord:
        """Persist a new memory record; returns the record with its assigned ID."""
        self._records[record.id] = record
        self._save()
        logger.info("Memory stored: [%s] %s (%s)", record.type.value, record.title, record.id)
        return record

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        return self._records.get(record_id)

    def update(self, record_id: str, **kwargs: Any) -> Optional[MemoryRecord]:
        rec = self._records.get(record_id)
        if not rec:
            return None
        for k, v in kwargs.items():
            if hasattr(rec, k):
                setattr(rec, k, v)
        rec.updated_at = time.time()
        self._save()
        return rec

    def delete(self, record_id: str) -> bool:
        if record_id in self._records:
            del self._records[record_id]
            self._save()
            return True
        return False

    # ── query ─────────────────────────────────────────────────────────────────

    def query(
        self,
        *,
        entity_urn: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        tags: Optional[List[str]] = None,
        resolved: Optional[bool] = None,
        limit: int = 50,
    ) -> List[MemoryRecord]:
        """Return memory records matching the given filters, most recent first."""
        results = list(self._records.values())

        if entity_urn is not None:
            results = [r for r in results if r.entity_urn == entity_urn]
        if memory_type is not None:
            results = [r for r in results if r.type == memory_type]
        if tags:
            results = [r for r in results if any(t in r.tags for t in tags)]
        if resolved is not None:
            results = [r for r in results if r.resolved == resolved]

        results.sort(key=lambda r: r.created_at, reverse=True)
        return results[:limit]

    def search(self, keyword: str, limit: int = 20) -> List[MemoryRecord]:
        """Full-text search across title + summary + detail."""
        kw = keyword.lower()
        results = []
        for rec in self._records.values():
            haystack = f"{rec.title} {rec.summary} {json.dumps(rec.detail)}".lower()
            if kw in haystack:
                results.append(rec)
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results[:limit]

    def all(self) -> List[MemoryRecord]:
        return sorted(self._records.values(), key=lambda r: r.created_at, reverse=True)

    @property
    def count(self) -> int:
        return len(self._records)


# Module-level singleton (lazy init)
_store: Optional[MemoryStore] = None


def get_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store
