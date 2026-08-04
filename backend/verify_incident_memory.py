# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
backend/verify_incident_memory.py
-----------------------------------
Emits a custom `incidentMemory` aspect for a dataset via DataHub MCP,
then reads it back to confirm the round-trip succeeded.

Requirements:
    pip install acryl-datahub

Usage:
    python backend/verify_incident_memory.py
"""

import json
import sys
import time

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATAHUB_GMS_URL = "http://localhost:8080"
DATASET_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:postgres,"
    "b2fd91.order_entry_db.order_entry.orders,PROD)"
)
ASPECT_NAME = "incidentMemory"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    sys.exit(1)


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


def get_aspect(entity_urn: str, aspect_name: str) -> dict:
    """Fetch a specific aspect from GMS."""
    response = requests.get(
        f"{DATAHUB_GMS_URL}/aspects/{requests.utils.quote(entity_urn, safe='')}",
        params={"aspect": aspect_name, "version": 0},
        timeout=30,
    )
    if response.status_code == 404:
        return {}
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print(" verify_incident_memory.py")
    print(f" Dataset URN : {DATASET_URN}")
    print(f" GMS URL     : {DATAHUB_GMS_URL}")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Check GMS is reachable
    # ------------------------------------------------------------------
    print("\n[1] Checking GMS connectivity...")
    try:
        resp = requests.get(f"{DATAHUB_GMS_URL}/config", timeout=10)
        resp.raise_for_status()
        config = resp.json()
        ok(f"GMS reachable - DataHub version info retrieved")
    except Exception as e:
        fail(f"Cannot reach GMS at {DATAHUB_GMS_URL}: {e}")

    # ------------------------------------------------------------------
    # 2. Check model was loaded
    # ------------------------------------------------------------------
    print("\n[2] Checking custom model registration...")
    models = config.get("models", {})
    registry_id = "anamnesis-incident-model"
    if registry_id in models:
        ok(f"Registry '{registry_id}' found in GMS config: {models[registry_id]}")
    else:
        print(f"  [WARN] Registry '{registry_id}' not found in GMS config.")
        print(f"     Available registries: {list(models.keys()) or '(none)'}")
        print("     Proceeding with aspect write anyway...")

    # ------------------------------------------------------------------
    # 3. Construct and emit IncidentMemory aspect
    # ------------------------------------------------------------------
    print("\n[3] Emitting incidentMemory aspect...")

    incident_memory = {
        "incidentId": "INC-2024-0042",
        "rootCause": (
            "A schema change in the upstream orders table dropped the "
            "`fulfillment_status` column without a coordinated migration, "
            "causing downstream aggregation pipelines to fail."
        ),
        "downstreamImpact": [
            "urn:li:dataset:(urn:li:dataPlatform:postgres,"
            "b2fd91.order_entry_db.reporting.daily_fulfillment_summary,PROD)",
            "urn:li:dataset:(urn:li:dataPlatform:postgres,"
            "b2fd91.order_entry_db.reporting.revenue_by_sku,PROD)",
        ],
        "resolutionCodeDiff": (
            "--- a/pipelines/orders_agg.py\n"
            "+++ b/pipelines/orders_agg.py\n"
            "@@ -42,7 +42,7 @@\n"
            "-    .select('order_id', 'fulfillment_status', 'revenue')\n"
            "+    .select('order_id', 'status', 'revenue')  # column renamed in v2 schema\n"
        ),
        "embeddingVector": [
            0.12, -0.45, 0.78, 0.03, -0.22, 0.61, 0.14, -0.09,
            0.55, 0.31, -0.77, 0.42, 0.08, -0.33, 0.90, 0.11,
        ],
        "similarPastIncidents": [
            "urn:li:dataset:(urn:li:dataPlatform:postgres,"
            "b2fd91.order_entry_db.order_entry.shipments,PROD)",
        ],
        "timeSavedEstimate": 120,
        "timestamp": int(time.time() * 1000),
    }

    try:
        emit_mcp(DATASET_URN, ASPECT_NAME, incident_memory)
        ok("MCP emitted successfully (HTTP 200/202)")
    except Exception as e:
        fail(f"MCP emit failed: {e}")

    # ------------------------------------------------------------------
    # 4. Read back the aspect
    # ------------------------------------------------------------------
    print("\n[4] Reading back incidentMemory aspect...")
    try:
        result = get_aspect(DATASET_URN, ASPECT_NAME)
    except Exception as e:
        fail(f"Aspect read failed: {e}")

    if not result:
        fail("Aspect read returned empty - aspect may not have been persisted.")

    # Extract the actual aspect value.
    # GMS returns: {"aspect": {"value": "{\"com.anamnesis.incident.IncidentMemory\": {...}}"}}
    # We need to unwrap two layers: the JSON string in "value", then the FQCN key.
    aspect_data = result.get("aspect", {})
    if isinstance(aspect_data, dict) and "value" in aspect_data:
        try:
            aspect_data = json.loads(aspect_data["value"])
        except json.JSONDecodeError:
            pass  # keep raw

    # Unwrap fully-qualified class name wrapper if present
    # e.g. {"com.anamnesis.incident.IncidentMemory": {actual fields}}
    if isinstance(aspect_data, dict) and len(aspect_data) == 1:
        only_key = next(iter(aspect_data))
        if "." in only_key:  # looks like a FQCN
            aspect_data = aspect_data[only_key]

    print("\n  Retrieved fields:")
    if isinstance(aspect_data, dict):
        for field, value in aspect_data.items():
            display = str(value)
            if len(display) > 80:
                display = display[:77] + "..."
            print(f"    {field:30s} = {display}")
    else:
        print(f"    {aspect_data}")

    # ------------------------------------------------------------------
    # 5. Spot-check key fields
    # ------------------------------------------------------------------
    print("\n[5] Validating returned fields...")
    checks = [
        ("incidentId",        lambda v: v == "INC-2024-0042"),
        ("rootCause",         lambda v: "schema change" in str(v)),
        ("downstreamImpact",  lambda v: isinstance(v, list) and len(v) == 2),
        ("embeddingVector",   lambda v: isinstance(v, list) and len(v) == 16),
        ("timeSavedEstimate", lambda v: v == 120),
        ("timestamp",         lambda v: isinstance(v, int) and v > 0),
    ]

    all_passed = True
    for field, predicate in checks:
        val = aspect_data.get(field) if isinstance(aspect_data, dict) else None
        passed = val is not None and predicate(val)
        if passed:
            ok(f"{field}")
        else:
            print(f"  [FAIL] {field} - got: {val!r}")
            all_passed = False

    print()
    if all_passed:
        print("=" * 60)
        print("  ALL CHECKS PASSED - incidentMemory round-trip verified!")
        print("=" * 60)
    else:
        print("=" * 60)
        print("  SOME CHECKS FAILED - see output above")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
