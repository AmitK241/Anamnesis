"""
Anamnesis – Memory-Recall Agent
=================================

Given a current diagnosis, find the most semantically similar past incidents
stored in DataHub as IncidentMemory aspects and return them ranked by cosine
similarity of their embedding vectors.

Entry point
-----------
    from backend.agents.recall import MemoryRecallAgent

    agent = MemoryRecallAgent()
    result = agent.recall_similar_incidents(diagnosis, top_k=3, min_similarity=0.75)

Module-level convenience wrapper (uses a module singleton)::

    from backend.agents.recall import recall_similar_incidents
    result = recall_similar_incidents(diagnosis)

Return schema
-------------
{
    "query_diagnosis_urn":        str,
    "matches": [
        {
            "incident_id":           str,
            "dataset_urn":           str,
            "root_cause":            str,
            "resolution_code_diff":  str,
            "time_saved_estimate":   int,
            "downstream_impact":     list[str],
            "similarity_score":      float,   # in [0, 1]
        },
        ...
    ],
    "no_similar_incidents_found": bool,
    "total_past_incidents_checked": int,
    "top_k":                       int,
    "min_similarity":              float,
}

Error handling
--------------
* Zero past incidents in DataHub → returns empty matches, no error.
* Past incident has no embedding vector → skipped (score = 0.0 if included).
* sentence-transformers not installed → RuntimeError with install hint.
* DataHub unreachable → empty past list returned, recall returns empty matches.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.core.datahub_client import DataHubAdapter
from backend.core.embeddings import (
    cosine_similarity,
    embed_incident_text,
    format_similarity,
    similarity_label,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------


class MemoryRecallAgent:
    """
    Semantic incident-recall agent.

    Fetches all past IncidentMemory aspects from DataHub, computes cosine
    similarity against the query diagnosis embedding, and returns the top-k
    matches above the configured threshold.
    """

    def __init__(self, datahub: Optional[DataHubAdapter] = None):
        self._dh = datahub or DataHubAdapter()

    def recall_similar_incidents(
        self,
        diagnosis: Dict[str, Any],
        top_k: int = 3,
        min_similarity: float = 0.75,
    ) -> Dict[str, Any]:
        """
        Find past incidents semantically similar to ``diagnosis``.

        Parameters
        ----------
        diagnosis:
            The structured dict returned by Diagnoser.diagnose() or constructed
            manually.  Keys used:
              - ``root_cause``    (str)         — primary narrative text
              - ``missing_fields`` (list[str])  — from detection_result / diagnosis
              - ``type_changes``  (list[dict])  — each with 'field', 'was', 'now'
              - ``dataset_urn``   (str)         — for labelling the result
        top_k:
            Maximum number of similar incidents to return (default 3).
        min_similarity:
            Cosine-similarity threshold in [0, 1].  Incidents scoring below this
            are excluded from results (default 0.75).

        Returns
        -------
        dict — see module docstring for full schema.
        """
        dataset_urn     = diagnosis.get("dataset_urn", "")
        root_cause      = diagnosis.get("root_cause", "")

        # Diagnoser new-style output uses these keys from the detection_result
        missing_fields  = diagnosis.get("missing_fields", [])
        type_changes    = diagnosis.get("type_changes", [])

        # Fall back to break_summary fields if the caller passes a raw detection_result
        if not missing_fields and "break_summary" in diagnosis:
            # parse nothing — embed_incident_text handles empty lists gracefully
            pass

        # ── 1. Build query embedding ───────────────────────────────────────────
        logger.info(
            "MemoryRecallAgent: embedding query diagnosis for %s "
            "(missing=%d, type_changes=%d)",
            dataset_urn, len(missing_fields), len(type_changes),
        )
        query_vector = embed_incident_text(
            root_cause=root_cause,
            missing_fields=missing_fields,
            type_changes=type_changes,
        )

        # ── 2. Fetch all past IncidentMemory records ───────────────────────────
        past_records = self._dh.scroll_incident_memories()
        total_checked = len(past_records)
        logger.info("MemoryRecallAgent: %d past incident(s) loaded from DataHub", total_checked)

        if total_checked == 0:
            return self._empty_result(dataset_urn, top_k, min_similarity)

        # ── 3. Score each past record ──────────────────────────────────────────
        scored: List[Dict[str, Any]] = []
        for rec in past_records:
            past_vec = rec.get("embedding_vector", [])
            if not past_vec:
                logger.debug(
                    "Skipping %s (incident_id=%s) — no embeddingVector",
                    rec.get("dataset_urn"), rec.get("incident_id"),
                )
                continue

            score = cosine_similarity(query_vector, past_vec)
            logger.debug(
                "  similarity %s (id=%s) = %.4f",
                rec.get("dataset_urn"), rec.get("incident_id"), score,
            )

            if score >= min_similarity:
                scored.append({
                    "incident_id":          rec.get("incident_id", ""),
                    "dataset_urn":          rec.get("dataset_urn", ""),
                    "root_cause":           rec.get("root_cause", ""),
                    "resolution_code_diff": rec.get("resolution_code_diff", ""),
                    "time_saved_estimate":  rec.get("time_saved_estimate", 0),
                    "downstream_impact":    rec.get("downstream_impact", []),
                    # ── raw score (used for all internal logic) ──────────────
                    "similarity_score":     round(score, 4),
                    # ── display-only fields (do not use for comparisons) ─────
                    "similarity_pct":       f"{round(score * 100, 1)}%",
                    "similarity_label":     similarity_label(score),
                    "similarity_display":   format_similarity(score),
                })

        # ── 4. Sort and truncate ──────────────────────────────────────────────
        scored.sort(key=lambda m: m["similarity_score"], reverse=True)
        matches = scored[:top_k]

        no_match = len(matches) == 0
        if no_match:
            logger.info(
                "MemoryRecallAgent: no incidents found above similarity threshold %.2f",
                min_similarity,
            )
        else:
            logger.info(
                "MemoryRecallAgent: %d match(es) returned (top score=%.4f)",
                len(matches), matches[0]["similarity_score"],
            )

        return {
            "query_diagnosis_urn":          dataset_urn,
            "matches":                      matches,
            "no_similar_incidents_found":   no_match,
            "total_past_incidents_checked": total_checked,
            "top_k":                        top_k,
            "min_similarity":               min_similarity,
        }

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _empty_result(
        dataset_urn: str,
        top_k: int,
        min_similarity: float,
    ) -> Dict[str, Any]:
        return {
            "query_diagnosis_urn":          dataset_urn,
            "matches":                      [],
            "no_similar_incidents_found":   True,
            "total_past_incidents_checked": 0,
            "top_k":                        top_k,
            "min_similarity":               min_similarity,
        }


# ---------------------------------------------------------------------------
# Module-level singleton + convenience function
# ---------------------------------------------------------------------------

_agent: Optional[MemoryRecallAgent] = None


def _get_agent() -> MemoryRecallAgent:
    global _agent
    if _agent is None:
        _agent = MemoryRecallAgent()
    return _agent


def recall_similar_incidents(
    diagnosis: Dict[str, Any],
    top_k: int = 3,
    min_similarity: float = 0.75,
) -> Dict[str, Any]:
    """
    Module-level convenience wrapper around :class:`MemoryRecallAgent`.

    Uses a process-level singleton DataHubAdapter.  Import and call directly::

        from backend.agents.recall import recall_similar_incidents
        result = recall_similar_incidents(diagnosis)
    """
    return _get_agent().recall_similar_incidents(
        diagnosis=diagnosis,
        top_k=top_k,
        min_similarity=min_similarity,
    )
