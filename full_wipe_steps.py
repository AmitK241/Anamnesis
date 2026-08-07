import os
import sys
import json
import time
import urllib.request

sys.path.insert(0, os.path.abspath('.'))
from backend.core.datahub_client import DataHubAdapter

# We will try both 8080 and whatever is in env, defaults to 8080
adapter = DataHubAdapter(server="http://localhost:8080", token="")

print("=== STEP 1: scroll_incident_memories() RAW ===")
try:
    incidents_step1 = adapter.scroll_incident_memories(max_results=500)
    print(json.dumps(incidents_step1, indent=2))
except Exception as e:
    print(f"Error in step 1: {e}")
    incidents_step1 = []

print("\n=== STEP 2: WIPING ALL ===")
deleted_count = 0
for inc in incidents_step1:
    urn = inc.get("dataset_urn")
    incident_id = inc.get("incident_id")
    from backend.agents.memory_writer import _emit_mcp
    try:
        aspect = {
            "incidentId": "__WIPED__",
            "rootCause": "",
            "downstreamImpact": [],
            "resolutionCodeDiff": "",
            "embeddingVector": [],
            "similarPastIncidents": [],
            "timeSavedEstimate": 0,
            "timestamp": 0,
        }
        _emit_mcp("http://localhost:8080", "", urn, "incidentMemory", aspect)
        print(f"DataHub Deleted: {urn} (Incident ID: {incident_id})")
        deleted_count += 1
    except Exception as e:
        print(f"Failed to delete {urn}: {e}")
        
print(f"Total wiped: {deleted_count}")

print("\n=== STEP 3: scroll_incident_memories() AFTER WIPE ===")
time.sleep(2)
try:
    incidents_step3 = adapter.scroll_incident_memories(max_results=500)
    print(json.dumps(incidents_step3, indent=2))
except Exception as e:
    print(f"Error in step 3: {e}")

print("\n=== STEP 4: WIPING LOCAL memory_store.json ===")
store_path = "memory_store.json"
with open(store_path, "w") as f:
    f.write("{}")
with open(store_path, "r") as f:
    print(f.read())

print("\n=== STEP 5: RESTARTING BACKEND ===")
os.utime("backend/api/main.py", None)
time.sleep(5) # wait for uvicorn to reload

print("\n=== STEP 6: CURL /api/incidents ===")
try:
    req = urllib.request.Request("http://localhost:8888/api/incidents")
    with urllib.request.urlopen(req) as resp:
        print(resp.read().decode())
except Exception as e:
    print(e)
    if hasattr(e, 'read'):
        print(e.read().decode())

print("\n=== STEP 7: CURL /health (and /api/health) ===")
try:
    req = urllib.request.Request("http://localhost:8888/health")
    with urllib.request.urlopen(req) as resp:
        print(f"/health: {resp.read().decode()}")
except Exception as e:
    print(f"/health error: {e}")
    if hasattr(e, 'read'):
        print(e.read().decode())

try:
    req = urllib.request.Request("http://localhost:8888/api/health")
    with urllib.request.urlopen(req) as resp:
        print(f"/api/health: {resp.read().decode()}")
except Exception as e:
    print(f"/api/health error: {e}")
    if hasattr(e, 'read'):
        print(e.read().decode())
