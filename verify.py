import urllib.request
import json

# 1. Check memories API
r = urllib.request.urlopen('http://localhost:8888/api/memories?limit=200')
data = json.load(r)
records = data.get('records', [])
print(f"=== /api/memories ===")
print(f"Total records: {len(records)}")
for rec in records[:10]:
    print(f"  [{rec['type']}] {rec['title']}")

# 2. Check /api/incidents (used by the graph)
r2 = urllib.request.urlopen('http://localhost:8888/api/incidents')
gdata = json.load(r2)
nodes = gdata.get('nodes', [])
edges = gdata.get('edges', [])
print(f"\n=== /api/incidents (graph data) ===")
print(f"Nodes: {len(nodes)}")
print(f"Edges: {len(edges)}")
for n in nodes[:5]:
    print(f"  Node: {n.get('id', '?')} - {n.get('title', '?')}")

# 3. Check health
r3 = urllib.request.urlopen('http://localhost:8888/health')
health = json.load(r3)
print(f"\n=== /health ===")
print(json.dumps(health, indent=2))
