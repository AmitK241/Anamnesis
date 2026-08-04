# -*- coding: utf-8 -*-
#!/usr/bin/env python3
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
"""
backend/verify_fixer.py
------------------------
End-to-end verification of the Fixer agent.

Scenarios
---------
A. High-similarity recall_result (reuses the INC-RECALL-A seed pattern from
   verify_recall.py) — asserts:
     * mode == "adapted"
     * based_on_incident_id == "INC-RECALL-A"
     * suggested_fix is non-empty and contains meaningful content
     * estimated_time_saved_minutes is set (INC-RECALL-A has 120 minutes)
     * confidence_note mentions the incident id

B. Empty recall_result (no_similar_incidents_found=True) — asserts:
     * mode == "generated_fresh"
     * based_on_incident_id is None
     * suggested_fix is non-empty and relevant (mentions known field names)
     * estimated_time_saved_minutes is None

Prerequisites
-------------
* GROQ_API_KEY must be set in d:\\Anamnesis\\.env (or environment).
* No DataHub connectivity required — recall_result is supplied directly.

Usage:
    python -m backend.verify_fixer
"""

import os

# ---------------------------------------------------------------------------
# Status helpers (same pattern as verify_recall.py)
# ---------------------------------------------------------------------------

def oks(msg: str) -> None:
    print(f"  \u2705 {msg}")


def fail(msg: str) -> None:
    print(f"  \u274c {msg}")


_failures: list = []


def check(condition: bool, msg_pass: str, msg_fail: str) -> bool:
    if condition:
        oks(msg_pass)
        return True
    else:
        fail(msg_fail)
        _failures.append(msg_fail)
        return False


# ---------------------------------------------------------------------------
# Shared fixtures  (mirror INC-RECALL-A data from verify_recall.py)
# ---------------------------------------------------------------------------

# The diagnosis that matches INC-RECALL-A's root-cause pattern
DIAGNOSIS_ORDERS = {
    "dataset_urn": (
        "urn:li:dataset:(urn:li:dataPlatform:postgres,"
        "b2fd91.order_entry_db.order_entry.orders,PROD)"
    ),
    "root_cause": (
        "Schema break: the `fulfillment_status` column was dropped from the orders "
        "table, and `order_total` had its type changed from DECIMAL to STRING. "
        "Downstream aggregation jobs are now failing."
    ),
    "missing_fields": ["fulfillment_status"],
    "type_changes":   [{"field": "order_total", "was": "DECIMAL", "now": "STRING"}],
    "downstream_impact": [
        "urn:li:dataset:(..,revenue_dashboard)",
        "urn:li:dataset:(..,orders_monthly)",
    ],
    "confidence": "high",
}

# A recall_result with INC-RECALL-A at similarity_score=0.92 (above threshold)
RECALL_HIGH_SIMILARITY = {
    "query_diagnosis_urn": DIAGNOSIS_ORDERS["dataset_urn"],
    "matches": [
        {
            "incident_id":          "INC-RECALL-A",
            "dataset_urn":          DIAGNOSIS_ORDERS["dataset_urn"],
            "root_cause": (
                "A schema change in the upstream orders table dropped the "
                "`fulfillment_status` column without a coordinated migration, "
                "and changed `order_total` from DECIMAL to STRING, causing "
                "downstream aggregation pipelines to fail."
            ),
            "resolution_code_diff": (
                "--- a/pipelines/orders_agg.py\n"
                "+++ b/pipelines/orders_agg.py\n"
                "@@ -42,7 +42,7 @@\n"
                "-    .select('order_id', 'fulfillment_status', 'revenue')\n"
                "+    .select('order_id', 'status', 'revenue')  # renamed in v2 schema\n"
            ),
            "time_saved_estimate":  120,
            "downstream_impact":    [],
            "similarity_score":     0.92,   # well above the 0.85 threshold
        }
    ],
    "no_similar_incidents_found": False,
    "total_past_incidents_checked": 3,
    "top_k": 3,
    "min_similarity": 0.75,
}

