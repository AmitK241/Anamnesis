"""
backend/seed_demo_data.py
===========================
Seeds exactly 3 curated incidents into a clean Anamnesis/DataHub instance
to produce a reproducible, judge-ready demo narrative.

Story:
  Incident 1 — "The Hard Way" (no memory exists)
    orders table, order_status DROPPED
    Recall: 0 matches (memory is empty) -> Fixer reasons from scratch
    -> Memory-Writer stores it

  Incident 2 — "The Fast Way" (recall kicks in)
    customers table, customer_class DROPPED (same pattern: status/classification column)
    Recall: finds Incident 1 with score ~0.83 -> Fixer adapts prior fix
    -> Memory-Writer stores it

  Incident 3 — "The Range" (nuanced partial match)
    products table, min_price DROPPED + list_price type-changed (pricing, different pattern)
    Recall: finds Incidents 1 & 2 at lower score ~0.67-0.69
    -> Fixer adapts strategy accordingly

Verified embedding scores (before seeding, from scratch_probe_similarity.py):
  Inc1 vs Inc2 = 0.8293   <- strong "this is the same type of problem"
  Inc1 vs Inc3 = 0.6711   <- weaker "related but different"
  Inc2 vs Inc3 = 0.6857   <- weaker "related but different"

Real DataHub URNs (confirmed from scratch_audit.py):
  orders    : urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.orders,PROD)
  customers : urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.crm_db.customers,PROD)
  products  : urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.products,PROD)

Real schema fields (confirmed from DataHub schema audit):
  orders.order_status     : NUMBER (the column we're simulating as DROPPED)
  customers.customer_class: STRING (the column we're simulating as DROPPED)
  products.min_price      : NUMBER (DROPPED); products.list_price: NUMBER -> STRING (TYPE CHANGED)

Run AFTER running scratch_wipe_test_incidents.py:
    python -m backend.seed_demo_data

Output: 3 incident IDs + similarity scores for docs/demo_script.md
"""
import sys
import time
import io as _io

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from backend.agents.detector import SchemaDetector
from backend.agents.diagnoser import Diagnoser
from backend.agents.fixer import FixerAgent
from backend.agents.memory_writer import MemoryWriterAgent, _register_urn
from backend.agents.recall import MemoryRecallAgent

# ── Real DataHub URNs (confirmed from audit) ──────────────────────────────────
ORDERS_URN    = "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.orders,PROD)"
CUSTOMERS_URN = "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.crm_db.customers,PROD)"
PRODUCTS_URN  = "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.products,PROD)"
ORDER_ITEMS_URN = "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.order_items,PROD)"
PROMOTIONS_URN  = "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.promotions,PROD)"

