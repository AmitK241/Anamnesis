"""
Anamnesis – Diagnoser Agent
==============================

Given a detected schema break, the Diagnoser:
  1. Traverses the DataHub lineage graph to find upstream sources and
     downstream consumers of the affected dataset.
  2. Builds a plain-English root-cause hypothesis from the break type and
     lineage context.
  3. Optionally searches Anamnesis memory for prior incidents on the same
     dataset / fields (used by the legacy diagnose() path).

Two entry points
----------------
diagnose(detection_result)
    New path — takes the structured dict from SchemaDetector.detect_schema_break()
    or simulate_schema_break() and returns a structured diagnosis.
    Does NOT write to memory (Memory-Writer's job).

diagnose(dataset_urn, diff, memory_id)   [legacy / keyword-arg path]
    Old path — accepts the legacy diff dict format from the baseline-based
    detector and persists an INCIDENT memory record (kept for backward compat).

Usage:
    from backend.agents.diagnoser import Diagnoser
    diagnoser = Diagnoser()

    # New path
    detection = detector.simulate_schema_break(urn)
    diagnosis = diagnoser.diagnose(detection)

    # Legacy path
    diagnosis = diagnoser.diagnose(dataset_urn=urn, diff=diff_dict)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.core.datahub_client import DataHubAdapter
from backend.core.memory_store import MemoryRecord, MemoryStore, MemoryType, get_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def _confidence(upstream: List, downstream: List, affected_fields: int) -> str:
    """
    Rate how confident we are in the diagnosis.

    high   – we have real lineage edges AND known affected fields
    medium – we have lineage OR known fields but not both
    low    – no lineage data at all
    """
    has_lineage = bool(upstream or downstream)
    has_fields  = affected_fields > 0

    if has_lineage and has_fields:
        return "high"
    if has_lineage or has_fields:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Root-cause narrative builder
# ---------------------------------------------------------------------------

def _build_root_cause(
    dataset_urn:    str,
    missing_fields: List[str],
    type_changes:   List[Dict[str, str]],
    new_fields:     List[str],
    upstream:       List[Dict[str, Any]],
    downstream:     List[Dict[str, Any]],
) -> str:
    parts: List[str] = []

    # Lead sentence
    if missing_fields and type_changes:
        parts.append(
            f"{len(missing_fields)} field(s) were removed and "
            f"{len(type_changes)} field type(s) changed."
        )
    elif missing_fields:
        fields_str = ", ".join(f"'{f}'" for f in missing_fields[:3])
        suffix = f" (and {len(missing_fields) - 3} more)" if len(missing_fields) > 3 else ""
        parts.append(f"Field(s) {fields_str}{suffix} no longer exist in the live schema.")
    elif type_changes:
        examples = ", ".join(
            f"'{tc['field']}' ({tc['was']} → {tc['now']})" for tc in type_changes[:2]
        )
        parts.append(f"Type change(s) detected: {examples}.")
    elif new_fields:
        parts.append(f"{len(new_fields)} unexpected new field(s) appeared.")
    else:
        parts.append("Schema differences were detected.")

    # Upstream hypothesis
    if upstream:
        up_names = [e.get("name") or e.get("urn", "").split(",")[-2] for e in upstream[:3]]
        parts.append(
            f"This dataset is fed by {len(upstream)} upstream source(s) "
            f"({', '.join(up_names)}), suggesting the break likely originated "
            "from an upstream schema change or pipeline modification."
        )
    else:
        parts.append(
            "No upstream lineage edges were found; the break may have been "
            "applied directly to this table's DDL."
        )

    # Downstream blast-radius
    if downstream:
        # Separate datasets from jobs/dashboards
        datasets   = [e for e in downstream if e.get("type") == "DATASET"]
        jobs       = [e for e in downstream if e.get("type") == "DATA_JOB"]
        dashboards = [e for e in downstream if e.get("type") == "DASHBOARD"]

        blast = []
        if datasets:
            blast.append(f"{len(datasets)} downstream dataset(s)")
        if jobs:
            blast.append(f"{len(jobs)} data job(s)")
        if dashboards:
            blast.append(f"{len(dashboards)} dashboard(s)")

        parts.append(
            f"Blast radius: {', '.join(blast)} are at risk of breakage."
        )
    else:
        parts.append(
            "No downstream consumers were found in the lineage graph; "
            "impact may be limited to direct API/query consumers."
        )

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Main agent class
# ---------------------------------------------------------------------------

class Diagnoser:
    """
    Analyses the impact of a schema break and produces a structured
    diagnosis including root cause, lineage context, and confidence rating.
    """

    def __init__(
        self,
        datahub: Optional[DataHubAdapter] = None,
        store:   Optional[MemoryStore] = None,
    ):
        self._dh    = datahub or DataHubAdapter()
        self._store = store   or get_store()

    # ── Public: diagnose(detection_result) ────────────────────────────────────

    def diagnose(
        self,
        detection_result: Optional[Dict[str, Any]] = None,
        *,
        # Legacy keyword arguments (backward compat)
        dataset_urn: Optional[str] = None,
        diff:        Optional[Dict[str, Any]] = None,
        memory_id:   Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dispatch to the correct internal method depending on call style.

        New style  (preferred):
            diagnoser.diagnose(detection_result)
            — detection_result is the dict from SchemaDetector.detect_schema_break()

        Legacy style (backward compat):
            diagnoser.diagnose(dataset_urn=..., diff=..., memory_id=...)
        """
        if detection_result is not None and isinstance(detection_result, dict):
            # Called with the new detection_result dict
            # (may also have dataset_urn as a positional arg from old callers
            #  that pass dataset_urn as the first positional — handle both)
            if "has_break" in detection_result:
                return self._diagnose_from_detection(detection_result)
            # Caller may have passed dataset_urn as first positional: diagnose(urn_str, diff=...)
            # In that case detection_result is actually the urn string — fall through to legacy.

        # Legacy path: positional dataset_urn, diff dict
        _urn  = dataset_urn or (detection_result if isinstance(detection_result, str) else "")
        _diff = diff or {}
        return self._diagnose_legacy(_urn, _diff, memory_id)

    # ── New diagnosis path ────────────────────────────────────────────────────

    def _diagnose_from_detection(self, detection: Dict[str, Any]) -> Dict[str, Any]:
        """
        Core logic for the new-style diagnose(detection_result) call.

        Returns:
        {
            "dataset_urn":           str,
            "root_cause":            str,
            "upstream_sources":      [{urn, type, name, degree}, ...],
            "downstream_impact":     [{urn, type, name, degree}, ...],
            "affected_field_count":  int,
            "diagnosis_confidence":  "high" | "medium" | "low",
            "break_summary":         str,
        }
        """
        urn            = detection.get("dataset_urn", "")
        missing_fields = detection.get("missing_fields", [])
        type_changes   = detection.get("type_changes",   [])
        new_fields     = detection.get("new_fields",     [])
        severity       = detection.get("severity",       "low")

        logger.info("Diagnoser: new-style diagnosis for %s", urn)

        # 1. Fetch upstream lineage (multi-hop via scrollAcrossLineage)
        upstream = self._dh.get_lineage_scroll(urn, direction="UPSTREAM", max_hops=3)

        # 2. Fetch downstream lineage (multi-hop)
        downstream = self._dh.get_lineage_scroll(urn, direction="DOWNSTREAM", max_hops=3)

        # 3. Build root cause narrative
        root_cause = _build_root_cause(
            urn, missing_fields, type_changes, new_fields, upstream, downstream
        )

        # 4. Affected field count
        affected_count = len(missing_fields) + len(type_changes)

        # 5. Confidence
        confidence = _confidence(upstream, downstream, affected_count)

        # 6. Human-readable break summary
        parts = []
        if missing_fields:
            parts.append(f"{len(missing_fields)} missing field(s): {missing_fields}")
        if type_changes:
            parts.append(f"{len(type_changes)} type change(s)")
        if new_fields:
            parts.append(f"{len(new_fields)} new field(s)")
        break_summary = "; ".join(parts) if parts else "No breaks detected"

        return {
            "dataset_urn":          urn,
            "root_cause":           root_cause,
            "upstream_sources":     upstream,
            "downstream_impact":    downstream,
            "affected_field_count": affected_count,
            "diagnosis_confidence": confidence,
            "break_summary":        break_summary,
            "severity":             severity,
            # Propagate detection fields so downstream agents (Recall, Fixer)
            # can read them directly without caller-side patching.
            "missing_fields":       missing_fields,
            "type_changes":         type_changes,
            "new_fields":           new_fields,
        }

    # ── Legacy diagnosis path ─────────────────────────────────────────────────

    def _diagnose_legacy(
        self,
        dataset_urn: str,
        diff:        Dict[str, Any],
        memory_id:   Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Original diagnose() implementation — uses get_lineage() (1-hop) and
        writes an INCIDENT memory record.  Preserved for backward compat with
        /api/diagnose callers that supply a legacy diff dict.
        """
        logger.info("Diagnoser: legacy diagnosis for %s", dataset_urn)

        downstream  = self._get_downstream_entities_legacy(dataset_urn)
        past_fixes  = self._find_past_fixes(dataset_urn, diff.get("removed", []))
        plan        = self._build_remediation_plan(diff, downstream, past_fixes)

        report: Dict[str, Any] = {
            "dataset_urn":         dataset_urn,
            "diff_summary":        diff.get("summary", ""),
            "downstream_count":    len(downstream),
            "downstream_entities": downstream,
            "past_fixes_found":    len(past_fixes),
            "past_fixes":          past_fixes,
            "remediation_plan":    plan,
        }

        # Persist the diagnosis as an INCIDENT memory record
        incident = MemoryRecord(
            type=MemoryType.INCIDENT,
            entity_urn=dataset_urn,
            title=f"Incident diagnosed: {diff.get('summary', 'schema break')}",
            summary=(
                f"{len(downstream)} downstream affected; "
                f"{len(past_fixes)} prior fixes found."
            ),
            detail=report,
            tags=["incident", "diagnosed"],
            severity="HIGH" if diff.get("is_breaking") else "MEDIUM",
        )
        mem = self._store.add(incident)
        report["incident_memory_id"] = mem.id

        if memory_id:
            existing = self._store.get(memory_id)
            if existing:
                self._store.update(
                    memory_id,
                    detail={**existing.detail, "diagnosis_id": mem.id},
                )

        return report

    # ── Legacy helpers ────────────────────────────────────────────────────────

    def _get_downstream_entities_legacy(
        self, dataset_urn: str, depth: int = 3
    ) -> List[Dict[str, Any]]:
        """Walk downstream lineage using the 1-hop dataset.lineage query."""
        raw = self._dh.get_lineage(dataset_urn, direction="DOWNSTREAM", depth=depth)
        entities = []
        try:
            dataset_node = (raw.get("data") or {}).get("dataset") or {}
            lineage_node = dataset_node.get("lineage") or {}
            relationships = lineage_node.get("relationships", [])
            for rel in relationships:
                e = rel.get("entity") or {}
                entities.append({
                    "urn":  e.get("urn", ""),
                    "type": e.get("type", ""),
                    "name": e.get("name", ""),
                })
        except Exception as exc:
            logger.error("Failed to parse lineage for %s: %s", dataset_urn, exc)
        return entities

    def _find_past_fixes(
        self,
        dataset_urn:    str,
        removed_fields: List[str],
    ) -> List[Dict[str, Any]]:
        """Search memory for prior resolutions involving the same dataset or fields."""
        past = []

        records = self._store.query(
            entity_urn=dataset_urn,
            memory_type=MemoryType.SCHEMA_FIX,
            resolved=True,
        )
        for rec in records:
            past.append({
                "source":  "same_dataset",
                "id":      rec.id,
                "title":   rec.title,
                "summary": rec.summary,
                "detail":  rec.detail,
            })

        for field in removed_fields:
            hits = self._store.search(field)
            for h in hits:
                if h.resolved and h.type == MemoryType.SCHEMA_FIX:
                    past.append({
                        "source":     "same_field_elsewhere",
                        "id":         h.id,
                        "title":      h.title,
                        "summary":    h.summary,
                        "entity_urn": h.entity_urn,
                    })

        seen: set = set()
        unique = []
        for p in past:
            if p["id"] not in seen:
                seen.add(p["id"])
                unique.append(p)
        return unique[:5]

    def _build_remediation_plan(
        self,
        diff:        Dict[str, Any],
        downstream:  List[Dict[str, Any]],
        past_fixes:  List[Dict[str, Any]],
    ) -> List[str]:
        steps = []

        removed      = diff.get("removed", [])
        type_changes = diff.get("type_changes", [])
        added        = diff.get("added", [])

        if downstream:
            names = [e.get("name") or e.get("urn") for e in downstream[:5]]
            steps.append(
                f"WARNING: {len(downstream)} downstream consumer(s) affected: "
                f"{', '.join(names)}"
                + ("..." if len(downstream) > 5 else "")
            )

        for field in removed:
            steps.append(f"CRITICAL: Removed field '{field}' — notify downstream owners.")
            if past_fixes:
                steps.append(
                    f"  HINT: Similar past fix found: '{past_fixes[0]['summary']}' "
                    "— apply same pattern."
                )

        for tc in type_changes:
            steps.append(
                f"WARNING: Type change on '{tc['field']}': "
                f"{tc.get('old_type', tc.get('was', '?'))} -> "
                f"{tc.get('new_type', tc.get('now', '?'))} "
                "— verify downstream serialisation."
            )

        for field in added:
            steps.append(f"INFO: New field '{field}' — update downstream schemas.")

        if not past_fixes:
            steps.append(
                "No prior fix found in memory. "
                "Standard playbook: (1) roll back migration, "
                "(2) add deprecation tags, "
                "(3) coordinate with downstream team before re-applying."
            )
        else:
            steps.append(
                f"{len(past_fixes)} prior resolution(s) found in Anamnesis memory — "
                "prioritise the same fix strategy."
            )

        return steps
