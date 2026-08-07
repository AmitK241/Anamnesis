import urllib.request
import json
import sys
import time

url = "http://127.0.0.1:8000/api/health"
print("Waiting for server...")
for _ in range(60):
    try:
        urllib.request.urlopen(url)
        print("Server is up!")
        break
    except Exception:
        time.sleep(1)
else:
    print("Server did not start.")
    sys.exit(1)

def hit_loop(urn):
    api_url = "http://127.0.0.1:8000/api/full-loop"
    data = json.dumps({"dataset_urn": urn, "simulate": True}).encode("utf-8")
    req = urllib.request.Request(api_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            print(f"--- Response for {urn} ---")
            print(json.dumps(json.loads(response.read().decode("utf-8")), indent=2))
    except Exception as e:
        print(f"--- Error for {urn} ---")
        print(e)
        if hasattr(e, 'read'):
            print(e.read().decode("utf-8"))

urns = [
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.orders,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.crm_db.customers,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.products,PROD)"
]

for u in urns:
    hit_loop(u)