# ── 7 curated detection payloads ──────────────────────────────────────────────
INCIDENT_CONFIGS = [
    {
        "label":    "Incident 1: orders (order_status DROPPED) - Baseline",
        "urn":      ORDERS_URN,
        "detection": {
            "dataset_urn":     ORDERS_URN,
            "has_break":       True,
            "severity":        "critical",
            "missing_fields":  ["order_status"],
            "type_changes":    [],
            "break_summary":   (
                "1 field(s) were removed: order_status was dropped from the orders "
                "table during a migration to a new state machine, breaking all downstream "
                "analytics pipelines relying on order status."
            ),
        },
    },
    {
        "label":    "Incident 2: customers (customer_class DROPPED) - Strong Match to #1",
        "urn":      CUSTOMERS_URN,
        "detection": {
            "dataset_urn":     CUSTOMERS_URN,
            "has_break":       True,
            "severity":        "critical",
            "missing_fields":  ["customer_class"],
            "type_changes":    [],
            "break_summary":   (
                "1 field(s) were removed: customer_class was dropped from the customers "
                "table following a CRM system upgrade that moved segmentation logic to a "
                "separate microservice."
            ),
        },
    },
    {
        "label":    "Incident 3: order_items (condition DROPPED) - Strong Match to #1/#2",
        "urn":      ORDER_ITEMS_URN,
        "detection": {
            "dataset_urn":     ORDER_ITEMS_URN,
            "has_break":       True,
            "severity":        "high",
            "missing_fields":  ["condition"],
            "type_changes":    [],
            "break_summary":   (
                "1 field(s) were removed: condition was dropped from the order_items "
                "table after the legacy inventory categorization system was deprecated."
            ),
        },
    },
    {
        "label":    "Incident 4: products (min_price DROPPED, list_price TYPE CHANGED) - Weaker Match",
        "urn":      PRODUCTS_URN,
        "detection": {
            "dataset_urn":     PRODUCTS_URN,
            "has_break":       True,
            "severity":        "medium",
            "missing_fields":  ["min_price"],
            "type_changes":    [{"field": "list_price", "was": "NUMBER", "now": "STRING"}],
            "break_summary":   (
                "1 field removed (min_price) and 1 type change (list_price: NUMBER -> STRING). "
                "Pricing-engine financial overhaul dropped minimum pricing column and changed "
                "list price to string type for multi-currency display, breaking numeric aggregation."
            ),
        },
    },
    {
        "label":    "Incident 5: promotions (promotion_name RENAMED) - Distinct Pattern",
        "urn":      PROMOTIONS_URN,
        "detection": {
            "dataset_urn":     PROMOTIONS_URN,
            "has_break":       True,
            "severity":        "medium",
            "missing_fields":  ["promotion_name"],
            "type_changes":    [],
            "break_summary":   (
                "1 field(s) were removed: promotion_name was dropped/renamed to promo_name "
                "in the promotions table, causing reporting views to fail."
            ),
        },
    },
    {
        "label":    "Incident 6: customers (credit_limit TYPE CHANGED) - Low Severity / Different Pattern",
        "urn":      CUSTOMERS_URN,
        "detection": {
            "dataset_urn":     CUSTOMERS_URN,
            "has_break":       True,
            "severity":        "low",
            "missing_fields":  [],
            "type_changes":    [{"field": "credit_limit", "was": "NUMBER", "now": "STRING"}],
            "break_summary":   (
                "1 type change (credit_limit: NUMBER -> STRING) in the customers table. "
                "A formatting update caused credit_limit to be returned as a formatted string."
            ),
        },
    },
    {
        "label":    "Incident 7: order_items (unit_price TYPE CHANGED) - Low Severity / Matches #6",
        "urn":      ORDER_ITEMS_URN,
        "detection": {
            "dataset_urn":     ORDER_ITEMS_URN,
            "has_break":       True,
            "severity":        "low",
            "missing_fields":  [],
            "type_changes":    [{"field": "unit_price", "was": "NUMBER", "now": "STRING"}],
            "break_summary":   (
                "1 type change (unit_price: NUMBER -> STRING) in the order_items table. "
                "Upstream parsing error caused the unit_price field to be cast to a string type."
            ),
        },
    },
]


