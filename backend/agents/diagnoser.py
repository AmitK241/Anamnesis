"""
Anamnesis – Diagnoser Agent
==============================

Given a detected schema break, the Diagnoser:
  1. Traverses the DataHub lineage graph to find all downstream consumers
  2. Checks Anamnesis memory for previous incidents on the same dataset
  3. Suggests a remediation plan based on past lessons

Usage:
    from backend.agents.diagnoser import Diagnoser
    diagnoser = Diagnoser()
    result = diagnoser.diagnose(dataset_urn="urn:li:dataset:(...)", diff=diff_dict)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.core.datahub_client import DataHubAdapter
from backend.core.memory_store import MemoryRecord, MemoryStore, MemoryType, get_store

logger = logging.getLogger(__name__)


class Diagnoser:
    """
    Analyses the impact of a schema break and proposes remediation steps
    drawing on institutional memory.
    """

    def __init__(
        self,
        datahub: Optional[DataHubAdapter] = None,
        store: Optional[MemoryStore] = None,
    ):
        self._dh = datahub or DataHubAdapter()
        self._store = store or get_store()

    # ── lineage impact analysis ───────────────────────────────────────────────

    def _get_downstream_entities(self, dataset_urn: str, depth: int = 3) -> List[Dict[str, Any]]:
        """Walk downstream lineage and return all affected entities."""
        raw = self._dh.get_lineage(dataset_urn, direction="DOWNSTREAM", depth=depth)
        entities = []
        try:
            relationships = (
                raw.get("data", {})
                .get("entity", {})
                .get("lineage", {})
                .get("relationships", [])
            )
            for rel in relationships:
                e = rel.get("entity", {})
                entities.append({
                    "urn": e.get("urn", ""),
                    "type": e.get("type", ""),
                    "name": e.get("name", ""),
                })
        except Exception as exc:
            logger.error("Failed to parse lineage for %s: %s", dataset_urn, exc)
        return entities

    # ── memory-based remediation ──────────────────────────────────────────────

    def _find_past_fixes(
        self,
        dataset_urn: str,
        removed_fields: List[str],
    ) -> List[Dict[str, Any]]:
        """Search memory for prior resolutions involving the same dataset or fields."""
        past = []

        # By entity URN (same dataset fixed before)
        records = self._store.query(
            entity_urn=dataset_urn,
            memory_type=MemoryType.SCHEMA_FIX,
            resolved=True,
        )
        for rec in records:
            past.append({
                "source": "same_dataset",
                "id": rec.id,
                "title": rec.title,
                "summary": rec.summary,
                "detail": rec.detail,
            })

        # By field name (field removed elsewhere before)
        for field in removed_fields:
            hits = self._store.search(field)
            for h in hits:
                if h.resolved and h.type == MemoryType.SCHEMA_FIX:
                    past.append({
                        "source": "same_field_elsewhere",
                        "id": h.id,
                        "title": h.title,
                        "summary": h.summary,
                        "entity_urn": h.entity_urn,
                    })

        # Deduplicate by id
        seen = set()
        unique = []
        for p in past:
            if p["id"] not in seen:
                seen.add(p["id"])
                unique.append(p)
        return unique[:5]

    def _build_remediation_plan(
        self,
        diff: Dict[str, Any],
        downstream: List[Dict[str, Any]],
        past_fixes: List[Dict[str, Any]],
    ) -> List[str]:
        """Generate actionable remediation steps."""
        steps = []

        removed = diff.get("removed", [])
        type_changes = diff.get("type_changes", [])
        added = diff.get("added", [])

        # Impact statement
        if downstream:
            entity_names = [e.get("name") or e.get("urn") for e in downstream[:5]]
            steps.append(
                f"⚠️  {len(downstream)} downstream consumer(s) affected: {', '.join(entity_names)}"
                + ("…" if len(downstream) > 5 else "")
            )

        # Field removal
        for field in removed:
            steps.append(f"🔴 Removed field `{field}` — notify owners of downstream consumers.")
            if past_fixes:
                steps.append(
                    f"   💡 Similar past fix found: '{past_fixes[0]['summary']}' — apply same pattern."
                )

        # Type changes
        for tc in type_changes:
            steps.append(
                f"🟡 Type change on `{tc['field']}`: {tc['old_type']} → {tc['new_type']} "
                f"— verify downstream serialisation."
            )

        # New fields
        for field in added:
            steps.append(f"🟢 New field `{field}` — update downstream schemas to include it.")

        # If no prior fix found, suggest standard playbook
        if not past_fixes:
            steps.append(
                "📋 No prior fix found in memory. "
                "Standard playbook: (1) roll back migration, (2) add deprecation tags, "
                "(3) coordinate with downstream team before re-applying."
            )
        else:
            steps.append(
                f"📚 {len(past_fixes)} prior resolution(s) found in Anamnesis memory — "
                "prioritise the same fix strategy."
            )

        return steps

    # ── main entry point ──────────────────────────────────────────────────────

    def diagnose(
        self,
        dataset_urn: str,
        diff: Dict[str, Any],
        memory_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run full diagnosis for a schema break.
        Returns a structured report with impact, past fixes, and remediation plan.
        """
        logger.info("Diagnosing schema break for %s", dataset_urn)

        downstream = self._get_downstream_entities(dataset_urn)
        past_fixes = self._find_past_fixes(dataset_urn, diff.get("removed", []))
        plan = self._build_remediation_plan(diff, downstream, past_fixes)

        report = {
            "dataset_urn": dataset_urn,
            "diff_summary": diff.get("summary", ""),
            "downstream_count": len(downstream),
            "downstream_entities": downstream,
            "past_fixes_found": len(past_fixes),
            "past_fixes": past_fixes,
            "remediation_plan": plan,
        }

        # Persist the diagnosis as an INCIDENT memory
        incident = MemoryRecord(
            type=MemoryType.INCIDENT,
            entity_urn=dataset_urn,
            title=f"Incident diagnosed: {diff.get('summary', 'schema break')}",
            summary=f"{len(downstream)} downstream affected; {len(past_fixes)} prior fixes found.",
            detail=report,
            tags=["incident", "diagnosed"],
            severity="HIGH" if diff.get("is_breaking") else "MEDIUM",
        )
        mem = self._store.add(incident)
        report["incident_memory_id"] = mem.id

        if memory_id:
            # Link back to the original detection record
            self._store.update(
                memory_id,
                detail={
                    **((self._store.get(memory_id) or MemoryRecord()).detail),
                    "diagnosis_id": mem.id,
                },
            )

        return report
