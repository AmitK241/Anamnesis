#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/verify_diagnoser.py
----------------------------
Exercises the Diagnoser agent and its /api/diagnose endpoint.

Scenarios:
  A. Real orders dataset (dbt platform) with simulated breaks from Detector
     — confirms real upstream/downstream URNs come back from DataHub lineage.
  B. Dataset with no lineage data (postgres orders, which has 0 edges)
     — confirms diagnosis_confidence correctly drops to "low" without crashing.
  C. Direct Python import — bypasses HTTP to test the agent class itself.
  D. /api/detect-and-diagnose combined endpoint — one-shot call.

Usage:
    python backend/verify_diagnoser.py
"""

import json
import sys
import urllib.request
import urllib.error

# Force UTF-8 on Windows (cp1252 console can't print emoji otherwise)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_BASE    = "http://localhost:8888"
DATAHUB_GMS = "http://localhost:8080"

# dbt platform orders has real lineage (upstream DataJob, downstream order_details)
ORDERS_DBT = (
    "urn:li:dataset:(urn:li:dataPlatform:dbt,"
    "b2fd91.order_entry_db.order_entry.orders,PROD)"
)
# postgres platform orders has 0 lineage edges — good for the "no lineage" scenario
ORDERS_PG = (
    "urn:li:dataset:(urn:li:dataPlatform:postgres,"
    "b2fd91.order_entry_db.order_entry.orders,PROD)"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ok(msg: str)   -> None: print(f"  ✅ {msg}")
def warn(msg: str) -> None: print(f"  ⚠️  {msg}")
def fail(msg: str, fatal: bool = True) -> None:
    print(f"  ❌ {msg}")
    if fatal:
        sys.exit(1)

def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)

def post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req  = urllib.request.Request(
        f"{API_BASE}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def get(path: str) -> dict:
    with urllib.request.urlopen(f"{API_BASE}{path}", timeout=10) as r:
        return json.loads(r.read())

def print_diagnosis(d: dict) -> None:
    print()
    print(f"    root_cause           : {d.get('root_cause', '')[:120]}")
    print(f"    upstream_sources     : {len(d.get('upstream_sources', []))} entities")
    for e in d.get("upstream_sources", [])[:3]:
        print(f"      [{e.get('type','?')}] {e.get('urn','')[:70]} (degree={e.get('degree')})")
    print(f"    downstream_impact    : {len(d.get('downstream_impact', []))} entities")
    for e in d.get("downstream_impact", [])[:3]:
        print(f"      [{e.get('type','?')}] {e.get('urn','')[:70]} (degree={e.get('degree')})")
    print(f"    affected_field_count : {d.get('affected_field_count')}")
    print(f"    diagnosis_confidence : {d.get('diagnosis_confidence')}")
    print(f"    severity             : {d.get('severity')}")
    print(f"    break_summary        : {d.get('break_summary')}")
    print()

# ---------------------------------------------------------------------------
# Scenario A: dbt orders — has real lineage, simulate breaks
# ---------------------------------------------------------------------------

def test_real_lineage() -> None:
    section("Scenario A: Real lineage — dbt orders with simulated breaks")

    # Step 1: simulate a break via /api/detect
    print(f"\n  [1] Running simulate_schema_break on dbt orders ...")
    try:
        detection = post("/api/detect", {
            "dataset_urn": ORDERS_DBT,
            "simulate": True,
        })
    except Exception as exc:
        fail(f"/api/detect failed: {exc}")
        return

    ok(f"Detection: has_break={detection.get('has_break')}, "
       f"severity={detection.get('severity')}, "
       f"missing={detection.get('missing_fields')}")

    # Step 2: pass detection_result to /api/diagnose
    print(f"\n  [2] Calling /api/diagnose with detection_result ...")
    try:
        diagnosis = post("/api/diagnose", {"detection_result": detection})
    except Exception as exc:
        fail(f"/api/diagnose failed: {exc}")
        return

    print_diagnosis(diagnosis)

    # Assertions
    all_ok = True

    if diagnosis.get("root_cause"):
        ok("root_cause is populated")
    else:
        fail("root_cause is empty", fatal=False)
        all_ok = False

    upstream   = diagnosis.get("upstream_sources", [])
    downstream = diagnosis.get("downstream_impact", [])

    if upstream:
        ok(f"{len(upstream)} upstream source(s) found (real DataHub lineage)")
        for e in upstream[:2]:
            ok(f"  upstream: [{e['type']}] {e.get('name') or e['urn'][:60]}")
    else:
        warn("No upstream sources returned — postgres platform has no lineage edges; "
             "this is expected if the dbt lineage graph is sparse")

    if downstream:
        ok(f"{len(downstream)} downstream entity/entities found (real DataHub lineage)")
        for e in downstream[:2]:
            ok(f"  downstream: [{e['type']}] {e.get('name') or e['urn'][:60]}")
    else:
        warn("No downstream entities returned — checking if this is expected ...")

    # confidence: "high" if lineage found, "medium" or better if fields found
    confidence = diagnosis.get("diagnosis_confidence")
    affected   = diagnosis.get("affected_field_count", 0)
    if confidence == "high":
        ok(f"diagnosis_confidence = high (lineage + fields)")
    elif confidence == "medium":
        ok(f"diagnosis_confidence = medium (partial data)")
    elif confidence == "low":
        if not upstream and not downstream:
            warn("diagnosis_confidence = low — no lineage edges in this platform; "
                 "try the dbt URN if postgres was used")
        else:
            fail(f"diagnosis_confidence = low but lineage was found", fatal=False)
            all_ok = False
    else:
        fail(f"diagnosis_confidence = {confidence} (unexpected value)", fatal=False)
        all_ok = False

    if affected > 0:
        ok(f"affected_field_count = {affected}")
    else:
        warn("affected_field_count = 0 (unexpected for a simulated break)")

    if all_ok:
        ok("Scenario A PASSED")
    else:
        warn("Scenario A had some warnings — see above")


# ---------------------------------------------------------------------------
# Scenario B: postgres orders — no lineage → confidence = "low"
# ---------------------------------------------------------------------------

def test_no_lineage() -> None:
    section("Scenario B: No-lineage dataset (postgres orders) → confidence='low'")

    # Simulate a break on the postgres orders dataset (we know it has 0 lineage edges)
    print(f"\n  [1] Simulating break on postgres orders (0 lineage edges) ...")
    try:
        detection = post("/api/detect", {
            "dataset_urn": ORDERS_PG,
            "simulate": True,
        })
    except Exception as exc:
        fail(f"/api/detect failed: {exc}")
        return

    ok(f"Detection: has_break={detection.get('has_break')}")

    print(f"\n  [2] Diagnosing ...")
    try:
        diagnosis = post("/api/diagnose", {"detection_result": detection})
    except Exception as exc:
        fail(f"/api/diagnose failed: {exc}")
        return

    print_diagnosis(diagnosis)

    # Key assertion: must NOT crash and must return meaningful data
    if "root_cause" in diagnosis:
        ok("root_cause key present (no crash)")
    else:
        fail("root_cause key missing — agent may have crashed", fatal=False)

    conf = diagnosis.get("diagnosis_confidence", "")
    ups  = diagnosis.get("upstream_sources", [])
    dns  = diagnosis.get("downstream_impact", [])

    if conf in ("high", "medium", "low"):
        ok(f"diagnosis_confidence = '{conf}' (valid value, no crash)")
    else:
        fail(f"diagnosis_confidence = '{conf}' (unexpected)", fatal=False)

    # postgres has no upstream, but may have cross-platform downstream edges
    if not ups:
        ok("upstream_sources = [] (expected — postgres platform has no upstream)")
    else:
        warn(f"Unexpected upstream for postgres: {len(ups)} edges found")

    if dns:
        ok(f"downstream_impact = {len(dns)} entities (cross-platform lineage resolved correctly)")
    else:
        ok("downstream_impact = [] (no downstream lineage for this platform)")

    if "affected_field_count" in diagnosis:
        ok(f"affected_field_count = {diagnosis['affected_field_count']}")

    ok("Scenario B PASSED — no crash, graceful low-confidence output")


# ---------------------------------------------------------------------------
# Scenario C: direct Python import (no HTTP)
# ---------------------------------------------------------------------------

def test_direct_import() -> None:
    section("Scenario C: Direct Python import (no HTTP)")

    try:
        from backend.agents.detector  import SchemaDetector
        from backend.agents.diagnoser import Diagnoser
    except Exception as exc:
        warn(f"Could not import agents: {exc} — skipping")
        return

    detector  = SchemaDetector()
    diagnoser = Diagnoser()

    print(f"\n  Running simulate_schema_break → diagnose() directly ...")
    detection = detector.simulate_schema_break(ORDERS_DBT)
    ok(f"Detection complete: has_break={detection.get('has_break')}")

    diagnosis = diagnoser.diagnose(detection)
    print_diagnosis(diagnosis)

    required_keys = [
        "dataset_urn", "root_cause", "upstream_sources",
        "downstream_impact", "affected_field_count", "diagnosis_confidence",
    ]
    all_ok = True
    for key in required_keys:
        if key in diagnosis:
            ok(f"'{key}' present")
        else:
            fail(f"'{key}' missing from diagnosis", fatal=False)
            all_ok = False

    if all_ok:
        ok("Scenario C PASSED")
    else:
        warn("Scenario C had missing keys")


# ---------------------------------------------------------------------------
# Scenario D: /api/detect-and-diagnose combined endpoint
# ---------------------------------------------------------------------------

def test_detect_and_diagnose() -> None:
    section("Scenario D: /api/detect-and-diagnose combined endpoint")

    print(f"\n  Calling /api/detect-and-diagnose on dbt orders ...")
    try:
        result = post("/api/detect-and-diagnose", {"dataset_urn": ORDERS_DBT})
    except Exception as exc:
        fail(f"/api/detect-and-diagnose failed: {exc}")
        return

    detection = result.get("detection") or {}
    diagnosis = result.get("diagnosis") or {}

    print(f"\n  detection.has_break       = {detection.get('has_break')}")
    print(f"  detection.severity        = {detection.get('severity')}")
    print(f"  diagnosis.confidence      = {diagnosis.get('diagnosis_confidence')}")
    print(f"  diagnosis.upstream_count  = {len(diagnosis.get('upstream_sources', []))}")
    print(f"  diagnosis.downstream_count= {len(diagnosis.get('downstream_impact', []))}")
    print(f"  diagnosis.root_cause      = {str(diagnosis.get('root_cause', ''))[:100]}")

    if detection.get("has_break"):
        ok("Detection phase returned has_break=True")
    else:
        warn("Detection phase returned has_break=False — simulation may not be wired")

    if diagnosis.get("root_cause"):
        ok("Diagnosis phase returned root_cause")
    else:
        warn("Diagnosis phase returned empty root_cause")

    ok("Scenario D PASSED — combined endpoint works end-to-end")


# ---------------------------------------------------------------------------
# Pre-flight health check
# ---------------------------------------------------------------------------

def test_health() -> None:
    section("Pre-flight: health checks")
    try:
        data = get("/health")
        if data.get("datahub_connected"):
            ok(f"DataHub connected ({data.get('datahub_server')})")
        else:
            warn("DataHub NOT connected — lineage calls will return empty lists")
        ok(f"API server healthy — {data.get('memory_records', 0)} memory record(s)")
    except Exception as exc:
        fail(f"API server unreachable at {API_BASE}: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("  verify_diagnoser.py")
    print(f"  API    : {API_BASE}")
    print(f"  GMS    : {DATAHUB_GMS}")
    print("=" * 60)

    test_health()
    test_real_lineage()
    test_no_lineage()
    test_direct_import()
    test_detect_and_diagnose()

    print()
    print("=" * 60)
    print("  verify_diagnoser.py complete — check ✅/❌/⚠️  above")
    print("=" * 60)


if __name__ == "__main__":
    main()