def run_incident(cfg: dict, recall_agent: MemoryRecallAgent) -> dict:
    """Run stages 2-5 (Diagnose → Recall → Fix → Write) for a pre-built detection."""
    label    = cfg["label"]
    urn      = cfg["urn"]
    detection = cfg["detection"]

    print(f"\n{'=' * 65}")
    print(f"  SEEDING: {label}")
    print(f"{'=' * 65}")
    print(f"  Dataset  : {urn.split(',')[1]}")
    print(f"  Missing  : {detection['missing_fields']}")
    print(f"  TypeChg  : {detection['type_changes']}")

    # Stage 2: Diagnose
    print("\n  [2] Diagnosing...")
    diagnoser = Diagnoser()
    diagnosis = diagnoser.diagnose(detection)
    # Propagate fields if diagnoser doesn't echo them
    if "missing_fields" not in diagnosis:
        diagnosis["missing_fields"] = detection["missing_fields"]
    if "type_changes" not in diagnosis:
        diagnosis["type_changes"] = detection["type_changes"]
    print(f"      root_cause: {str(diagnosis.get('root_cause',''))[:80]}...")
    print(f"      confidence: {diagnosis.get('diagnosis_confidence')}")

    # Stage 3: Recall — BEFORE registering the new URN so we don't recall ourselves
    print("\n  [3] Recalling similar past incidents (min_similarity=0.60)...")
    recall_result = recall_agent.recall_similar_incidents(
        diagnosis=diagnosis,
        top_k=5,
        min_similarity=0.60,
    )
    n_matches = len(recall_result.get("matches", []))
    print(f"      Checked  : {recall_result.get('total_past_incidents_checked', 0)} past incident(s)")
    print(f"      Matches  : {n_matches}")
    for m in recall_result.get("matches", []):
        print(f"        -> {m.get('incident_id'):30s}  score={m.get('similarity_score', 0):.4f}")

    # Stage 4: Fix
    print("\n  [4] Generating fix (Groq LLM)...")
    fixer = FixerAgent()
    try:
        fix_result = fixer.generate_fix(diagnosis=diagnosis, recall_result=recall_result)
    except RuntimeError as exc:
        print(f"      WARNING: Fixer failed ({exc}) — using placeholder fix")
        fix_result = {
            "suggested_fix": f"# Placeholder fix for {label}",
            "mode": "fallback",
            "estimated_time_saved_minutes": 30,
        }
    print(f"      mode: {fix_result.get('mode')}  time_saved: {fix_result.get('estimated_time_saved_minutes')}min")
    print(f"      fix preview: {str(fix_result.get('suggested_fix',''))[:80]}...")

    # Stage 5: Write-memory
    print("\n  [5] Writing to DataHub memory...")
    writer = MemoryWriterAgent()
    write_result = writer.write_incident_memory(
        detection=detection,
        diagnosis=diagnosis,
        recall_result=recall_result,
        fix_result=fix_result,
    )
    incident_id   = write_result.get("incident_id", "?")
    verification  = write_result.get("verification", "?")
    success       = write_result.get("success", False)

    if success:
        print(f"\n  ✅ Written: {incident_id}")
        print(f"     verification: {verification}")
    else:
        print(f"\n  ❌ Write FAILED: {verification}")

    return {
        "label":         label,
        "incident_id":   incident_id,
        "urn":           urn,
        "detection":     detection,
        "recall_matches": recall_result.get("matches", []),
        "write_result":  write_result,
    }


def main():
    import backend.agents.recall as _recall_mod

    print("=" * 65)
    print("  seed_demo_data.py — Demo Data Seeder")
    print("  Seeding 3 curated incidents for the Anamnesis demo")
    print("=" * 65)

    recall_agent = MemoryRecallAgent()
    results = []

    for i, cfg in enumerate(INCIDENT_CONFIGS):
        result = run_incident(cfg, recall_agent)
        results.append(result)

        # After writing, register the new URN so the NEXT incident can recall it
        _register_urn(cfg["urn"])
        # Reset the recall agent singleton so it picks up the new env var
        _recall_mod._agent = None
        recall_agent = MemoryRecallAgent()

        if i < len(INCIDENT_CONFIGS) - 1:
            print("\n  Waiting 2 seconds between incidents...")
            time.sleep(2)

    # ── Final summary ─────────────────────────────────────────────────────────
    print("\n\n" + "=" * 65)
    print("  SEEDING COMPLETE — Summary")
    print("=" * 65)

    for i, r in enumerate(results):
        inc_id = r["incident_id"]
        urn    = r["urn"].split(",")[1]
        matches = r["recall_matches"]
        print(f"\n  Incident {i+1}: {r['label']}")
        print(f"    ID        : {inc_id}")
        print(f"    Dataset   : {urn}")
        if matches:
            for m in matches:
                print(f"    Recall    : {m.get('incident_id')} @ score={m.get('similarity_score',0):.4f}")
        else:
            print(f"    Recall    : (no matches — expected for incident {i+1})")

    print()
    print("  Results for docs/demo_script.md:")
    for i, r in enumerate(results):
        print(f"  INC{i+1}_ID   = {r['incident_id']}")
        if r["recall_matches"]:
            top = r["recall_matches"][0]
            print(f"  INC{i+1}_SCORE = {top.get('similarity_score', 0):.4f}  (matched {top.get('incident_id')})")
        else:
            print(f"  INC{i+1}_SCORE = n/a (no recall match)")

    print()
    all_written = all(r["write_result"].get("success") for r in results)
    if all_written:
        print("  ✅ ALL 3 INCIDENTS WRITTEN SUCCESSFULLY")
    else:
        failed = [r["label"] for r in results if not r["write_result"].get("success")]
        print(f"  ❌ FAILURES: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    main()