# A recall_result with no qualifying matches
RECALL_NO_MATCHES = {
    "query_diagnosis_urn": "urn:li:dataset:(urn:li:dataPlatform:postgres,novel_table,PROD)",
    "matches": [],
    "no_similar_incidents_found": True,
    "total_past_incidents_checked": 0,
    "top_k": 3,
    "min_similarity": 0.75,
}

# A fresh diagnosis with no matching historical incident
DIAGNOSIS_NOVEL = {
    "dataset_urn": "urn:li:dataset:(urn:li:dataPlatform:postgres,novel_table,PROD)",
    "root_cause": (
        "The `payment_method` column was unexpectedly dropped from the transactions "
        "table and `transaction_amount` changed from NUMERIC to VARCHAR, breaking "
        "the fraud-detection pipeline and three downstream BI dashboards."
    ),
    "missing_fields": ["payment_method"],
    "type_changes":   [{"field": "transaction_amount", "was": "NUMERIC", "now": "VARCHAR"}],
    "downstream_impact": [
        "fraud_detection_pipeline",
        "bi_dashboard_revenue",
        "bi_dashboard_compliance",
    ],
    "confidence": "medium",
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 65)
    print("  verify_fixer.py -- Fixer Agent Verification")
    print("=" * 65)

    # -----------------------------------------------------------------------
    # 0. Import the agent (also loads .env)
    # -----------------------------------------------------------------------
    print("\n[0] Importing FixerAgent…")
    try:
        from backend.agents.fixer import FixerAgent, ADAPT_THRESHOLD
        agent = FixerAgent()
        oks(f"FixerAgent imported (adapt threshold = {ADAPT_THRESHOLD})")
    except Exception as exc:
        fail(f"Could not import FixerAgent: {exc}")
        import traceback; traceback.print_exc()
        sys.exit(1)

    # Sanity-check: GROQ_API_KEY must be present before we spend time on tests
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        fail(
            "GROQ_API_KEY is not set. "
            r"Add it to d:\Anamnesis\.env as: GROQ_API_KEY=gsk_..."
        )
        sys.exit(1)
    oks(f"GROQ_API_KEY is set (len={len(api_key)})")

    # =======================================================================
    # SCENARIO A — High-similarity recall (adapted mode)
    # =======================================================================
    print("\n" + "=" * 65)
    print("  SCENARIO A: High-similarity recall -> mode='adapted'")
    print("=" * 65)

    print(
        f"\n  Recall result has 1 match: INC-RECALL-A  "
        f"similarity={RECALL_HIGH_SIMILARITY['matches'][0]['similarity_score']}"
    )
    print(f"  ADAPT_THRESHOLD = {ADAPT_THRESHOLD}")
    print("\n  Calling generate_fix()…")

    try:
        result_a = agent.generate_fix(
            diagnosis=DIAGNOSIS_ORDERS,
            recall_result=RECALL_HIGH_SIMILARITY,
        )
    except Exception as exc:
        fail(f"generate_fix raised an exception: {exc}")
        import traceback; traceback.print_exc()
        sys.exit(1)

    print("\n  --- Raw result (Scenario A) ---")
    print(f"  mode                         : {result_a.get('mode')}")
    print(f"  based_on_incident_id         : {result_a.get('based_on_incident_id')}")
    print(f"  estimated_time_saved_minutes : {result_a.get('estimated_time_saved_minutes')}")
    print(f"  confidence_note              : {result_a.get('confidence_note', '')[:80]}…")
    print(f"  suggested_fix (first 200ch)  : {result_a.get('suggested_fix', '')[:200]}…")

    print("\n  [A] Assertions:")

    check(
        result_a.get("mode") == "adapted",
        "mode == 'adapted'",
        f"mode is '{result_a.get('mode')}', expected 'adapted'",
    )

    check(
        result_a.get("based_on_incident_id") == "INC-RECALL-A",
        "based_on_incident_id == 'INC-RECALL-A'",
        f"based_on_incident_id = {result_a.get('based_on_incident_id')!r}",
    )

    check(
        isinstance(result_a.get("suggested_fix"), str) and len(result_a.get("suggested_fix", "")) > 20,
        f"suggested_fix is non-empty str (len={len(result_a.get('suggested_fix', ''))})",
        "suggested_fix is empty or missing",
    )

    # The LLM should reference at least one known field name in its output
    fix_text_a = result_a.get("suggested_fix", "").lower()
    relevant_keywords = ["fulfillment_status", "order_total", "decimal", "string", "status", "orders"]
    found_keywords = [kw for kw in relevant_keywords if kw in fix_text_a]
    check(
        len(found_keywords) >= 1,
        f"suggested_fix references relevant field/term(s): {found_keywords}",
        f"suggested_fix does not mention any of: {relevant_keywords}",
    )

    check(
        result_a.get("estimated_time_saved_minutes") == 120,
        "estimated_time_saved_minutes == 120 (from INC-RECALL-A)",
        f"estimated_time_saved_minutes = {result_a.get('estimated_time_saved_minutes')!r}",
    )

    confidence_note_a = result_a.get("confidence_note", "")
    check(
        "INC-RECALL-A" in confidence_note_a,
        "confidence_note mentions 'INC-RECALL-A'",
        f"confidence_note does not mention incident id: {confidence_note_a[:80]!r}",
    )

    check(
        isinstance(result_a.get("confidence_note"), str) and len(confidence_note_a) > 10,
        "confidence_note is a non-empty string",
        "confidence_note is empty or missing",
    )

    # =======================================================================
    # SCENARIO B — No matches (generated_fresh mode)
    # =======================================================================
    print("\n" + "=" * 65)
    print("  SCENARIO B: Empty recall result -> mode='generated_fresh'")
    print("=" * 65)

    print(
        f"\n  Recall result: no_similar_incidents_found="
        f"{RECALL_NO_MATCHES['no_similar_incidents_found']}, "
        f"matches={RECALL_NO_MATCHES['matches']}"
    )
    print("\n  Calling generate_fix()…")

    try:
        result_b = agent.generate_fix(
            diagnosis=DIAGNOSIS_NOVEL,
            recall_result=RECALL_NO_MATCHES,
        )
    except Exception as exc:
        fail(f"generate_fix raised an exception: {exc}")
        import traceback; traceback.print_exc()
        sys.exit(1)

    print("\n  --- Raw result (Scenario B) ---")
    print(f"  mode                         : {result_b.get('mode')}")
    print(f"  based_on_incident_id         : {result_b.get('based_on_incident_id')}")
    print(f"  estimated_time_saved_minutes : {result_b.get('estimated_time_saved_minutes')}")
    print(f"  confidence_note              : {result_b.get('confidence_note', '')[:80]}…")
    print(f"  suggested_fix (first 200ch)  : {result_b.get('suggested_fix', '')[:200]}…")

    print("\n  [B] Assertions:")

    check(
        result_b.get("mode") == "generated_fresh",
        "mode == 'generated_fresh'",
        f"mode is '{result_b.get('mode')}', expected 'generated_fresh'",
    )

    check(
        result_b.get("based_on_incident_id") is None,
        "based_on_incident_id is None",
        f"based_on_incident_id = {result_b.get('based_on_incident_id')!r}, expected None",
    )

    check(
        isinstance(result_b.get("suggested_fix"), str) and len(result_b.get("suggested_fix", "")) > 20,
        f"suggested_fix is non-empty str (len={len(result_b.get('suggested_fix', ''))})",
        "suggested_fix is empty or missing",
    )

    # The fresh fix should reference the diagnosis context
    fix_text_b = result_b.get("suggested_fix", "").lower()
    relevant_keywords_b = ["payment_method", "transaction_amount", "numeric", "varchar", "fraud", "transactions"]
    found_keywords_b = [kw for kw in relevant_keywords_b if kw in fix_text_b]
    check(
        len(found_keywords_b) >= 1,
        f"suggested_fix references relevant field/term(s): {found_keywords_b}",
        f"suggested_fix does not mention any of: {relevant_keywords_b}",
    )

    check(
        result_b.get("estimated_time_saved_minutes") is None,
        "estimated_time_saved_minutes is None (no historical estimate available)",
        f"estimated_time_saved_minutes = {result_b.get('estimated_time_saved_minutes')!r}, expected None",
    )

    confidence_note_b = result_b.get("confidence_note", "")
    check(
        isinstance(confidence_note_b, str) and len(confidence_note_b) > 10,
        "confidence_note is a non-empty string",
        "confidence_note is empty or missing",
    )

    # Should NOT mention a past incident id
    check(
        "INC-RECALL" not in confidence_note_b,
        "confidence_note does NOT reference a past incident id (correct for fresh mode)",
        f"confidence_note unexpectedly references a past incident: {confidence_note_b[:80]!r}",
    )

    # =======================================================================
    # SCENARIO C — Below-threshold match (should still be generated_fresh)
    # =======================================================================
    print("\n" + "=" * 65)
    print("  SCENARIO C: Below-threshold match (0.60) -> mode='generated_fresh'")
    print("=" * 65)

    recall_low_similarity = {
        "query_diagnosis_urn": DIAGNOSIS_NOVEL["dataset_urn"],
        "matches": [
            {
                "incident_id":          "INC-RECALL-B",
                "dataset_urn":          "urn:li:dataset:(urn:li:dataPlatform:postgres,shipments,PROD)",
                "root_cause":           "Carrier code dropped from shipments.",
                "resolution_code_diff": "--- a/shipments.py\n+++ b/shipments.py\n",
                "time_saved_estimate":  45,
                "downstream_impact":    [],
                "similarity_score":     0.60,   # below 0.85 threshold
            }
        ],
        "no_similar_incidents_found": False,
        "total_past_incidents_checked": 3,
        "top_k": 3,
        "min_similarity": 0.55,
    }

    print(f"\n  Best match similarity_score=0.60 < ADAPT_THRESHOLD={ADAPT_THRESHOLD}")
    print("  Calling generate_fix()…")

    try:
        result_c = agent.generate_fix(
            diagnosis=DIAGNOSIS_NOVEL,
            recall_result=recall_low_similarity,
        )
    except Exception as exc:
        fail(f"generate_fix raised an exception: {exc}")
        import traceback; traceback.print_exc()
        sys.exit(1)

    print(f"  mode = {result_c.get('mode')!r}")
    print("\n  [C] Assertions:")

    check(
        result_c.get("mode") == "generated_fresh",
        "mode == 'generated_fresh' (low-similarity match ignored)",
        f"mode is '{result_c.get('mode')}', should be 'generated_fresh' since score < threshold",
    )
    check(
        result_c.get("based_on_incident_id") is None,
        "based_on_incident_id is None (low-similarity match not used)",
        f"based_on_incident_id = {result_c.get('based_on_incident_id')!r}",
    )

    # =======================================================================
    # Final summary
    # =======================================================================
    print()
    if _failures:
        print("=" * 65)
        print(f"  \u274c {len(_failures)} CHECK(S) FAILED:")
        for f_msg in _failures:
            print(f"     * {f_msg}")
        print("=" * 65)
        sys.exit(1)
    else:
        print("=" * 65)
        print("  \u2705 ALL CHECKS PASSED -- Fixer agent verified!")
        print("=" * 65)


if __name__ == "__main__":
    main()
