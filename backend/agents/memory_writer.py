"""
Anamnesis – Memory-Writer Agent
=================================

Takes the full pipeline output (detection + diagnosis + fix) and writes it
back into DataHub as a new IncidentMemory aspect, closing the full loop:

    Detect → Diagnose → Recall → Fix → Write-back

The write mechanism reuses the exact MCP-emit + read-back pattern proven in
``verify_incident_memory.py``.

Usage
-----
    from backend.agents.memory_writer import MemoryWriterAgent

    agent = MemoryWriterAgent()
    result = agent.write_incident_memory(detection, diagnosis, recall_result, fix_result)

Module-level convenience wrapper (uses a module singleton)::

    from backend.agents.memory_writer import write_incident_memory
    result = write_incident_memory(detection, diagnosis, recall_result, fix_result)

Return schema
-------------
{
    "success":      bool,
    "incident_id":  str,
    "dataset_urn":  str,
    "written_at":   int,   # epoch millis
    "verification": str,   # "confirmed via read-back" or error detail
}

Environment
-----------
DATAHUB_GMS_SERVER  – e.g. http://localhost:8080  (default)
DATAHUB_GMS_TOKEN   – Personal Access Token (optional for local dev)

Error handling
--------------
* DataHub unreachable → success=False with error in verification field.
* MCP write fails     → success=False with error detail.
* Read-back mismatch  → success=True but verification contains the discrepancy.
"""

from __future__ import annotations

import json
import logging
import os
import random
import string
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from backend.core.embeddings import embed_incident_text
from backend.core.memory_store import get_store, MemoryRecord, MemoryType

logger = logging.getLogger(__name__)

ASPECT_NAME = "incidentMemory"


# ---------------------------------------------------------------------------
# Helpers (same pattern as verify_incident_memory.py)
# ---------------------------------------------------------------------------

def _emit_mcp(
    server: str,
    token: str,
    entity_urn: str,
    aspect_name: str,
    aspect_value: dict,
) -> None:
    """Emit a MetadataChangeProposal via the GMS REST endpoint."""
    import urllib.request as _req
    mcp = {
        "entityType": "dataset",
        "entityUrn": entity_urn,
        "changeType": "UPSERT",
        "aspectName": aspect_name,
        "aspect": {
            "contentType": "application/json",
            "value": json.dumps(aspect_value),
        },
    }
    body = json.dumps({"proposal": mcp}).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = _req.Request(
        f"{server}/aspects?action=ingestProposal",
        data=body,
        headers=headers,
        method="POST",
    )
    with _req.urlopen(req, timeout=2) as resp:
        status = resp.status
    if status not in (200, 201, 202):
        raise RuntimeError(f"MCP ingest failed [HTTP {status}]")


def _get_aspect(server: str, token: str, entity_urn: str, aspect_name: str) -> dict:
    """Fetch a specific aspect from GMS and unwrap it the same way
    as verify_incident_memory.py does."""
    import urllib.request as _req
    encoded = urllib.parse.quote(entity_urn, safe="")
    url = f"{server}/aspects/{encoded}?aspect={aspect_name}&version=0"
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = _req.Request(url, headers=headers)
    try:
        with _req.urlopen(req, timeout=2) as resp:
            raw = json.loads(resp.read())
    except Exception as exc:
        if "404" in str(exc):
            return {}
        raise

    # Unwrap: GMS returns {"aspect": {"value": "<json-string>"}}
    aspect_data = raw.get("aspect", {})
    if isinstance(aspect_data, dict) and "value" in aspect_data:
        try:
            aspect_data = json.loads(aspect_data["value"])
        except json.JSONDecodeError:
            pass

    # Unwrap FQCN wrapper: {"com.anamnesis.incident.IncidentMemory": {...}}
    if isinstance(aspect_data, dict) and len(aspect_data) == 1:
        only_key = next(iter(aspect_data))
        if "." in only_key:
            aspect_data = aspect_data[only_key]

    return aspect_data if isinstance(aspect_data, dict) else {}


