"""
Anamnesis – Schema Detector Agent
===================================

Watches a DataHub dataset for schema changes and classifies them as:
  - BREAKING  : field removal, type narrowing, required field added
  - NON_BREAKING : new optional field, description change, tag update

Two entry points
----------------
detect_schema_break(dataset_urn, known_good_schema)
    Compare a dataset's live schema against a caller-supplied baseline dict
    of {field_name: type_string}.  Returns a structured result dict.

simulate_schema_break(dataset_urn)
    Demo helper: fetches the real schema, artificially removes two fields
    and changes a type, then calls detect_schema_break so the caller can
    see a realistic detection result without needing a live schema change.

detect(dataset_urn, auto_capture_baseline)
    Legacy entry point that stores baselines in the MemoryStore.  Still
    wired to /api/detect when no known_good_schema is supplied.

Usage:
    from backend.agents.detector import SchemaDetector
    detector = SchemaDetector()

    # Real detection against a supplied baseline
    result = detector.detect_schema_break(
        dataset_urn="urn:li:dataset:(...)",
        known_good_schema={"order_id": "NUMBER", "order_date": "DATE", ...}
    )

    # Demo simulation (no live change needed)
    result = detector.simulate_schema_break(
        dataset_urn="urn:li:dataset:(...)"
    )
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.core.datahub_client import DataHubAdapter
from backend.core.memory_store import MemoryRecord, MemoryStore, MemoryType, get_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal data structures (kept for legacy detect() path)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------

# Field-type pairs that constitute a BREAKING change (old → new).
_BREAKING_TYPE_CHANGES: set[tuple[str, str]] = {
    ("STRING", "NUMBER"),
    ("STRING", "BOOLEAN"),
    ("NUMBER", "BOOLEAN"),
    ("BOOLEAN", "NUMBER"),
    ("ARRAY", "STRING"),
    ("ARRAY", "NUMBER"),
}


def _classify_severity(
    missing: List[str],
    type_changes: List[Dict[str, Any]],
    new_fields: List[str],
) -> str:
    """
    Return a severity label based on the detected differences.

    critical  – one or more fields removed  (downstream consumers break)
    high      – a field type changed in a breaking way
    medium    – a field type changed in a non-breaking way, or new unexpected fields
    low       – only new optional fields added
    """
    if missing:
        return "critical"

    breaking_type_changes = [
        tc for tc in type_changes
        if (tc["was"].upper(), tc["now"].upper()) in _BREAKING_TYPE_CHANGES
    ]
    if breaking_type_changes:
        return "high"

    if type_changes:
        return "medium"

    if new_fields:
        return "low"

    return "low"


# ---------------------------------------------------------------------------
# Main agent class
# ---------------------------------------------------------------------------

class SchemaDetector:
    """
    Compares a dataset's current schema against a stored baseline and
    detects breaking vs non-breaking changes.
    """

    # kept for legacy _diff_schemas path
    BREAKING_TYPE_CHANGES = _BREAKING_TYPE_CHANGES

    def __init__(
        self,
        datahub: Optional[DataHubAdapter] = None,
        store: Optional[MemoryStore] = None,
    ):
        self._dh = datahub or DataHubAdapter()
        self._store = store or get_store()

    # ── Public: detect_schema_break ───────────────────────────────────────────

    def detect_schema_break(
        self,
        dataset_urn: str,
        known_good_schema: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Compare the live DataHub schema for *dataset_urn* against
        *known_good_schema* (a dict of {field_name: type_string}).

        Returns
        -------
        {
            "has_break": bool,
            "dataset_urn": str,
            "missing_fields": [str, ...],
            "type_changes":   [{"field": str, "was": str, "now": str}, ...],
            "new_fields":     [str, ...],
            "severity":       "critical" | "high" | "medium" | "low",
            "current_schema": {field: type, ...},
            "checked_at":     float  (unix epoch)
        }
        """
        logger.info("detect_schema_break called for %s", dataset_urn)

        # 1. Fetch live schema from DataHub
        live_fields = self._dh.get_schema(dataset_urn)
        current_schema: Dict[str, str] = {
            f["fieldPath"]: f.get("type", "UNKNOWN")
            for f in live_fields
        }

        if not current_schema and not known_good_schema:
            return self._empty_result(dataset_urn, current_schema, note="No schema data available")

        # 2. Compute diff
        baseline_names = set(known_good_schema)
        current_names  = set(current_schema)

        missing_fields: List[str] = sorted(baseline_names - current_names)
        new_fields:     List[str] = sorted(current_names - baseline_names)

        type_changes: List[Dict[str, str]] = []
        for field in baseline_names & current_names:
            was = known_good_schema[field]
            now = current_schema[field]
            if was.upper() != now.upper():
                type_changes.append({"field": field, "was": was, "now": now})

        has_break = bool(missing_fields or type_changes)
        severity  = _classify_severity(missing_fields, type_changes, new_fields)

        logger.info(
            "detect_schema_break result for %s: has_break=%s, missing=%s, type_changes=%s, new=%s",
            dataset_urn, has_break, missing_fields, type_changes, new_fields,
        )

        return {
            "has_break":      has_break,
            "dataset_urn":    dataset_urn,
            "missing_fields": missing_fields,
            "type_changes":   type_changes,
            "new_fields":     new_fields,
            "severity":       severity,
            "current_schema": current_schema,
            "checked_at":     time.time(),
        }

    # ── Public: simulate_schema_break ─────────────────────────────────────────

    # Fallback schema used when DataHub is unreachable (keeps simulation
    # working in CI, offline demos, and unit tests).
    _FALLBACK_SCHEMA: Dict[str, str] = {
        "order_id":            "NUMBER",
        "order_date":          "DATE",
        "customer_id":         "NUMBER",
        "order_status":        "STRING",
        "order_total":         "NUMBER",
        "payment_method_code": "STRING",
    }

    def simulate_schema_break(self, dataset_urn: str) -> Dict[str, Any]:
        """
        Demo helper — fetches the real live schema, then artificially
        constructs a "known-good" baseline that includes two extra fields
        (simulating them having been dropped) and one type that has changed.

        This lets you demo the detector without needing an actual schema
        change in the upstream database.

        Works offline: if DataHub is unreachable, falls back to a built-in
        orders schema so the simulation always produces meaningful output.

        The simulation:
          - Pretends 'payment_method_code' and 'order_status' existed as
            STRING fields in the baseline (they still exist in the live schema
            but with potentially different DataHub type labels).
          - Pretends 'fulfillment_status' (a STRING) was present in the
            baseline — it does NOT exist in the live schema, so it surfaces
            as a missing (breaking) field.
          - Pretends 'order_total' was a STRING (it is actually NUMBER in
            the live schema), simulating a type-change break.
        """
        logger.info("simulate_schema_break called for %s", dataset_urn)

        # Fetch the live schema so the "known good" snapshot is realistic
        live_fields = self._dh.get_schema(dataset_urn)
        current_schema: Dict[str, str] = {
            f["fieldPath"]: f.get("type", "STRING")
            for f in live_fields
        }

        # Fall back to hardcoded schema when DataHub is unavailable so that
        # simulation is always meaningful (useful in CI, offline demos, tests).
        if not current_schema:
            logger.warning(
                "simulate_schema_break: live schema empty for %s "
                "– using built-in fallback schema",
                dataset_urn,
            )
            current_schema = dict(self._FALLBACK_SCHEMA)

        # Build a "known good" baseline from the live schema …
        known_good: Dict[str, str] = dict(current_schema)

        # … then mutate it to represent the "before" state:
        #   1. Add a field that no longer exists (field-removal simulation)
        known_good["fulfillment_status"] = "STRING"

        #   2. Add another dropped field for richer demo output
        known_good["estimated_delivery_days"] = "NUMBER"

        #   3. Change a type so order_total looks like it was STRING before
        if "order_total" in known_good:
            known_good["order_total"] = "STRING"   # live value is NUMBER

        result = self.detect_schema_break(dataset_urn, known_good)
        # Tag result so callers know it's simulated
        result["simulated"] = True
        return result

    # ── Legacy: baseline-based detect() ──────────────────────────────────────

    def _baseline_key(self, dataset_urn: str) -> str:
        return f"schema_baseline:{dataset_urn}"

    def capture_baseline(self, dataset_urn: str) -> List[Dict[str, Any]]:
        """Fetch the current schema and persist it as the baseline in memory."""
        fields = self._dh.get_schema(dataset_urn)
        record = MemoryRecord(
            type=MemoryType.DECISION,
            entity_urn=dataset_urn,
            title="Schema baseline captured",
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

    def _diff_schemas(
        self,
        baseline: List[Dict[str, Any]],
        current: List[Dict[str, Any]],
    ) -> SchemaDiff:
        baseline_map = {f["fieldPath"]: f for f in baseline}
        current_map  = {f["fieldPath"]: f for f in current}

        baseline_paths = set(baseline_map)
        current_paths  = set(current_map)

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

    def detect(
        self,
        dataset_urn: str,
        auto_capture_baseline: bool = True,
    ) -> Dict[str, Any]:
        """
        Legacy baseline-based detection.

        Detect schema changes for ``dataset_urn`` against a previously
        captured in-memory baseline.

        Returns a dict with keys:
          has_changes, is_breaking, diff, similar_past_incidents, memory_id
        """
        baseline = self._get_baseline(dataset_urn)
        current  = self._dh.get_schema(dataset_urn)

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
                "added_fields":   [f.field_path for f in diff.added],
                "type_changes":   diff.type_changes,
            },
            tags=["schema", "detected"] + (["breaking"] if diff.is_breaking else []),
            severity=severity,
        )
        mem = self._store.add(record)

        return {
            "has_changes": True,
            "is_breaking": diff.is_breaking,
            "diff": {
                "removed":      [f.field_path for f in diff.removed],
                "added":        [f.field_path for f in diff.added],
                "type_changes": diff.type_changes,
                "summary":      diff.summary(),
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
                        "id":         h.id,
                        "title":      h.title,
                        "summary":    h.summary,
                        "severity":   h.severity,
                        "resolved":   h.resolved,
                        "created_at": h.created_at,
                    })
        return similar[:5]

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _empty_result(
        dataset_urn: str,
        current_schema: Dict[str, str],
        note: str = "",
    ) -> Dict[str, Any]:
        return {
            "has_break":      False,
            "dataset_urn":    dataset_urn,
            "missing_fields": [],
            "type_changes":   [],
            "new_fields":     [],
            "severity":       "low",
            "current_schema": current_schema,
            "checked_at":     time.time(),
            "note":           note,
        }
