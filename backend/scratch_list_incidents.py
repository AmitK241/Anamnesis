"""
One-shot audit: call scroll_incident_memories() and list every record found.
Run: python -m backend.scratch_list_incidents
"""
import sys, io as _io

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import logging
logging.basicConfig(level=logging.WARNING)   # suppress INFO noise

from backend.core.datahub_client import DataHubAdapter

dh = DataHubAdapter()
records = dh.scroll_incident_memories()

print(f"\n{'='*60}")
print(f"  IncidentMemory records in DataHub: {len(records)}")
print(f"{'='*60}")

for i, r in enumerate(records, 1):
    vec = r.get("embedding_vector", [])
    ts  = r.get("timestamp", 0)
    print(f"\n  [{i}]")
    print(f"    incident_id  : {r.get('incident_id', '—')}")
    print(f"    dataset_urn  : {r.get('dataset_urn', '—')}")
    print(f"    embedding    : {len(vec)}-dim vector {'✅' if vec else '❌ MISSING'}")
    print(f"    timestamp_ms : {ts}")

print(f"\n{'='*60}")
if len(records) == 3:
    print("  ✅  EXACTLY 3 records — demo trio confirmed clean")
else:
    print(f"  ❌  Expected 3, got {len(records)} — investigate above")
print(f"{'='*60}\n")

sys.exit(0 if len(records) == 3 else 1)
