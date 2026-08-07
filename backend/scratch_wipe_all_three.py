"""
backend/scratch_wipe_all_three.py
----------------------------------
Wipes all 3 demo URNs before a clean reseed.
Handles orders, customers, AND products.

Run: python -m backend.scratch_wipe_all_three
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

WIPE_TARGETS = [
    (
        "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.orders,PROD)",
        "orders (INC-1785651735132-LNBB7W)",
    ),
    (
        "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.crm_db.customers,PROD)",
        "customers (INC-1785991726222-J0OC7X)",
    ),
    (
        "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.products,PROD)",
        "products (INC-1785651742952-PO58CF)",
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
print("  scratch_wipe_all_three.py")
print("  Wiping all 3 demo IncidentMemory aspects for clean reseed")
print("=" * 65)

failures = []
for urn, label in WIPE_TARGETS:
    print(f"\n  Wiping: {label}")
    print(f"    URN: {urn}")
    try:
        emit_mcp(urn, BLANK_ASPECT)
        aspect = get_aspect(urn)
        incident_id = aspect.get("incidentId", "")
        if incident_id == "__WIPED__":
            print(f"  ✅ Wiped successfully (incidentId='__WIPED__')")
        else:
            print(f"  ⚠️  Unexpected state: incidentId={incident_id!r}")
    except Exception as exc:
        print(f"  ❌ Failed: {exc}")
        failures.append(label)

os.environ.pop("ANAMNESIS_KNOWN_DATASET_URNS", None)

print()
if failures:
    print("=" * 65)
    print(f"  ❌ {len(failures)} wipe(s) failed — see above")
    print("=" * 65)
    sys.exit(1)
else:
    print("=" * 65)
    print("  ✅ All 3 URNs wiped — ready for clean reseed")
    print("=" * 65)
