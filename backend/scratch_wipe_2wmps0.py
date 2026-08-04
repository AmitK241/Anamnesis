"""
Wipe INC-1785608750783-2WMPS0 from crm_db.customers URN.

The spurious 4th incident was created by the /api/full-loop verification test.
Overwrites it with the standard __WIPED__ sentinel so scroll_incident_memories()
filters it out going forward.

Run: python -m backend.scratch_wipe_2wmps0
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

TARGET_URN = "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.crm_db.customers,PROD)"
TARGET_INC = "INC-1785608750783-2WMPS0"

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


def emit_mcp(urn: str, aspect_value: dict) -> int:
    mcp = {
        "entityType": "dataset",
        "entityUrn": urn,
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
        return r.status


def get_aspect(urn: str) -> dict:
    encoded = urllib.parse.quote(urn, safe="")
    url = f"{GMS}/aspects/{encoded}?aspect={ASPECT_NAME}&version=0"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as r:
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


print("=" * 65)
print(f"  Wiping {TARGET_INC}")
print(f"  URN: {TARGET_URN}")
print("=" * 65)

# 1. Read current state
before = get_aspect(TARGET_URN)
print(f"\n  Before wipe: incidentId = {before.get('incidentId', '(none)')!r}")

# 2. Emit __WIPED__ sentinel
status = emit_mcp(TARGET_URN, BLANK_ASPECT)
print(f"  MCP ingest HTTP status: {status}")

# 3. Read back to confirm
after = get_aspect(TARGET_URN)
inc_id = after.get("incidentId", "")

if inc_id == "__WIPED__":
    print(f"  OK  incidentId = {inc_id!r}")
    print("      (excluded from scroll_incident_memories going forward)")
else:
    print(f"  WARN unexpected state after wipe: incidentId = {inc_id!r}")
    sys.exit(1)

print("\n" + "=" * 65)
print("  Wipe complete. Run scratch_verify_scores to confirm 3 clean incidents.")
print("=" * 65)
