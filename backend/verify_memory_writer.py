# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
backend/verify_memory_writer.py
---------------------------------
End-to-end verification of the Memory-Writer agent.

Steps
-----
a. Run the full pipeline against the "orders" dataset with simulate=True.
b. Confirm write_incident_memory() returns success=True and a real incident_id.
c. Independently re-read the aspect directly via raw REST (bypassing our
   own code) to confirm the data actually landed in DataHub.
d. Call recall_similar_incidents() with a diagnosis matching what was just
   written, and confirm THIS incident now shows up as a similarity match --
   proving the loop is genuinely closed.

Usage:
    python -m backend.verify_memory_writer
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request

# Re-configure stdout for UTF-8 on Windows consoles that default to cp1252.
import io as _io
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = _io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATAHUB_GMS_URL = os.getenv("DATAHUB_GMS_SERVER", "http://localhost:8080")
ASPECT_NAME = "incidentMemory"
ORDERS_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:postgres,"
    "b2fd91.order_entry_db.order_entry.orders,PROD)"
)

# ---------------------------------------------------------------------------
# Status helpers (same style as other verify scripts)
# ---------------------------------------------------------------------------
_failures: list = []


def oks(msg: str) -> None:
    print(f"  ✅ {msg}")


def fail(msg: str) -> None:
    print(f"  ❌ {msg}")
    _failures.append(msg)


def check(condition: bool, msg_pass: str, msg_fail: str) -> bool:
    if condition:
        oks(msg_pass)
        return True
    else:
        fail(msg_fail)
        return False


