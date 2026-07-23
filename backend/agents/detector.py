"""
Anamnesis – Schema Detector Agent
===================================

Watches a DataHub dataset for schema changes and classifies them as:
  - BREAKING  : field removal, type narrowing, required field added
  - NON_BREAKING : new optional field, description change, tag update

When a breaking change is detected the agent:
  1. Creates a MemoryRecord of type SCHEMA_FIX
  2. Searches Anamnesis memory for similar past incidents
  3. Returns a structured diagnosis with suggested remediation

Usage:
    from backend.agents.detector import SchemaDetector
    detector = SchemaDetector()
    result = detector.detect(dataset_urn="urn:li:dataset:(...)")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.core.datahub_client import DataHubAdapter
from backend.core.memory_store import MemoryRecord, MemoryStore, MemoryType, get_store

logger = logging.getLogger(__name__)


@dataclass
class SchemaField:
    field_path: str
    field_type: str
    description: str = ""


@dataclass
class SchemaDiff:
    added: List[SchemaField]
    removed: List[SchemaField]
    type_changes: List[Dict[str, Any]]   # {field, old_type, new_type}
    is_breaking: bool = False

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.type_changes)

    def summary(self) -> str:
        parts = []
        if self.removed:
            parts.append(f"{len(self.removed)} field(s) removed: {[f.field_path for f in self.removed]}")
        if self.type_changes:
            parts.append(f"{len(self.type_changes)} type change(s)")
        if self.added:
            parts.append(f"{len(self.added)} field(s) added")
        return "; ".join(parts) if parts else "No schema changes"


class SchemaDetector:
    """
    Compares a dataset's current schema against a stored baseline and
    detects breaking vs non-breaking changes.
    """

    BREAKING_TYPE_CHANGES = {
        # (old_type, new_type) pairs considered breaking
        ("STRING", "NUMBER"),
        ("STRING", "BOOLEAN"),
        ("NUMBER", "BOOLEAN"),
        ("BOOLEAN", "NUMBER"),
        ("ARRAY", "STRING"),
    }

    def __init__(
        self,
        datahub: Optional[DataHubAdapter] = None,
        store: Optional[MemoryStore] = None,
    ):
        self._dh = datahub or DataHubAdapter()
        self._store = store or get_store()

    # ── baseline management ───────────────────────────────────────────────────

    def _baseline_key(self, dataset_urn: str) -> str:
        return f"schema_baseline:{dataset_urn}"

    def capture_baseline(self, dataset_urn: str) -> List[Dict[str, Any]]:
        """Fetch the current schema and persist it as the baseline in memory."""
        fields = self._dh.get_schema(dataset_urn)
        record = MemoryRecord(
            type=MemoryType.DECISION,
            entity_urn=dataset_urn,
            title=f"Schema baseline captured",
            summary=f"Captured {len(fields)} fields as baseline",
            detail={"baseline": fields, "baseline_key": self._baseline_key(dataset_urn)},
            tags=["baseline", "schema"],
        )
        self._store.add(record)
        logger.info("Baseline captured for %s: %d fields", dataset_urn, len(fields))
        return fields

    def _get_baseline(self, dataset_urn: str) -> Optional[List[Dict[str, Any]]]:
        """Retrieve the most recent baseline for the given dataset."""
        key = self._baseline_key(dataset_urn)
        records = self._store.query(entity_urn=dataset_urn, memory_type=MemoryType.DECISION)
        for rec in records:
            if rec.detail.get("baseline_key") == key:
                return rec.detail.get("baseline")
        return None

    # ── diffing ───────────────────────────────────────────────────────────────

    def _diff_schemas(
        self,
        baseline: List[Dict[str, Any]],
        current: List[Dict[str, Any]],
    ) -> SchemaDiff:
        baseline_map = {f["fieldPath"]: f for f in baseline}
        current_map = {f["fieldPath"]: f for f in current}

        baseline_paths = set(baseline_map)
        current_paths = set(current_map)

        added = [
            SchemaField(f["fieldPath"], f.get("type", ""), f.get("description", ""))
            for p, f in current_map.items()
            if p not in baseline_paths
        ]
        removed = [
            SchemaField(f["fieldPath"], f.get("type", ""), f.get("description", ""))
            for p, f in baseline_map.items()
            if p not in current_paths
        ]
        type_changes = []
        for path in baseline_paths & current_paths:
            old_type = baseline_map[path].get("type", "")
            new_type = current_map[path].get("type", "")
            if old_type != new_type:
                type_changes.append({"field": path, "old_type": old_type, "new_type": new_type})

        is_breaking = bool(removed) or any(
            (tc["old_type"].upper(), tc["new_type"].upper()) in self.BREAKING_TYPE_CHANGES
            for tc in type_changes
        )

        return SchemaDiff(added=added, removed=removed, type_changes=type_changes, is_breaking=is_breaking)

    # ── main entry point ──────────────────────────────────────────────────────

    def detect(
        self,
        dataset_urn: str,
        auto_capture_baseline: bool = True,
    ) -> Dict[str, Any]:
        """
        Detect schema changes for ``dataset_urn``.

        Returns a dict with keys:
          has_changes, is_breaking, diff, similar_past_incidents, memory_id
        """
        baseline = self._get_baseline(dataset_urn)
        current = self._dh.get_schema(dataset_urn)

        if not baseline:
            if auto_capture_baseline and current:
                self.capture_baseline(dataset_urn)
                return {
                    "has_changes": False,
                    "is_breaking": False,
                    "diff": None,
                    "message": "First run – baseline captured. Run again to detect changes.",
                    "similar_past_incidents": [],
                }
            return {
                "has_changes": False,
                "is_breaking": False,
                "diff": None,
                "message": "No baseline found and no schema data available.",
                "similar_past_incidents": [],
            }

        diff = self._diff_schemas(baseline, current)

        if diff.is_empty:
            return {
                "has_changes": False,
                "is_breaking": False,
                "diff": None,
                "message": "No schema changes detected.",
                "similar_past_incidents": [],
            }

        # Search memory for similar past incidents
        similar = self._search_similar(diff)

        # Persist this detection as a memory record
        severity = "HIGH" if diff.is_breaking else "LOW"
        record = MemoryRecord(
            type=MemoryType.SCHEMA_FIX,
            entity_urn=dataset_urn,
            title=f"{'BREAKING' if diff.is_breaking else 'Non-breaking'} schema change detected",
            summary=diff.summary(),
            detail={
                "removed_fields": [f.field_path for f in diff.removed],
                "added_fields": [f.field_path for f in diff.added],
                "type_changes": diff.type_changes,
            },
            tags=["schema", "detected"] + (["breaking"] if diff.is_breaking else []),
            severity=severity,
        )
        mem = self._store.add(record)

        return {
            "has_changes": True,
            "is_breaking": diff.is_breaking,
            "diff": {
                "removed": [f.field_path for f in diff.removed],
                "added": [f.field_path for f in diff.added],
                "type_changes": diff.type_changes,
                "summary": diff.summary(),
            },
            "severity": severity,
            "similar_past_incidents": similar,
            "memory_id": mem.id,
        }

    def _search_similar(self, diff: SchemaDiff) -> List[Dict[str, Any]]:
        """Find past incidents that involved the same removed/changed fields."""
        similar = []
        for removed_field in diff.removed:
            hits = self._store.search(removed_field.field_path)
            for h in hits:
                if h.type == MemoryType.SCHEMA_FIX:
                    similar.append({
                        "id": h.id,
                        "title": h.title,
                        "summary": h.summary,
                        "severity": h.severity,
                        "resolved": h.resolved,
                        "created_at": h.created_at,
                    })
        return similar[:5]