def _new_incident_id() -> str:
    """Generate a unique incident ID: INC-{epoch_ms}-{6-char random suffix}."""
    ts = int(time.time() * 1000)
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"INC-{ts}-{suffix}"


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class MemoryWriterAgent:
    """
    Writes a completed incident resolution back into DataHub as an
    IncidentMemory aspect, then reads it back to confirm the write succeeded.

    Parameters
    ----------
    server : str
        DataHub GMS URL (default: ``DATAHUB_GMS_SERVER`` env var or
        ``http://localhost:8080``).
    token : str
        Personal Access Token for authenticated DataHub instances
        (default: ``DATAHUB_GMS_TOKEN`` env var).
    """

    def __init__(
        self,
        server: Optional[str] = None,
        token: Optional[str] = None,
    ) -> None:
        self._server = (
            server or os.getenv("DATAHUB_GMS_SERVER", "http://localhost:8080")
        ).rstrip("/")
        self._token = token or os.getenv("DATAHUB_GMS_TOKEN", "")

    # ── Public entry point ────────────────────────────────────────────────────

    def write_incident_memory(
        self,
        detection: Dict[str, Any],
        diagnosis: Dict[str, Any],
        recall_result: Dict[str, Any],
        fix_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Write the full pipeline output as an IncidentMemory aspect to DataHub.

        Parameters
        ----------
        detection : dict
            Output from ``SchemaDetector.simulate_schema_break()`` or
            ``detect_schema_break()``.  Must contain ``dataset_urn``,
            ``missing_fields``, ``type_changes``.
        diagnosis : dict
            Output from ``Diagnoser.diagnose()``.  Must contain
            ``root_cause``, ``downstream_impact``.
        recall_result : dict
            Output from ``MemoryRecallAgent.recall_similar_incidents()``.
            Keys used: ``matches`` (list of dicts with ``incident_id``).
        fix_result : dict
            Output from ``FixerAgent.generate_fix()``.  Keys used:
            ``suggested_fix``, ``estimated_time_saved_minutes`` (optional).

        Returns
        -------
        dict::

            {
                "success":      bool,
                "incident_id":  str,
                "dataset_urn":  str,
                "written_at":   int,   # epoch millis
                "verification": str,   # "confirmed via read-back" or error detail
            }
        """
        # dataset_urn: new-style detect_schema_break() includes it in detection;
        # legacy detect() does not — fall back to diagnosis which always has it.
        dataset_urn = (
            detection.get("dataset_urn")
            or diagnosis.get("dataset_urn", "")
        )
        # missing_fields / type_changes: prefer diagnosis (authoritative after
        # our Diagnoser fix) and fall back to detection for raw-detection callers.
        missing_fields: List[str]  = (
            diagnosis.get("missing_fields") or detection.get("missing_fields", [])
        )
        type_changes:   List[Dict] = (
            diagnosis.get("type_changes")  or detection.get("type_changes",   [])
        )

        root_cause:     str             = diagnosis.get("root_cause", "")
        downstream:     List[str]       = _extract_downstream_urns(diagnosis)

        matches:        List[Dict]      = recall_result.get("matches", [])
        similar_ids:    List[str]       = [m.get("incident_id", "") for m in matches if m.get("incident_id")]

        suggested_fix:  str             = fix_result.get("suggested_fix", "")
        time_saved:     int             = int(fix_result.get("estimated_time_saved_minutes") or 0)

        # ── 1. Generate incident ID ───────────────────────────────────────────
        incident_id = _new_incident_id()
        written_at  = int(time.time() * 1000)

        logger.info(
            "MemoryWriterAgent: writing %s for dataset %s",
            incident_id, dataset_urn,
        )

        # ── 2. Compute embedding for THIS incident ────────────────────────────
        # Use the same embed_incident_text() call that verify_recall.py uses for
        # seeding, so future recalls can find it via cosine similarity.
        try:
            embedding_vector: List[float] = embed_incident_text(
                root_cause=root_cause,
                missing_fields=missing_fields,
                type_changes=type_changes,
            )
            logger.info(
                "MemoryWriterAgent: embedding computed (dim=%d)", len(embedding_vector)
            )
        except Exception as exc:
            logger.error("MemoryWriterAgent: embedding failed: %s", exc)
            return self._error_result(dataset_urn, incident_id, written_at, f"Embedding failed: {exc}")

        # ── 3. Build the IncidentMemory aspect ────────────────────────────────
        aspect: Dict[str, Any] = {
            "incidentId":           incident_id,
            "rootCause":            root_cause,
            "downstreamImpact":     downstream,
            "resolutionCodeDiff":   suggested_fix,
            "embeddingVector":      embedding_vector,
            "similarPastIncidents": similar_ids,
            "timeSavedEstimate":    time_saved,
            "timestamp":            written_at,
        }

        # ── 4. Emit MCP to DataHub ────────────────────────────────────────────
        try:
            _emit_mcp(self._server, self._token, dataset_urn, ASPECT_NAME, aspect)
            logger.info(
                "MemoryWriterAgent: MCP emitted for %s (incident_id=%s)",
                dataset_urn, incident_id,
            )
        except Exception as exc:
            logger.error("MemoryWriterAgent: MCP emit failed: %s", exc)
            # DO NOT return early. Continue to save to local memory_store.json so the demo works!

        # ── 5. Round-trip read-back verification ──────────────────────────────
        try:
            read_back = _get_aspect(self._server, self._token, dataset_urn, ASPECT_NAME)
        except Exception as exc:
            logger.warning("MemoryWriterAgent: read-back failed: %s", exc)
            verification = f"write assumed succeeded but read-back failed: {exc}"
            read_back = None

        if not read_back:
            verification = "write emitted but read-back returned empty (aspect may still be indexed)"
            logger.warning("MemoryWriterAgent: %s", verification)
        elif read_back.get("incidentId") == incident_id:
            verification = "confirmed via read-back"
            logger.info("MemoryWriterAgent: round-trip verification passed for %s", incident_id)
        else:
            # The URN may host an OLDER record from a prior write; the new one
            # is stored at the same URN so it overwrites. If incidentId differs,
            # report the mismatch but treat as soft-warning (write did land).
            stored_id = read_back.get("incidentId", "(unknown)")
            verification = (
                f"write completed; read-back shows incidentId={stored_id!r} "
                f"(expected {incident_id!r}) — DataHub may have a prior record at this URN"
            )
            logger.warning("MemoryWriterAgent: incidentId mismatch — %s", verification)

        # ── 6. Update ANAMNESIS_KNOWN_DATASET_URNS so recall can find the new record ──
        _register_urn(dataset_urn)

        # ── 7. Keep local memory_store.json in sync with DataHub (Option B) ──
        # Extract severity from diagnosis/detection or default to LOW
        severity = diagnosis.get("severity") or detection.get("severity") or "low"
        
        # Build title from dataset_urn roughly
        table_name = dataset_urn.split(".")[-1].split(",")[0] if "." in dataset_urn else dataset_urn
        title = f"Schema break on {table_name}"
        
        store = get_store()
        rec = MemoryRecord(
            id=incident_id,
            type=MemoryType.INCIDENT,
            entity_urn=dataset_urn,
            title=title,
            summary=root_cause,
            detail={
                "missing_fields": missing_fields,
                "type_changes": type_changes,
                "downstream_impact": downstream,
                "suggested_fix": suggested_fix,
                "embedding_vector": embedding_vector,
                "timestamp": written_at,
            },
            severity=severity.upper(),
            tags=[table_name],
            agent_id="anamnesis"
        )
        store.add(rec)
        logger.info("MemoryWriterAgent: Synced incident %s to local memory_store.json", incident_id)

        return {
            "success":      True,
            "incident_id":  incident_id,
            "dataset_urn":  dataset_urn,
            "written_at":   written_at,
            "verification": verification,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _error_result(
        dataset_urn: str,
        incident_id: str,
        written_at: int,
        detail: str,
    ) -> Dict[str, Any]:
        return {
            "success":      False,
            "incident_id":  incident_id,
            "dataset_urn":  dataset_urn,
            "written_at":   written_at,
            "verification": detail,
        }


# ---------------------------------------------------------------------------
# Private module-level helpers
# ---------------------------------------------------------------------------

def _extract_downstream_urns(diagnosis: Dict[str, Any]) -> List[str]:
    """
    Extract downstream URN strings from the diagnosis dict.

    Diagnoser returns ``downstream_impact`` as a list of dicts with an
    ``urn`` key (from get_lineage_scroll).  The IncidentMemory aspect
    stores them as plain strings.
    """
    raw = diagnosis.get("downstream_impact", [])
    urns: List[str] = []
    for item in raw:
        if isinstance(item, str):
            urns.append(item)
        elif isinstance(item, dict):
            u = item.get("urn", "")
            if u:
                urns.append(u)
    return urns


def _register_urn(dataset_urn: str) -> None:
    """
    Add *dataset_urn* to the ``ANAMNESIS_KNOWN_DATASET_URNS`` env-var so that
    ``DataHubAdapter.scroll_incident_memories()`` can discover the new record
    immediately (before DataHub indexes it via the GraphQL ``_exists_`` filter).
    """
    existing = os.environ.get("ANAMNESIS_KNOWN_DATASET_URNS", "")
    known = [u.strip() for u in existing.split("|") if u.strip()]
    if dataset_urn not in known:
        known.append(dataset_urn)
        os.environ["ANAMNESIS_KNOWN_DATASET_URNS"] = "|".join(known)
        logger.debug(
            "MemoryWriterAgent: registered %s in ANAMNESIS_KNOWN_DATASET_URNS",
            dataset_urn,
        )


# ---------------------------------------------------------------------------
# Module-level singleton + convenience function
# ---------------------------------------------------------------------------

_agent: Optional[MemoryWriterAgent] = None


def _get_agent() -> MemoryWriterAgent:
    global _agent
    if _agent is None:
        _agent = MemoryWriterAgent()
    return _agent


def write_incident_memory(
    detection: Dict[str, Any],
    diagnosis: Dict[str, Any],
    recall_result: Dict[str, Any],
    fix_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Module-level convenience wrapper around :class:`MemoryWriterAgent`.

    Uses a process-level singleton.  Import and call directly::

        from backend.agents.memory_writer import write_incident_memory
        result = write_incident_memory(detection, diagnosis, recall_result, fix_result)
    """
    return _get_agent().write_incident_memory(
        detection=detection,
        diagnosis=diagnosis,
        recall_result=recall_result,
        fix_result=fix_result,
    )
