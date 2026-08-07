import sys
sys.stdout.reconfigure(line_buffering=True)
import os
import time
import json
import urllib.request
import subprocess

print("Starting Uvicorn...", flush=True)
u_log = open("uvicorn.log", "w")
proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.api.main:app", "--port", "8000"], stdout=u_log, stderr=u_log)

url = "http://127.0.0.1:8000/api/health"
print("Waiting for server to be ready...", flush=True)
for _ in range(60):
    try:
        urllib.request.urlopen(url)
        print("Server is up!", flush=True)
        break
    except Exception:
        time.sleep(1)
else:
    print("Server failed to start", flush=True)
    proc.terminate()
    sys.exit(1)

urns = [
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.orders,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.crm_db.customers,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.products,PROD)"
]

for urn in urns:
    print(f"\n--- Output for {urn} ---", flush=True)
    data = json.dumps({"dataset_urn": urn, "simulate": True}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:8000/api/full-loop", data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            print(json.dumps(json.loads(response.read().decode("utf-8")), indent=2), flush=True)
    except Exception as e:
        print(f"Error: {e}", flush=True)
        if hasattr(e, 'read'):
            print(e.read().decode("utf-8"), flush=True)

print("\n--- Independent Verification (DataHub Scroll) ---", flush=True)
sys.path.insert(0, os.path.abspath('.'))
try:
    from backend.core.datahub_client import DataHubAdapter
    dh = DataHubAdapter()
    records = dh.scroll_incident_memories()
    print(json.dumps(records, indent=2), flush=True)
except Exception as e:
    print(f"Error checking datahub: {e}", flush=True)

proc.terminate()
