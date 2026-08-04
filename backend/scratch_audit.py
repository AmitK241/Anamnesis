"""
Scratch: Targeted audit — IncidentMemory aspects + key table schemas.
Run: python -m backend.scratch_audit
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

KNOWN_URNS = [
    # From verify_recall.py seeds
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.orders,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.logistics.shipments,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.crm_db.customers,PROD)",
    # Other real tables visible in UI
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.products,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.customers,PROD)",
]


def gql(query: str, variables: dict = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    req = urllib.request.Request(
        f"{GMS}/api/graphql",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def get_schema(urn: str) -> dict:
    q = """
    query Schema($urn: String!) {
      dataset(urn: $urn) {
        schemaMetadata {
          fields { fieldPath type }
        }
      }
    }
    """
    try:
        data = gql(q, {"urn": urn})
        fields = (
            (data.get("data") or {})
            .get("dataset", {})
            .get("schemaMetadata") or {}
        ).get("fields", []) or []
        return {f["fieldPath"]: f.get("type", "UNKNOWN") for f in fields}
    except Exception as exc:
        return {"__error__": str(exc)}


def get_aspect(urn: str, aspect: str) -> dict:
    encoded = urllib.parse.quote(urn, safe="")
    url = f"{GMS}/aspects/{encoded}?aspect={aspect}&version=0"
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
        return {"__error__": str(exc)}


# ── Step 1: ALL datasets in DataHub (names only) ─────────────────────────────
print("=" * 70)
print("STEP 1: All datasets currently in DataHub")
print("=" * 70)

SEARCH_Q = """
query {
  searchAcrossEntities(input: {
    types: [DATASET]
    query: "*"
    count: 200
  }) {
    total
    searchResults {
      entity {
        urn
        ... on Dataset { name platform { name } }
      }
    }
  }
}
"""
resp = gql(SEARCH_Q)
all_results = (
    resp.get("data", {})
    .get("searchAcrossEntities", {})
    .get("searchResults", [])
)
print(f"\n  Total datasets: {len(all_results)}\n")
all_urns_discovered = []
for r in sorted(all_results, key=lambda x: x["entity"].get("name", "")):
    e = r["entity"]
    name = e.get("name", "?")
    urn = e.get("urn", "")
    platform = (e.get("platform") or {}).get("name", "?")
    all_urns_discovered.append(urn)
    print(f"  {name:50s} [{platform:12s}] {urn}")


# ── Step 2: Schema for our KEY tables ────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 2: Schema fields for key tables")
print("=" * 70)

key_label = {
    "orders":    "ORDERS TABLE",
    "shipments": "SHIPMENTS TABLE",
    "customers": "CUSTOMERS TABLE",
    "products":  "PRODUCTS TABLE",
}
for urn in all_urns_discovered:
    for keyword in key_label:
        if keyword in urn.lower():
            schema = get_schema(urn)
            print(f"\n  [{key_label[keyword]}] {urn}")
            for field, ftype in sorted(schema.items()):
                print(f"    {field:40s} {ftype}")
            break


# ── Step 3: IncidentMemory aspects ───────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 3: IncidentMemory aspects — EVERYTHING currently stored")
print("=" * 70)

found_incidents = []
# Check all known + discovered URNs
check_urns = list(dict.fromkeys(KNOWN_URNS + all_urns_discovered))
for urn in check_urns:
    aspect = get_aspect(urn, "incidentMemory")
    if aspect and aspect.get("incidentId"):
        found_incidents.append((urn, aspect))
        print(f"\n  incidentId       : {aspect.get('incidentId')}")
        print(f"  dataset URN      : {urn}")
        print(f"  timestamp        : {aspect.get('timestamp')}")
        rc = str(aspect.get("rootCause", ""))
        print(f"  rootCause        : {rc[:100]}{'...' if len(rc)>100 else ''}")
        vec = aspect.get("embeddingVector", [])
        print(f"  embeddingVector  : dim={len(vec)}")
        print(f"  timeSavedEstimate: {aspect.get('timeSavedEstimate')}")
        si = aspect.get("similarPastIncidents", [])
        print(f"  similarPastInc.  : {si}")

if not found_incidents:
    print("\n  (NO IncidentMemory aspects found in DataHub)")

print(f"\n\n{'=' * 70}")
print(f"  SUMMARY: {len(found_incidents)} IncidentMemory record(s) found across {len(check_urns)} URN(s) checked")
print(f"{'=' * 70}")
