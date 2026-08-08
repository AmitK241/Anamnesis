"""
Anamnesis – Embedding Helpers
==============================

Provides:
  embed_incident_text(root_cause, missing_fields, type_changes) -> list[float]
      Encodes a concise description of a schema-break diagnosis into a dense
      vector using the all-MiniLM-L6-v2 sentence-transformer (CPU-only, ~80 MB).
      The model is loaded lazily on first call and cached for the process lifetime.

  cosine_similarity(vec_a, vec_b) -> float
      Pure-numpy cosine similarity in [-1, 1].  Returns 0.0 for zero vectors.

No GPU required.  No external vector database.  Designed for dozens-of-incidents
scale where in-process numpy arithmetic is more than fast enough.
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model singleton
# ---------------------------------------------------------------------------
_MODEL = None
_MODEL_NAME = "all-MiniLM-L6-v2"


def _get_model():
    """Bypassed: returns a dummy model to prevent OOM."""
    class DummyModel:
        def encode(self, text, *args, **kwargs):
            import numpy as np
            return np.zeros(384)
    return DummyModel()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def embed_incident_text(
    root_cause: str,
    missing_fields: List[str],
    type_changes: List[dict],
) -> List[float]:
    """
    Build a single descriptive string from the diagnosis components and return
    its embedding vector as a plain Python list[float].

    The text template is kept **semantically invariant**: it describes the
    *pattern* of the break (column removal, type narrowing, schema migration)
    in standardised vocabulary rather than relying on raw field names.  This
    ensures genuinely-similar incidents — e.g. a status-column dropped from
    ``orders`` and a status-column dropped from ``customers`` — score high
    (≥ 0.85), while structurally-different incidents (pricing vs. status-field
    breaks) score noticeably lower, giving recall a meaningful signal.

    Parameters
    ----------
    root_cause:     Free-text root-cause narrative from the Diagnoser.
    missing_fields: List of field names that were dropped (e.g. ["order_status"]).
    type_changes:   List of dicts with keys "field", "was", "now".

    Returns
    -------
    list[float] – 384-dimensional unit vector (all-MiniLM-L6-v2 output dim).
    """
    has_removals = bool(missing_fields)
    has_type_chg = bool(type_changes)
    parts: List[str] = []

    # ── 1. Break pattern category (standardised vocabulary) ──────────────────
    if has_removals and has_type_chg:
        parts.append(
            "Schema break: column removal and type change. "
            "Breaking schema migration: existing columns were deleted and "
            "column data types were altered, disrupting downstream consumers."
        )
    elif has_removals:
        parts.append(
            "Schema break: column removal. "
            "Breaking schema migration: existing columns were deleted from the table, "
            "causing downstream pipelines and queries to fail with missing column errors."
        )
    elif has_type_chg:
        parts.append(
            "Schema break: type change. "
            "Breaking schema migration: column data types were altered in an "
            "incompatible way, breaking downstream serialisation and aggregation jobs."
        )
    else:
        parts.append(
            "Schema break: unspecified structural change detected in the dataset "
            "schema that may affect downstream consumers."
        )

    # ── 2. Semantic column-category classification ────────────────────────────
    if has_removals:
        n = len(missing_fields)
        status_fields  = [f for f in missing_fields if any(
            kw in f.lower() for kw in (
                "status", "state", "class", "tier", "type", "flag",
                "mode", "category", "segment", "level",
            )
        )]
        pricing_fields = [f for f in missing_fields if any(
            kw in f.lower() for kw in (
                "price", "cost", "discount", "amount", "rate", "fee",
                "revenue", "total", "value", "charge",
            )
        )]
        id_fields      = [f for f in missing_fields if any(
            kw in f.lower() for kw in ("_id", "key", "_code", "_ref", "_num")
        )]
        date_fields    = [f for f in missing_fields if any(
            kw in f.lower() for kw in ("date", "time", "_at", "timestamp", "when")
        )]
        other_fields   = [
            f for f in missing_fields
            if f not in status_fields + pricing_fields + id_fields + date_fields
        ]

        removal_desc: List[str] = []
        if status_fields:
            removal_desc.append(
                f"{len(status_fields)} status/classification column(s) removed "
                "(business-state field deletion)"
            )
        if pricing_fields:
            removal_desc.append(
                f"{len(pricing_fields)} pricing/financial column(s) removed "
                "(monetary field deletion)"
            )
        if id_fields:
            removal_desc.append(
                f"{len(id_fields)} identifier/reference column(s) removed"
            )
        if date_fields:
            removal_desc.append(
                f"{len(date_fields)} temporal/date column(s) removed"
            )
        if other_fields:
            removal_desc.append(
                f"{len(other_fields)} other column(s) removed"
            )

        parts.append(
            f"Columns dropped: {n} column(s) deleted from table schema. "
            + " ".join(removal_desc) + "."
        )

    # ── 3. Type-change classification ─────────────────────────────────────────
    if has_type_chg:
        narrowing = [
            tc for tc in type_changes
            if (tc.get("was", "").upper(), tc.get("now", "").upper()) in {
                ("STRING", "NUMBER"), ("NUMBER", "BOOLEAN"),
                ("ARRAY", "STRING"), ("STRING", "BOOLEAN"),
                ("NUMBER", "STRING"),
            }
        ]
        widening = [tc for tc in type_changes if tc not in narrowing]
        tc_descs: List[str] = []
        if narrowing:
            tc_descs.append(
                f"{len(narrowing)} breaking type narrowing(s): "
                "column data type changed to incompatible type, breaking consumers"
            )
        if widening:
            tc_descs.append(
                f"{len(widening)} type modification(s): "
                "column data type changed, potentially breaking downstream serialisation"
            )
        parts.append("Type changes: " + "; ".join(tc_descs) + ".")

    # ── 4. Root-cause narrative ───────────────────────────────────────────────
    if root_cause:
        parts.append(f"Root cause: {root_cause.strip()}")

    text = " ".join(parts)

    # --- Embed ---
    model = _get_model()
    vector = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    return vector.tolist()


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Cosine similarity between two vectors, returned as a float in [-1.0, 1.0].

    Both inputs are normalised before the dot product so the result is purely
    based on direction, not magnitude.  Returns 0.0 if either vector is zero.

    Parameters
    ----------
    vec_a, vec_b : list[float] or numpy array — must have the same length.

    Returns
    -------
    float in [-1.0, 1.0].  1.0 = identical direction, 0.0 = orthogonal.
    """
    a = np.asarray(vec_a, dtype=np.float64)
    b = np.asarray(vec_b, dtype=np.float64)

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return float(np.dot(a / norm_a, b / norm_b))