def fatal(msg: str) -> None:
    """Print a fatal error and exit immediately."""
    print(f"  ❌ FATAL: {msg}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Raw DataHub helpers (bypass our own code for independent verification)
# ---------------------------------------------------------------------------

def _raw_get_aspect(entity_urn: str, aspect_name: str) -> dict:
    """
    Fetch an aspect from DataHub GMS REST API directly — no wrappers, no SDK.
    Returns the unwrapped aspect dict, or {} on 404.
    """
    encoded = urllib.parse.quote(entity_urn, safe="")
    url = f"{DATAHUB_GMS_URL}/aspects/{encoded}?aspect={aspect_name}&version=0"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read())
    except Exception as exc:
        if "404" in str(exc):
            return {}
        raise

    # Unwrap JSON-string value
    aspect_data = raw.get("aspect", {})
    if isinstance(aspect_data, dict) and "value" in aspect_data:
        try:
            aspect_data = json.loads(aspect_data["value"])
        except json.JSONDecodeError:
            pass

    # Unwrap FQCN wrapper
    if isinstance(aspect_data, dict) and len(aspect_data) == 1:
        only_key = next(iter(aspect_data))
        if "." in only_key:
            aspect_data = aspect_data[only_key]

    return aspect_data if isinstance(aspect_data, dict) else {}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 65)
    print("  verify_memory_writer.py — Memory-Writer Agent Verification")
    print(f"  GMS URL: {DATAHUB_GMS_URL}")
    print(f"  Dataset: orders (simulated break)")
    print("=" * 65)

    # ──────────────────────────────────────────────────────────────────────────
    # 0. GMS connectivity
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[0] Checking GMS connectivity…")
    try:
        resp = urllib.request.urlopen(f"{DATAHUB_GMS_URL}/config", timeout=10)
        resp.read()
        oks("GMS reachable")
    except Exception as e:
        fatal(f"Cannot reach GMS at {DATAHUB_GMS_URL}: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Stage 1 — Detect (simulate=True)
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[1] Stage 1 – Detect (simulate=True)…")
    try:
        from backend.agents.detector import SchemaDetector
        detector = SchemaDetector()
        detection = detector.simulate_schema_break(ORDERS_URN)
    except Exception as e:
        fatal(f"SchemaDetector.simulate_schema_break failed: {e}")

    check(
        detection.get("has_break") is True,
        f"Detection: has_break=True  severity={detection.get('severity')}",
        f"Detection: expected has_break=True, got {detection.get('has_break')}",
    )
    print(f"     missing_fields : {detection.get('missing_fields', [])}")
    print(f"     type_changes   : {detection.get('type_changes', [])}")

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Stage 2 — Diagnose
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[2] Stage 2 – Diagnose…")
    try:
        from backend.agents.diagnoser import Diagnoser
        diagnoser = Diagnoser()
        diagnosis = diagnoser.diagnose(detection)
        # Propagate missing_fields / type_changes if diagnoser didn't echo them
        if "missing_fields" not in diagnosis:
            diagnosis["missing_fields"] = detection.get("missing_fields", [])
        if "type_changes" not in diagnosis:
            diagnosis["type_changes"] = detection.get("type_changes", [])
    except Exception as e:
        fatal(f"Diagnoser.diagnose failed: {e}")

    check(
        bool(diagnosis.get("root_cause")),
        "Diagnosis: root_cause is non-empty",
        "Diagnosis: root_cause is missing or empty",
    )
    check(
        "dataset_urn" in diagnosis,
        "Diagnosis: dataset_urn present",
        "Diagnosis: dataset_urn missing",
    )
    print(f"     confidence     : {diagnosis.get('diagnosis_confidence')}")
    print(f"     root_cause     : {str(diagnosis.get('root_cause',''))[:100]}…")

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Stage 3 — Recall
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[3] Stage 3 – Recall (min_similarity=0.70)…")
    try:
        from backend.agents.recall import recall_similar_incidents
        recall_result = recall_similar_incidents(
            diagnosis=diagnosis,
            top_k=3,
            min_similarity=0.70,
        )
    except Exception as e:
        fatal(f"recall_similar_incidents failed: {e}")

    print(f"     past incidents checked : {recall_result.get('total_past_incidents_checked', 0)}")
    print(f"     matches found          : {len(recall_result.get('matches', []))}")
    oks("Recall completed (0 matches is acceptable — no prior incidents required)")

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Stage 4 — Fix
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[4] Stage 4 – Fix (calls Groq LLM)…")
    print("     (this may take a few seconds for the first LLM call)")
    try:
        from backend.agents.fixer import FixerAgent
        fixer = FixerAgent()
        fix_result = fixer.generate_fix(diagnosis=diagnosis, recall_result=recall_result)
    except Exception as e:
        fatal(f"FixerAgent.generate_fix failed: {e}")

    check(
        bool(fix_result.get("suggested_fix")),
        f"Fix: suggested_fix is non-empty  (mode={fix_result.get('mode')})",
        "Fix: suggested_fix is empty",
    )
    print(f"     mode           : {fix_result.get('mode')}")
    print(f"     fix preview    : {str(fix_result.get('suggested_fix',''))[:100]}…")

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Stage 5 — Write-memory
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[5] Stage 5 – write_incident_memory()…")
    try:
        from backend.agents.memory_writer import write_incident_memory
        write_result = write_incident_memory(
            detection=detection,
            diagnosis=diagnosis,
            recall_result=recall_result,
            fix_result=fix_result,
        )
    except Exception as e:
        fatal(f"write_incident_memory raised an exception: {e}")
        import traceback; traceback.print_exc()

    # ── Check (b): success=True and real incident_id ─────────────────────────
    check(
        write_result.get("success") is True,
        f"write_incident_memory() returned success=True",
        f"write_incident_memory() returned success=False — detail: {write_result.get('verification')}",
    )

    incident_id = write_result.get("incident_id", "")
    check(
        incident_id.startswith("INC-") and len(incident_id) > 10,
        f"incident_id looks real: {incident_id}",
        f"incident_id looks invalid: {incident_id!r}",
    )

    check(
        write_result.get("dataset_urn") == ORDERS_URN,
        f"dataset_urn matches orders URN",
        f"dataset_urn mismatch: {write_result.get('dataset_urn')}",
    )

    check(
        "verified" in (write_result.get("verification") or "").lower()
        or "confirmed" in (write_result.get("verification") or "").lower()
        or "write" in (write_result.get("verification") or "").lower(),
        f"verification field: '{write_result.get('verification')}'",
        f"unexpected verification: '{write_result.get('verification')}'",
    )

    print(f"\n     incident_id    : {incident_id}")
    print(f"     written_at     : {write_result.get('written_at')}")
    print(f"     verification   : {write_result.get('verification')}")

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Check (c): Independent read-back via raw REST (bypass our code)
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[6] Check (c) – Independent raw REST read-back (bypassing our code)…")
    # Brief pause to allow DataHub to commit the aspect before we read it back
    time.sleep(0.5)

    try:
        raw_aspect = _raw_get_aspect(ORDERS_URN, ASPECT_NAME)
    except Exception as e:
        fail(f"Raw REST read-back failed with exception: {e}")
        raw_aspect = {}

    check(
        bool(raw_aspect),
        "Raw REST: incidentMemory aspect exists in DataHub",
        "Raw REST: incidentMemory aspect returned empty (write may not have landed yet)",
    )

    if raw_aspect:
        stored_id = raw_aspect.get("incidentId", "")
        # The stored ID is the one that was written LAST.  Our new write overwrote
        # any previous record at this URN, so stored_id should equal incident_id.
        check(
            stored_id == incident_id,
            f"Raw REST: incidentId={stored_id!r} matches written incident_id",
            f"Raw REST: incidentId={stored_id!r} ≠ written={incident_id!r} "
            "(another write may have raced, or the aspect is stale)",
        )

        check(
            bool(raw_aspect.get("embeddingVector")),
            f"Raw REST: embeddingVector present (dim={len(raw_aspect.get('embeddingVector', []))})",
            "Raw REST: embeddingVector is missing or empty",
        )

        check(
            bool(raw_aspect.get("resolutionCodeDiff")),
            "Raw REST: resolutionCodeDiff is non-empty",
            "Raw REST: resolutionCodeDiff missing",
        )

        check(
            isinstance(raw_aspect.get("timestamp"), int) and raw_aspect["timestamp"] > 0,
            f"Raw REST: timestamp={raw_aspect.get('timestamp')}",
            "Raw REST: timestamp missing or invalid",
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 7. Check (d): Recall finds the newly written incident
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[7] Check (d) – Recall closes the loop: new incident is now recallable…")

    # The env var ANAMNESIS_KNOWN_DATASET_URNS was updated by write_incident_memory().
    # Reset the recall agent singleton so it picks up the new env var state.
    import backend.agents.recall as _recall_mod
    _recall_mod._agent = None

    # Build a diagnosis that closely matches what we JUST wrote
    loop_diagnosis = {
        "dataset_urn":    ORDERS_URN,
        "root_cause":     diagnosis.get("root_cause", ""),
        "missing_fields": detection.get("missing_fields", []),
        "type_changes":   detection.get("type_changes", []),
    }

    print("     Query diagnosis (matches what was just written):")
    print(f"       missing_fields : {loop_diagnosis['missing_fields']}")
    print(f"       type_changes   : {loop_diagnosis['type_changes']}")

    try:
        loop_recall = recall_similar_incidents(
            diagnosis=loop_diagnosis,
            top_k=5,
            min_similarity=0.60,   # lower threshold to catch the freshly written record
        )
    except Exception as e:
        fail(f"Recall (loop-close check) raised an exception: {e}")
        loop_recall = {"matches": [], "total_past_incidents_checked": 0}

    print(f"\n     past incidents checked : {loop_recall.get('total_past_incidents_checked', 0)}")
    print(f"     matches returned       : {len(loop_recall.get('matches', []))}")

    for m in loop_recall.get("matches", []):
        print(
            f"       {m.get('incident_id','?'):30s}  "
            f"score={m.get('similarity_score', 0.0):.4f}"
        )

    # The newly written incident should appear in recall results
    new_match = next(
        (m for m in loop_recall.get("matches", []) if m.get("incident_id") == incident_id),
        None,
    )

    if check(
        new_match is not None,
        f"Loop closed ✓ — new incident {incident_id} appears in recall results",
        f"Loop NOT closed — {incident_id} NOT found in recall results "
        f"(checked {loop_recall.get('total_past_incidents_checked', 0)} past incident(s))",
    ):
        check(
            new_match["similarity_score"] >= 0.60,
            f"Similarity score for new incident: {new_match['similarity_score']:.4f} ≥ 0.60",
            f"Similarity score too low: {new_match['similarity_score']:.4f} < 0.60",
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 8. Final summary
    # ──────────────────────────────────────────────────────────────────────────
    print()
    if _failures:
        print("=" * 65)
        print(f"  ❌ {len(_failures)} CHECK(S) FAILED:")
        for msg in _failures:
            print(f"     • {msg}")
        print("=" * 65)
        sys.exit(1)
    else:
        print("=" * 65)
        print("  ✅ ALL CHECKS PASSED — Memory-Writer + full loop verified!")
        print(f"     Incident written : {incident_id}")
        print(f"     Recall loop      : CLOSED")
        print("=" * 65)


if __name__ == "__main__":
    main()
