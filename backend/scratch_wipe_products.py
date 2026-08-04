"""
Wipe the products URN incidentMemory so seed_demo_data starts clean.
Run: python -m backend.scratch_wipe_products
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

WIPE_TARGETS = [
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.products,PROD)",
    # Also ensure the crm_db customers URN (demo Incident 2 slot) is clean
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.crm_db.customers,PROD)",
    # And orders (demo Incident 1 slot)
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.orders,PROD)",
]

BLANK = {
    "incidentId":           "__WIPED__",
    "rootCause":            "",
    "downstreamImpact":     [],
    "resolutionCodeDiff":   "",
    "embeddingVector":      [],
    "similarPastIncidents": [],
    "timeSavedEstimate":    0,
    "timestamp":            0,
}

def emit_mcp(urn, aspect_value):
    mcp = {
        "entityType": "dataset",
        "entityUrn": urn,
        "changeType": "UPSERT",
        "aspectName": "incidentMemory",
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
        return r.status

def read_back(urn):
    encoded = urllib.parse.quote(urn, safe="")
    url = f"{GMS}/aspects/{encoded}?aspect=incidentMemory&version=0"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as r:
            raw = json.loads(r.read())
        aspect = raw.get("aspect", {})
        if isinstance(aspect, dict) and "value" in aspect:
            aspect = json.loads(aspect["value"])
        if isinstance(aspect, dict) and len(aspect) == 1:
            only = next(iter(aspect))
            if "." in only:
                aspect = aspect[only]
        return aspect if isinstance(aspect, dict) else {}
    except Exception as exc:
        if "404" in str(exc):
            return {}
        raise

print("=" * 60)
print("  Wiping all 3 demo slots before clean reseed")
print("=" * 60)

for urn in WIPE_TARGETS:
    short = urn.split(",")[1] if "," in urn else urn
    print(f"\n  Wiping: {short}")
    status = emit_mcp(urn, BLANK)
    aspect = read_back(urn)
    inc_id = aspect.get("incidentId", "?")
    if inc_id == "__WIPED__":
        print(f"  OK  incidentId = '{inc_id}'")
    else:
        print(f"  WARN unexpected state: incidentId = '{inc_id}'")

print("\n" + "=" * 60)
print("  All 3 demo slots cleared. Ready for seed_demo_data.")
print("=" * 60)
