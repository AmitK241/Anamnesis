import os
import json
import urllib.request
import urllib.parse
from backend.core.datahub_client import DataHubAdapter
from backend.core.memory_store import get_store

def wipe_datahub_memories():
    SERVER = os.getenv("DATAHUB_GMS_SERVER", "http://localhost:8080")
    TOKEN  = os.getenv("DATAHUB_GMS_TOKEN", "")

    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    adapter = DataHubAdapter(server=SERVER, token=TOKEN)
    incidents = adapter.scroll_incident_memories(max_results=500)
    
    deleted_count = 0
    for inc in incidents:
        urn = inc["dataset_urn"]
        incident_id = inc["incident_id"]
        
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
            _emit_mcp(SERVER, TOKEN, urn, "incidentMemory", aspect)
            print(f"DataHub Deleted: {urn} (Incident ID: {incident_id})")
            deleted_count += 1
        except Exception as e:
            print(f"Failed to delete {urn}: {e}")
            
    print(f"\nTotal DataHub incidentMemory aspects deleted: {deleted_count}")

def wipe_local_memories():
    store = get_store()
    count = 0
    for rec_id in list(store._records.keys()):
        store.delete(rec_id)
        count += 1
    print(f"Total local memory_store.json records deleted: {count}")

if __name__ == "__main__":
    print("--- Wiping DataHub Incident Memories ---")
    wipe_datahub_memories()
    print("\n--- Wiping Local memory_store.json ---")
    wipe_local_memories()
    print("\nWipe complete.")
