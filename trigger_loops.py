import urllib.request
import json
import sys

def hit_loop(urn):
    url = "http://127.0.0.1:8000/api/full-loop"
    data = json.dumps({"dataset_urn": urn, "simulate": True}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
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
