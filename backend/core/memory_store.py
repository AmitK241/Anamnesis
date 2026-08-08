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
        if "created_at" in data:
            data["created_at"] = float(data["created_at"])
        if "updated_at" in data:
            data["updated_at"] = float(data["updated_at"])
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
        self._last_dh_sync: float = 0.0
        self._load()

    # ── persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        # On Render, ensure we read fresh from DataHub (the true source of truth)
        # instead of relying on the per-worker ephemeral local file cache.
        if os.environ.get("RENDER"):
            now = time.time()
            # 10 second TTL to avoid spamming DataHub on burst requests
            if now - self._last_dh_sync > 10.0:
                self._last_dh_sync = now
                self._sync_from_datahub()
            return

        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                content = fh.read().strip()
            if not content:
                logger.debug("Memory store file is empty – starting fresh: %s", self._path)
                return
            raw = json.loads(content)
            self._records = {
                k: MemoryRecord.from_dict(v) for k, v in raw.items()
            }
            logger.info("Loaded %d memory records from %s", len(self._records), self._path)
        except Exception as exc:
            logger.error("Failed to load memory store: %s", exc)

    def _sync_from_datahub(self) -> None:
        """Dynamically fetch memories from DataHub and overwrite the local in-memory cache."""
        try:
            from backend.core.datahub_client import DataHubAdapter
            dh = DataHubAdapter()
            memories = dh.scroll_incident_memories()
            
            new_records = {}
            for m in memories:
                incident_id = m.get('incident_id')
                if not incident_id:
                    continue
                dataset_urn = m.get('dataset_urn', '')
                root_cause = m.get('root_cause', '')
                summary = m.get('resolution_code_diff', '')
                
                table_name = dataset_urn.split('.')[-1]
                if table_name.endswith(',PROD)'):
                    table_name = table_name.replace(',PROD)', '')

                detail = {
                    'root_cause': root_cause,
                    'suggested_fix': summary,
                    'downstream_impact': m.get('downstream_impact', []),
                    'embedding_vector': m.get('embedding_vector', []),
                    'time_saved_estimate': m.get('time_saved_estimate', 0)
                }
                if 'timestamp' in m:
                    detail['timestamp'] = m['timestamp']

                record = MemoryRecord(
                    id=incident_id,
                    type=MemoryType.INCIDENT,
                    entity_urn=dataset_urn,
                    title=f"Schema Break: {table_name}",
                    summary=summary[:100] + '...' if summary else '',
                    detail=detail,
                    tags=[],
                    severity='high',
                    agent_id='anamnesis'
                )
                if 'timestamp' in m and m['timestamp']:
                    record.created_at = float(m['timestamp'] / 1000.0)
                    
                new_records[incident_id] = record
            
            if new_records:
                # Merge into existing records to avoid dropping newly added ones that DataHub 
                # hasn't indexed yet, but prefer DataHub's version for existing ones.
                self._records.update(new_records)
                logger.info("Synced %d memories fresh from DataHub (Render mode)", len(new_records))
        except Exception as exc:
            logger.error("Failed to sync MemoryStore from DataHub on Render: %s", exc)

    def _save(self) -> None:
        if os.environ.get("RENDER"):
            # On Render, we rely on DataHub dynamically. Writing to the ephemeral disk 
            # across multiple workers is unnecessary and prone to race conditions.
            return

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
        self._load()  # Always read fresh from disk in case external processes modified it
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
        self._load()
        kw = keyword.lower()
        results = []
        for rec in self._records.values():
            haystack = f"{rec.title} {rec.summary} {json.dumps(rec.detail)}".lower()
            if kw in haystack:
                results.append(rec)
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results[:limit]

    def all(self) -> List[MemoryRecord]:
        self._load()
        return sorted(self._records.values(), key=lambda r: r.created_at, reverse=True)

    @property
    def count(self) -> int:
        self._load()
        return len(self._records)


# Module-level singleton (lazy init)
_store: Optional[MemoryStore] = None


def get_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store
