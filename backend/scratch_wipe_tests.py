import os
from backend.core.datahub_client import DataHubAdapter
from backend.core.memory_store import get_store
from backend.agents.memory_writer import _emit_mcp

CANONICAL = [
    "INC-1786061210822-6XA1E6",
    "INC-1786061218314-KTP8HU",
    "INC-1786061214588-KLPB41"
]

def wipe_test_memories():
    SERVER = os.getenv("DATAHUB_GMS_SERVER", "http://localhost:8080")
    TOKEN  = os.getenv("DATAHUB_GMS_TOKEN", "")

    adapter = DataHubAdapter(server=SERVER, token=TOKEN)
    incidents = adapter.scroll_incident_memories(max_results=500)
    
    deleted_dh = 0
    for inc in incidents:
        incident_id = inc["incident_id"]
        if incident_id not in CANONICAL:
            urn = inc["dataset_urn"]
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
                print(f"DataHub Wiped: {urn} (ID: {incident_id})")
                deleted_dh += 1
            except Exception as e:
                print(f"Failed to wipe DataHub for {urn}: {e}")
                
    store = get_store()
    deleted_local = 0
    for rec_id in list(store._records.keys()):
        if rec_id not in CANONICAL:
            store.delete(rec_id)
            print(f"Local Store Wiped: {rec_id}")
            deleted_local += 1
            
    print(f"Total wiped: {deleted_dh} in DataHub, {deleted_local} locally")

if __name__ == "__main__":
    wipe_test_memories()
