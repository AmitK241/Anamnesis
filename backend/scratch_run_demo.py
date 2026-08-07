import urllib.request
import json
import time

urls = ["http://localhost:8888/api/full-loop", "http://localhost:8000/api/full-loop"]

urns = [
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.products,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.products,PROD)",
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.crm_db.customers,PROD)"
]

for urn in urns:
    print(f"\n======================================")
    print(f"Running full loop for {urn}")
    success = False
    for url in urls:
        payload = json.dumps({"dataset_urn": urn, "simulate": True, "top_k": 3, "min_similarity": 0.60}).encode()
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.loads(r.read())
                print(f"Success on {url}!")
                print(f"Diagnosis: {res.get('diagnose', {}).get('severity')}")
                print(f"Write details:")
                print(json.dumps(res.get('write', {}), indent=2))
                success = True
                break
        except Exception as e:
            # only print if it's not a connection error (meaning wrong port)
            if "WinError 10061" not in str(e):
                print(f"Error on {url}: {e}")
    if not success:
        print("FAILED TO RUN ON ALL URLS")
    time.sleep(1)

