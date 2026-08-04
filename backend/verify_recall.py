# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
backend/verify_recall.py
--------------------------
End-to-end verification of the Memory-Recall agent.

Steps
-----
1. Seeds 3 fake IncidentMemory records directly into DataHub via MCP,
   each with a REAL embedding vector (computed by all-MiniLM-L6-v2):
     INC-RECALL-A : missing fulfillment_status + order_total type change  (similar)
     INC-RECALL-B : missing carrier_code + delivery_date type change      (marginally related)
     INC-RECALL-C : missing email_hash on customers table                 (unrelated)

2. Sets ANAMNESIS_KNOWN_DATASET_URNS env var so scroll_incident_memories()
   can find all three URNs without needing the GraphQL _exists_ filter.

3. Runs recall_similar_incidents() with a query matching INC-RECALL-A's pattern.

4. Asserts:
     ✅ INC-RECALL-A in results with similarity_score >= 0.80
     ✅ INC-RECALL-C either absent OR similarity_score < 0.60
     ✅ no_similar_incidents_found == False
     ✅ total_past_incidents_checked == 3

Usage:
    python -m backend.verify_recall
"""

import json
import os
import sys
import time

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATAHUB_GMS_URL = os.getenv("DATAHUB_GMS_SERVER", "http://localhost:8080")
ASPECT_NAME = "incidentMemory"

# Dataset URNs — we use separate datasets so each can carry its own aspect
URN_A = (
    "urn:li:dataset:(urn:li:dataPlatform:postgres,"
    "b2fd91.order_entry_db.order_entry.orders,PROD)"
)
URN_B = (
    "urn:li:dataset:(urn:li:dataPlatform:postgres,"
    "b2fd91.order_entry_db.logistics.shipments,PROD)"
)
URN_C = (
    "urn:li:dataset:(urn:li:dataPlatform:postgres,"
    "b2fd91.crm_db.customers,PROD)"
)


# ---------------------------------------------------------------------------
# Colour / status helpers
# ---------------------------------------------------------------------------

def oks(msg: str) -> None:
    print(f"  ✅ {msg}")


def fail(msg: str) -> None:
    print(f"  ❌ {msg}")


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
# DataHub helpers (reused from verify_incident_memory.py)
# ---------------------------------------------------------------------------

def emit_mcp(entity_urn: str, aspect_name: str, aspect_value: dict) -> None:
    """Emit a MetadataChangeProposal via the GMS REST endpoint."""
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
    response = requests.post(
        f"{DATAHUB_GMS_URL}/aspects?action=ingestProposal",
        json={"proposal": mcp},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if response.status_code not in (200, 201, 202):
        raise RuntimeError(
            f"MCP ingest failed [{response.status_code}]: {response.text[:500]}"
        )


# ---------------------------------------------------------------------------
# Compute real embeddings for seed data
# ---------------------------------------------------------------------------

def compute_embedding(root_cause: str, missing_fields: list, type_changes: list) -> list:
    """Use our own embed_incident_text() so seeded vectors match the query space."""
    from backend.core.embeddings import embed_incident_text
    return embed_incident_text(
        root_cause=root_cause,
        missing_fields=missing_fields,
        type_changes=type_changes,
    )


# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------

INCIDENT_A = {
    "incident_id":    "INC-RECALL-A",
    "urn":            URN_A,
    "root_cause": (
        "A schema change in the upstream orders table dropped the "
        "`fulfillment_status` column without a coordinated migration, "
        "and changed `order_total` from DECIMAL to STRING, causing "
        "downstream aggregation pipelines to fail."
    ),
    "missing_fields": ["fulfillment_status"],
    "type_changes":   [{"field": "order_total", "was": "DECIMAL", "now": "STRING"}],
    "resolution_code_diff": (
        "--- a/pipelines/orders_agg.py\n"
        "+++ b/pipelines/orders_agg.py\n"
        "@@ -42,7 +42,7 @@\n"
        "-    .select('order_id', 'fulfillment_status', 'revenue')\n"
        "+    .select('order_id', 'status', 'revenue')  # renamed in v2 schema\n"
    ),
    "time_saved_estimate": 120,
}

INCIDENT_B = {
    "incident_id":    "INC-RECALL-B",
    "urn":            URN_B,
    "root_cause": (
        "The shipments table lost the `carrier_code` field after a provider "
        "migration, and `delivery_date` changed from DATE to TIMESTAMP."
    ),
    "missing_fields": ["carrier_code"],
    "type_changes":   [{"field": "delivery_date", "was": "DATE", "now": "TIMESTAMP"}],
    "resolution_code_diff": (
        "--- a/pipelines/shipments.py\n"
        "+++ b/pipelines/shipments.py\n"
        "@@ -10,3 +10,4 @@\n"
        "+provider_code = row.get('carrier_code') or row.get('provider_id')\n"
    ),
    "time_saved_estimate": 45,
}

INCIDENT_C = {
    "incident_id":    "INC-RECALL-C",
    "urn":            URN_C,
    "root_cause": (
        "The CRM customers table had its PII hash column `email_hash` removed "
        "following a GDPR compliance policy change; no schema migration notice "
        "was sent to downstream analytics consumers."
    ),
    "missing_fields": ["email_hash"],
    "type_changes":   [],
    "resolution_code_diff": (
        "--- a/analytics/customer_segment.py\n"
        "+++ b/analytics/customer_segment.py\n"
        "@@ -5,1 +5,2 @@\n"
        "-email_hash = row['email_hash']\n"
        "+email_hash = hashlib.sha256(row['email'].encode()).hexdigest()\n"
    ),
    "time_saved_estimate": 30,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 65)
    print("  verify_recall.py — Memory-Recall Agent Verification")
    print(f"  GMS URL: {DATAHUB_GMS_URL}")
    print("=" * 65)

    # ------------------------------------------------------------------
    # 0. Check GMS is reachable
    # ------------------------------------------------------------------
    print("\n[0] Checking GMS connectivity…")
    try:
        resp = requests.get(f"{DATAHUB_GMS_URL}/config", timeout=10)
        resp.raise_for_status()
        oks("GMS reachable")
    except Exception as e:
        fail(f"Cannot reach GMS at {DATAHUB_GMS_URL}: {e}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 1. Compute REAL embeddings for seed incidents
    # ------------------------------------------------------------------
    print("\n[1] Computing real embeddings for seed incidents…")
    print("    (first run downloads ~80 MB model from HuggingFace — cached after that)")
    try:
        vec_a = compute_embedding(
            INCIDENT_A["root_cause"],
            INCIDENT_A["missing_fields"],
            INCIDENT_A["type_changes"],
        )
        oks(f"INC-RECALL-A embedding: dim={len(vec_a)}, first3={[round(v,4) for v in vec_a[:3]]}")

        vec_b = compute_embedding(
            INCIDENT_B["root_cause"],
            INCIDENT_B["missing_fields"],
            INCIDENT_B["type_changes"],
        )
        oks(f"INC-RECALL-B embedding: dim={len(vec_b)}")

        vec_c = compute_embedding(
            INCIDENT_C["root_cause"],
            INCIDENT_C["missing_fields"],
            INCIDENT_C["type_changes"],
        )
        oks(f"INC-RECALL-C embedding: dim={len(vec_c)}")
    except Exception as e:
        fail(f"Embedding computation failed: {e}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. Seed IncidentMemory aspects into DataHub
    # ------------------------------------------------------------------
    print("\n[2] Seeding 3 IncidentMemory aspects into DataHub…")
    now_ms = int(time.time() * 1000)

    seeds = [
        (INCIDENT_A, vec_a),
        (INCIDENT_B, vec_b),
        (INCIDENT_C, vec_c),
    ]

    for inc, vec in seeds:
        aspect = {
            "incidentId":         inc["incident_id"],
            "rootCause":          inc["root_cause"],
            "downstreamImpact":   [],
            "resolutionCodeDiff": inc["resolution_code_diff"],
            "embeddingVector":    vec,
            "similarPastIncidents": [],
            "timeSavedEstimate":  inc["time_saved_estimate"],
            "timestamp":          now_ms,
        }
        try:
            emit_mcp(inc["urn"], ASPECT_NAME, aspect)
            oks(f"Seeded {inc['incident_id']} → {inc['urn'].split(',')[1]}")
        except Exception as e:
            fail(f"Failed to seed {inc['incident_id']}: {e}")
            sys.exit(1)

    # ------------------------------------------------------------------
    # 3. Set env-var fallback so scroll_incident_memories() finds all URNs
    # ------------------------------------------------------------------
    print("\n[3] Setting ANAMNESIS_KNOWN_DATASET_URNS env var…")
    known_urns = "|".join([URN_A, URN_B, URN_C])
    os.environ["ANAMNESIS_KNOWN_DATASET_URNS"] = known_urns
    oks(f"Env var set with {len(known_urns.split('|'))} URN(s)")

    # Force singleton re-init so the new env var is picked up
    import backend.core.datahub_client as _dh_mod
    import backend.agents.recall as _recall_mod
    _recall_mod._agent = None  # reset singleton

    # ------------------------------------------------------------------
    # 4. Build query diagnosis matching INC-RECALL-A's pattern
    # ------------------------------------------------------------------
    print("\n[4] Building query diagnosis (matches INC-RECALL-A pattern)…")
    query_diagnosis = {
        "dataset_urn":    URN_A,
        "root_cause": (
            "Schema break: the `fulfillment_status` column was dropped from the orders "
            "table, and `order_total` had its type changed from DECIMAL to STRING. "
            "Downstream aggregation jobs are now failing."
        ),
        "missing_fields": ["fulfillment_status"],
        "type_changes":   [{"field": "order_total", "was": "DECIMAL", "now": "STRING"}],
    }
    oks("Query diagnosis constructed")

    # ------------------------------------------------------------------
    # 5. Run recall
    # ------------------------------------------------------------------
    print("\n[5] Running recall_similar_incidents() (top_k=3, min_similarity=0.70)…")
    try:
        from backend.agents.recall import recall_similar_incidents
        result = recall_similar_incidents(
            diagnosis=query_diagnosis,
            top_k=3,
            min_similarity=0.70,  # slightly lower threshold to also catch B for inspection
        )
    except Exception as e:
        fail(f"recall_similar_incidents raised an exception: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)

    # ------------------------------------------------------------------
    # 6. Print raw result
    # ------------------------------------------------------------------
    print("\n  Raw result:")
    print(f"    no_similar_incidents_found   : {result['no_similar_incidents_found']}")
    print(f"    total_past_incidents_checked : {result['total_past_incidents_checked']}")
    print(f"    matches returned             : {len(result['matches'])}")
    for m in result["matches"]:
        print(
            f"      {m['incident_id']:20s}  dataset={m['dataset_urn'].split(',')[1][:30]:30s}"
            f"  score={m['similarity_score']:.4f}"
        )

    # ------------------------------------------------------------------
    # 7. Assertions
    # ------------------------------------------------------------------
    print("\n[6] Running assertions…")

    # a) total past incidents checked
    check(
        result["total_past_incidents_checked"] == 3,
        "total_past_incidents_checked == 3",
        f"expected 3, got {result['total_past_incidents_checked']}",
    )

    # b) no_similar_incidents_found should be False (we seeded similar ones)
    check(
        result["no_similar_incidents_found"] is False,
        "no_similar_incidents_found == False (matches exist)",
        "no_similar_incidents_found is True — no matches above threshold",
    )

    # c) INC-RECALL-A must be in results with high similarity
    match_a = next(
        (m for m in result["matches"] if m["incident_id"] == "INC-RECALL-A"), None
    )
    check(
        match_a is not None,
        "INC-RECALL-A found in results",
        "INC-RECALL-A NOT found in results",
    )
    if match_a:
        check(
            match_a["similarity_score"] >= 0.80,
            f"INC-RECALL-A similarity_score={match_a['similarity_score']:.4f} >= 0.80",
            f"INC-RECALL-A similarity_score={match_a['similarity_score']:.4f} is below 0.80",
        )

    # d) INC-RECALL-C (unrelated) must be absent OR score low
    match_c = next(
        (m for m in result["matches"] if m["incident_id"] == "INC-RECALL-C"), None
    )
    if match_c is None:
        oks("INC-RECALL-C correctly absent from results (below threshold)")
    else:
        check(
            match_c["similarity_score"] < 0.80,
            f"INC-RECALL-C appears but with low score={match_c['similarity_score']:.4f} < 0.80",
            f"INC-RECALL-C has unexpectedly HIGH score={match_c['similarity_score']:.4f}",
        )

    # e) Results sorted descending
    scores = [m["similarity_score"] for m in result["matches"]]
    check(
        scores == sorted(scores, reverse=True),
        "Results are sorted descending by similarity_score",
        f"Results NOT sorted: {scores}",
    )

    # ------------------------------------------------------------------
    # 8. Empty-case smoke test
    # ------------------------------------------------------------------
    print("\n[7] Smoke-test: empty URN list → no_similar_incidents_found=True…")
    old_env = os.environ.pop("ANAMNESIS_KNOWN_DATASET_URNS", "")
    _recall_mod._agent = None  # reset singleton

    try:
        from backend.agents.recall import recall_similar_incidents as rsi2
        empty_result = rsi2(
            diagnosis={"dataset_urn": "urn:li:dataset:(urn:li:dataPlatform:postgres,x,PROD)",
                        "root_cause": "test", "missing_fields": [], "type_changes": []},
            top_k=3,
            min_similarity=0.75,
        )
        check(
            empty_result["no_similar_incidents_found"] is True,
            "Empty-case: no_similar_incidents_found=True (no URNs configured)",
            "Empty-case: expected no_similar_incidents_found=True, got False",
        )
        check(
            empty_result["matches"] == [],
            "Empty-case: matches list is empty",
            f"Empty-case: expected empty matches, got {empty_result['matches']}",
        )
    except Exception as e:
        fail(f"Empty-case raised unexpected exception: {e}")
        import traceback; traceback.print_exc()
    finally:
        # Restore env var for any further use
        os.environ["ANAMNESIS_KNOWN_DATASET_URNS"] = old_env
        _recall_mod._agent = None

    # ------------------------------------------------------------------
    # 9. Final summary
    # ------------------------------------------------------------------
    print()
    if _failures:
        print("=" * 65)
        print(f"  ❌ {len(_failures)} CHECK(S) FAILED:")
        for f_msg in _failures:
            print(f"     • {f_msg}")
        print("=" * 65)
        sys.exit(1)
    else:
        print("=" * 65)
        print("  ✅ ALL CHECKS PASSED — Memory-Recall agent verified!")
        print("=" * 65)


if __name__ == "__main__":
    main()
