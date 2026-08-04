"""Test whether the GraphQL _exists_ filter works for incidentMemory aspect."""
import json
import os
import urllib.request

server = os.getenv("DATAHUB_GMS_SERVER", "http://localhost:8080")

gql = """
query {
  searchAcrossEntities(input: {
    types: [DATASET]
    query: "*"
    count: 10
    filters: [{field: "_exists_", values: ["incidentMemory"]}]
  }) {
    searchResults {
      entity { urn }
    }
  }
}
"""

payload = json.dumps({"query": gql}).encode()
req = urllib.request.Request(
    f"{server}/api/graphql",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    results = data.get("data", {}).get("searchAcrossEntities", {}).get("searchResults", [])
    print(f"_exists_ filter returned {len(results)} result(s):")
    for r in results:
        print(f"  {r['entity']['urn']}")
    if "errors" in data:
        print("GraphQL errors:", data["errors"])
except Exception as e:
    print(f"Error: {e}")
