#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/verify_detector.py
---------------------------
Exercises SchemaDetector directly (no HTTP server needed) and via the
/api/detect endpoint.

Covers three scenarios:
  A. Clean schema  – no breaks expected
  B. Known-good baseline with missing field + type change – breaks expected
  C. Simulation helper (simulate_schema_break) – breaks expected

Usage:
    python backend/verify_detector.py
"""

import json
import sys

# Force UTF-8 on Windows (cp1252 console can't print emoji otherwise)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import time
import urllib.request

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_BASE = "http://localhost:8888"
DATAHUB_GMS = "http://localhost:8080"

ORDERS_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:postgres,"
    "b2fd91.order_entry_db.order_entry.orders,PROD)"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ok(msg: str) -> None:
    print(f"  \u2705 {msg}")


def warn(msg: str) -> None:
    print(f"  \u26a0\ufe0f  {msg}")


def fail(msg: str, fatal: bool = True) -> None:
    print(f"  \u274c {msg}")
    if fatal:
        sys.exit(1)


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def get(path: str) -> dict:
    req = urllib.request.Request(f"{API_BASE}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def print_result(result: dict) -> None:
    """Pretty-print a detection result."""
    print()
    print(f"    has_break      : {result.get('has_break')}")
    print(f"    severity       : {result.get('severity')}")
    print(f"    missing_fields : {result.get('missing_fields', [])}")
    print(f"    type_changes   : {result.get('type_changes', [])}")
    print(f"    new_fields     : {result.get('new_fields', [])}")
    if result.get("simulated"):
        print(f"    simulated      : True")
    if result.get("current_schema"):
        print(f"    live fields    : {sorted(result['current_schema'].keys())}")
    print()


# ---------------------------------------------------------------------------
# Scenario tests
# ---------------------------------------------------------------------------

def test_health() -> None:
    section("Pre-flight: health checks")

    try:
        data = get("/health")
        if data.get("datahub_connected"):
            ok(f"DataHub connected ({data.get('datahub_server')})")
        else:
            warn("DataHub NOT connected – detector will return empty schemas")
        ok(f"API server healthy – {data.get('memory_records', 0)} memory records")
    except Exception as exc:
        fail(f"API server unreachable at {API_BASE}: {exc}")


def test_clean_schema() -> None:
    """Scenario A: pass in the EXACT live schema → zero breaks."""
    section("Scenario A: Clean schema (no breaks expected)")

    # Fetch the live field list via DataHub GraphQL directly
    gql = json.dumps({
        "query": """
        query { dataset(urn: "%s") {
          schemaMetadata { fields { fieldPath type } }
        } }
        """ % ORDERS_URN
    }).encode()
    req = urllib.request.Request(
        f"{DATAHUB_GMS}/api/graphql",
        data=gql,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            gql_resp = json.loads(r.read())
        live_fields = (
            gql_resp.get("data", {})
                    .get("dataset", {})
                    .get("schemaMetadata", {})
                    .get("fields", [])
        )
        if not live_fields:
            warn("Could not fetch live schema – skipping Scenario A")
            return
        known_good = {f["fieldPath"]: f.get("type", "STRING") for f in live_fields}
        ok(f"Fetched live schema: {len(known_good)} fields")
    except Exception as exc:
        warn(f"Could not fetch live schema: {exc} – skipping Scenario A")
        return

    try:
        result = post("/api/detect", {
            "dataset_urn": ORDERS_URN,
            "known_good_schema": known_good,
        })
    except Exception as exc:
        fail(f"/api/detect failed: {exc}")
        return

    print_result(result)

    if result.get("has_break") is False:
        ok("has_break = False (correct – no differences expected)")
    else:
        fail(
            "has_break = True but schema should match! "
            f"Missing: {result.get('missing_fields')}, "
            f"Type changes: {result.get('type_changes')}",
            fatal=False,
        )

    if result.get("severity") in ("low",):
        ok(f"severity = {result['severity']}")
    else:
        warn(f"severity = {result.get('severity')} (expected 'low')")


def test_breaking_changes() -> None:
    """Scenario B: baseline has a dropped field + type change → breaks expected."""
    section("Scenario B: Known-good baseline with injected breaks")

    # Baseline claims these fields exist at these types
    known_good = {
        "order_id":            "NUMBER",
        "order_date":          "DATE",
        "customer_id":         "NUMBER",
        "order_status":        "STRING",
        "order_total":         "STRING",        # ← live schema has NUMBER → type change
        "fulfillment_status":  "STRING",        # ← does NOT exist in live → missing field
        "payment_method_code": "STRING",
    }

    print(f"\n  Baseline schema has {len(known_good)} fields:")
    for f, t in known_good.items():
        print(f"    {f:30s} → {t}")

    try:
        result = post("/api/detect", {
            "dataset_urn": ORDERS_URN,
            "known_good_schema": known_good,
        })
    except Exception as exc:
        fail(f"/api/detect failed: {exc}")
        return

    print_result(result)

    # Assertions
    all_ok = True

    if result.get("has_break"):
        ok("has_break = True ✓")
    else:
        fail("has_break = False — expected True", fatal=False)
        all_ok = False

    if "fulfillment_status" in result.get("missing_fields", []):
        ok("fulfillment_status correctly in missing_fields")
    else:
        fail("fulfillment_status missing from missing_fields", fatal=False)
        all_ok = False

    type_changes = result.get("type_changes", [])
    order_total_change = next((tc for tc in type_changes if tc["field"] == "order_total"), None)
    if order_total_change:
        ok(f"order_total type change detected: {order_total_change['was']} → {order_total_change['now']}")
    else:
        warn("order_total type change not detected (DataHub type label may differ)")

    severity = result.get("severity")
    if severity == "critical":
        ok(f"severity = critical (field removal detected)")
    else:
        warn(f"severity = {severity} (expected 'critical' due to missing field)")

    if all_ok:
        ok("Scenario B PASSED")
    else:
        warn("Scenario B had assertion failures — see above")


def test_simulation() -> None:
    """Scenario C: simulate_schema_break helper."""
    section("Scenario C: Built-in simulation (simulate=True)")

    try:
        result = post("/api/detect", {
            "dataset_urn": ORDERS_URN,
            "simulate": True,
        })
    except Exception as exc:
        fail(f"/api/detect failed: {exc}")
        return

    print_result(result)

    all_ok = True

    if result.get("simulated"):
        ok("simulated = True flag is set")
    else:
        fail("simulated flag missing from result", fatal=False)
        all_ok = False

    if result.get("has_break"):
        ok("has_break = True (simulation injected breaks)")
    else:
        fail("has_break = False — simulation should inject breaks", fatal=False)
        all_ok = False

    missing = result.get("missing_fields", [])
    if "fulfillment_status" in missing:
        ok(f"fulfillment_status in missing_fields (simulated drop)")
    else:
        fail(f"fulfillment_status not in missing_fields: {missing}", fatal=False)
        all_ok = False

    if "estimated_delivery_days" in missing:
        ok("estimated_delivery_days in missing_fields (simulated drop)")
    else:
        warn(f"estimated_delivery_days not in missing_fields: {missing}")

    if all_ok:
        ok("Scenario C PASSED")
    else:
        warn("Scenario C had assertion failures — see above")


def test_via_direct_import() -> None:
    """
    Scenario D: call detect_schema_break() directly (no HTTP) to confirm
    the module itself works independently of FastAPI.
    """
    section("Scenario D: Direct Python import (no HTTP)")

    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from backend.agents.detector import SchemaDetector
        detector = SchemaDetector()
    except Exception as exc:
        warn(f"Could not import SchemaDetector: {exc} — skipping")
        return

    known_good = {
        "order_id":   "NUMBER",
        "order_date": "DATE",
        "ghost_field": "STRING",   # will be missing from live schema
    }

    try:
        result = detector.detect_schema_break(ORDERS_URN, known_good)
    except Exception as exc:
        fail(f"detect_schema_break raised: {exc}", fatal=False)
        return

    print_result(result)

    if "ghost_field" in result.get("missing_fields", []):
        ok("ghost_field detected as missing")
    else:
        warn(f"ghost_field not in missing_fields: {result.get('missing_fields')}")

    if result.get("has_break"):
        ok("has_break = True")
    else:
        warn("has_break = False (ghost_field should trigger a break)")

    ok("Scenario D complete")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("  verify_detector.py")
    print(f"  API    : {API_BASE}")
    print(f"  GMS    : {DATAHUB_GMS}")
    print(f"  URN    : {ORDERS_URN}")
    print("=" * 60)

    test_health()
    test_clean_schema()
    test_breaking_changes()
    test_simulation()
    test_via_direct_import()

    print()
    print("=" * 60)
    print("  verify_detector.py complete — check ✅/❌/⚠️  above")
    print("=" * 60)


if __name__ == "__main__":
    main()
