"""
Step 7 smoke test: Verify LangChain can query DataHub.
Run from project root: python backend/verify_setup.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

DATAHUB_GMS_SERVER = os.getenv("DATAHUB_GMS_SERVER", "http://localhost:8080")
DATAHUB_GMS_TOKEN = os.getenv("DATAHUB_GMS_TOKEN", "")

print(f"Connecting to DataHub GMS at: {DATAHUB_GMS_SERVER}")

# ── 1. Test raw HTTP connectivity ─────────────────────────────────────────────
import urllib.request

try:
    req = urllib.request.urlopen(f"{DATAHUB_GMS_SERVER}/health", timeout=5)
    print(f"✅ GMS /health → {req.status}")
except Exception as e:
    print(f"❌ Cannot reach GMS at {DATAHUB_GMS_SERVER}: {e}")
    print("   Make sure 'datahub docker quickstart' has finished and all containers are healthy.")
    sys.exit(1)

# ── 2. DataHub Python SDK client ──────────────────────────────────────────────
try:
    from datahub.sdk.main_client import DataHubClient

    client = DataHubClient(
        server=DATAHUB_GMS_SERVER,
        token=DATAHUB_GMS_TOKEN or None,
    )
    print("✅ DataHubClient initialised")
except ImportError as e:
    print(f"⚠️  DataHubClient not importable: {e}")
    print("   Try: pip install 'acryl-datahub[datahub-rest]'")
    client = None

# ── 3. Agent Context / LangChain tools (optional, SDK is evolving) ────────────
try:
    from datahub_agent_context.langchain_tools import build_langchain_tools  # type: ignore

    if client:
        tools = build_langchain_tools(client, include_mutations=False)
        print(f"✅ {len(tools)} LangChain tools available:")
        for t in tools:
            print(f"   - {t.name}: {t.description[:80]}")

        # Quick search test
        search_tool = next((t for t in tools if "search" in t.name.lower()), None)
        if search_tool:
            result = search_tool.run("orders")
            print("\n✅ Search test result (first 500 chars):")
            print(str(result)[:500])
        else:
            print("⚠️  No search tool found in the tool list")
except ImportError:
    print("⚠️  datahub_agent_context not installed – skipping LangChain tool test")
    print("   Will add: pip install datahub-agent-context")

# ── 4. Direct GraphQL search as fallback ─────────────────────────────────────
import json
import urllib.request

headers = {"Content-Type": "application/json"}
if DATAHUB_GMS_TOKEN:
    headers["Authorization"] = f"Bearer {DATAHUB_GMS_TOKEN}"

search_gql = json.dumps({
    "query": """
    {
      search(input: { type: DATASET, query: "orders", start: 0, count: 3 }) {
        count
        searchResults { entity { urn type } }
      }
    }
    """
}).encode()

try:
    req = urllib.request.Request(
        f"{DATAHUB_GMS_SERVER}/api/graphql",
        data=search_gql,
        headers=headers,
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read())
    hits = data.get("data", {}).get("search", {}).get("count", 0)
    print(f"\n✅ GraphQL search for 'orders' → {hits} results")
    if hits > 0:
        for r in data["data"]["search"]["searchResults"]:
            print(f"   {r['entity']['urn']}")
except Exception as e:
    print(f"⚠️  GraphQL search failed: {e}")

print("\nDone.")