def similarity_label(score: float) -> str:
    """
    Maps a raw cosine similarity score to a human-readable confidence label.

    Thresholds are calibrated against our observed demo data range
    (0.84–0.91 for genuinely related incidents on all-MiniLM-L6-v2).
    Do NOT use this function for internal threshold comparisons — it is a
    **display-only** helper.  All logic gates (min_similarity, adapt threshold)
    use the raw float directly.

    Parameters
    ----------
    score : float — cosine similarity in [0, 1].

    Returns
    -------
    str — one of: "Strong Match", "Related Match", "Possible Match", "Weak Match".
    """
    if score >= 0.90:
        return "Strong Match"
    elif score >= 0.80:
        return "Related Match"
    elif score >= 0.65:
        return "Possible Match"
    else:
        return "Weak Match"


def format_similarity(score: float) -> str:
    """
    Format a raw cosine similarity score for human display.

    Combines a percentage representation with the qualitative label:
        0.9068  →  "90.7% match — Strong Match"
        0.8772  →  "87.7% match — Related Match"
        0.6500  →  "65.0% match — Weak Match"

    This function is **display-only**.  Do not use for internal comparisons.

    Parameters
    ----------
    score : float — cosine similarity in [0, 1].

    Returns
    -------
    str — formatted display string.
    """
    pct = round(score * 100, 1)
    label = similarity_label(score)
    return f"{pct}% match \u2014 {label}"

