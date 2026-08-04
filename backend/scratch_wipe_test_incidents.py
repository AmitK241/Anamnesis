"""
backend/scratch_wipe_test_incidents.py
---------------------------------------
Wipes ALL known test/scratch IncidentMemory aspects from DataHub
before seeding the clean demo story.

Incidents being wiped (from audit Step 1):
  - INC-1785431016721-QL6YVB  (verify_memory_writer.py)
  - INC-RECALL-A              (verify_recall.py — already overwritten on orders URN)
  - INC-RECALL-B              (verify_recall.py — shipments URN)
  - INC-RECALL-C              (verify_recall.py — crm_db.customers URN)

Wipe strategy: overwrite the aspect with a "null/empty" sentinel, then
verify it no longer has a meaningful incidentId. DataHub UPSERT doesn't
support DELETE on custom aspects, so we overwrite with a blank record.

Run: python -m backend.scratch_wipe_test_incidents
"""
import json
import os
import sys
import urllib.parse
import urllib.request
import io as _io

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

GMS = os.getenv("DATAHUB_GMS_SERVER", "http://localhost:8080")
ASPECT_NAME = "incidentMemory"

# ── Exact URNs carrying test incidents ───────────────────────────────────────
WIPE_TARGETS = [
    # INC-1785431016721-QL6YVB (and INC-RECALL-A which was overwritten here)
    (
        "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.orders,PROD)",
        "INC-1785431016721-QL6YVB / INC-RECALL-A (orders — verify runs)",
    ),
    # INC-RECALL-B
    (
        "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.logistics.shipments,PROD)",
        "INC-RECALL-B (shipments — verify_recall seed)",
    ),
    # INC-RECALL-C
    (
        "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.crm_db.customers,PROD)",
        "INC-RECALL-C (crm_db.customers — verify_recall seed)",
    ),
]

BLANK_ASPECT = {
    "incidentId":           "__WIPED__",
    "rootCause":            "",
    "downstreamImpact":     [],
    "resolutionCodeDiff":   "",
    "embeddingVector":      [],
    "similarPastIncidents": [],
    "timeSavedEstimate":    0,
    "timestamp":            0,
}


def emit_mcp(entity_urn: str, aspect_value: dict) -> None:
    mcp = {
        "entityType": "dataset",
        "entityUrn": entity_urn,
        "changeType": "UPSERT",
        "aspectName": ASPECT_NAME,
        "aspect": {
            "contentType": "application/json",
            "value": json.dumps(aspect_value),
        },
    }
    body = json.dumps({"proposal": mcp}).encode()
    req = urllib.request.Request(
        f"{GMS}/aspects?action=ingestProposal",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        status = r.status
    if status not in (200, 201, 202):
        raise RuntimeError(f"MCP ingest failed [HTTP {status}]")


def get_aspect(urn: str) -> dict:
    encoded = urllib.parse.quote(urn, safe="")
    url = f"{GMS}/aspects/{encoded}?aspect={ASPECT_NAME}&version=0"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = json.loads(r.read())
        aspect_data = raw.get("aspect", {})
        if isinstance(aspect_data, dict) and "value" in aspect_data:
            aspect_data = json.loads(aspect_data["value"])
        if isinstance(aspect_data, dict) and len(aspect_data) == 1:
            only = next(iter(aspect_data))
            if "." in only:
                aspect_data = aspect_data[only]
        return aspect_data if isinstance(aspect_data, dict) else {}
    except Exception as exc:
        if "404" in str(exc):
            return {}
        raise


print("=" * 65)
print("  scratch_wipe_test_incidents.py")
print("  Wiping all test/scratch IncidentMemory aspects")
print("=" * 65)

failures = []
for urn, label in WIPE_TARGETS:
    print(f"\n  Wiping: {label}")
    print(f"    URN: {urn}")
    try:
        # 1. Overwrite with blank sentinel
        emit_mcp(urn, BLANK_ASPECT)
        # 2. Read back to confirm
        aspect = get_aspect(urn)
        incident_id = aspect.get("incidentId", "")
        if incident_id == "__WIPED__":
            print(f"  ✅ Wiped successfully (incidentId='__WIPED__')")
        else:
            print(f"  ⚠️  Unexpected state after wipe: incidentId={incident_id!r}")
    except Exception as exc:
        print(f"  ❌ Failed: {exc}")
        failures.append(label)

# Also clear the env-var so no stale URNs leak into recall
os.environ.pop("ANAMNESIS_KNOWN_DATASET_URNS", None)

print()
if failures:
    print("=" * 65)
    print(f"  ❌ {len(failures)} wipe(s) failed — see above")
    print("=" * 65)
    sys.exit(1)
else:
    print("=" * 65)
    print("  ✅ All test incidents wiped — DataHub is clean for demo seeding")
    print("=" * 65)
