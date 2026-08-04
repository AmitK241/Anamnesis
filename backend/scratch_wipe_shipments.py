"""
Wipe the stale empty incidentMemory aspect on the shipments URN
using a MetadataChangeProposal with changeType=DELETE.
Run: python -m backend.scratch_wipe_shipments
"""
import json, sys, time, urllib.request, urllib.parse, os
import io as _io

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SERVER = os.getenv("DATAHUB_GMS_SERVER", "http://localhost:8080")
TOKEN  = os.getenv("DATAHUB_GMS_TOKEN", "")
URN    = "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.logistics.shipments,PROD)"

headers = {"Content-Type": "application/json"}
if TOKEN:
    headers["Authorization"] = f"Bearer {TOKEN}"

def gql(query, variables=None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    req = urllib.request.Request(
        f"{SERVER}/api/graphql",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

print(f"\nTarget URN: {URN}")

# ── Method 1: MCP via POST /aspects (changeType=DELETE) ────────────────────
print("\n[1] Attempting MCP DELETE via POST /aspects ...")
mcp = {
    "proposal": {
        "entityType": "dataset",
        "entityUrn": URN,
        "changeType": "DELETE",
        "aspectName": "incidentMemory",
        "aspect": {
            "value": "{}",
            "contentType": "application/json",
        },
    }
}
try:
    req = urllib.request.Request(
        f"{SERVER}/aspects?action=ingestProposal",
        data=json.dumps(mcp).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read()
    print(f"  Response: {body[:200]}")
except Exception as e:
    print(f"  Failed: {e}")

# ── Method 2: GraphQL mutation updateDataset / deleteAspect ───────────────
print("\n[2] Attempting GraphQL removeAspect ...")
mutation = """
mutation RemoveAspect($urn: String!, $aspectName: String!) {
  removeAspect(input: { urn: $urn, aspectName: $aspectName })
}
"""
try:
    r = gql(mutation, {"urn": URN, "aspectName": "incidentMemory"})
    print(f"  GraphQL response: {r}")
except Exception as e:
    print(f"  GraphQL failed: {e}")

# ── Wait and recheck ───────────────────────────────────────────────────────
time.sleep(1)
print("\nRechecking...")
encoded = urllib.parse.quote(URN, safe="")
url = f"{SERVER}/aspects/{encoded}?aspect=incidentMemory&version=0"
try:
    req2 = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req2, timeout=10) as resp2:
        raw = json.loads(resp2.read())
    aspect = raw.get("aspect", {})
    inner = aspect.get("com.anamnesis.incident.IncidentMemory", aspect)
    if not inner.get("incidentId") and not inner.get("embeddingVector"):
        print("  ⚠️  Aspect still present but is empty shell — checking alternate approach")
    else:
        print(f"  Still present with data: {json.dumps(inner)[:200]}")
except Exception as e:
    if "404" in str(e):
        print("  ✅  Gone — 404 confirmed")
    else:
        print(f"  Check error: {e}")
