# Anamnesis

**A persistent memory layer for AI data agents, built on DataHub.**

Every schema fix, every incident resolution, every agent decision becomes
institutional memory that future agents can query and reason over — instead
of every AI agent reasoning from zero, every time.

Built for [Build with DataHub: The Agent Hackathon](https://datahubproject.io) — 2026.

---

## The Problem

Every data team has felt this: a schema breaks, an engineer spends time tracing
the root cause through lineage, writes a fix — and that knowledge dies with the
conversation. Two months later, a different engineer (or AI agent) hits the same
class of problem and starts from zero again.

AI agents built on top of today's data stacks inherit this same amnesia. Without
persistent memory, every agent run reasons in isolation, with no access to what
was learned from the last hundred times this exact problem occurred.

## The Solution

Anamnesis is a 5-stage agent pipeline that turns every resolved data incident
into searchable, structured memory — written back directly into DataHub's graph:

1. **Detect** — watches DataHub for real schema changes against a captured baseline
2. **Diagnose** — traces the live DataHub lineage graph to find every downstream
   dataset, dashboard, and model actually affected
3. **Recall** — searches vector-embedded past incidents for genuinely similar
   breaks, ranked by real semantic similarity
4. **Fix** — generates a resolution from scratch when memory is empty, or adapts
   a prior fix instantly when a strong match exists
5. **Write** — persists the resolved incident back to DataHub as a structured
   `IncidentMemory` object — read-back verified, not just claimed

The result: the first time a problem occurs, the agent reasons from scratch.
The second time a similar problem occurs — anywhere in the org, on any dataset —
the agent recognizes it and resolves it in seconds, not minutes.

## Demo

[TO BE FILLED: Link to demo video — under 3 minutes]

[TO BE FILLED: Link to live/hosted demo if available, or clear local-setup pointer below]

### What you'll see in the demo:
- Incident 1: a schema break on `orders`, resolved from scratch (no prior memory)
- Incident 2: a related break on `customers`, instantly recalled from Incident 1's
  resolution (90.7% similarity — Strong Match)
- Incident 3: a different-pattern break on `products`, correctly recognized as
  related-but-distinct (87.7% and 84.5% similarities — Related Match)
- The Memory Constellation: a live, force-directed graph of every incident and
  its recall relationships, growing in real time as new incidents are resolved

## Understanding the Dashboard

The 4 stat cards on the Dashboard give an at-a-glance health snapshot of the
memory graph:

| Card | What it counts |
|---|---|
| **Total Memories** | Every record stored in DataHub's memory graph so far — the full count, regardless of type. |
| **Incidents** | Of those, how many are genuine resolved problems (`type = INCIDENT`) — schema breaks the pipeline actually diagnosed and fixed, as opposed to other record types like baseline captures. |
| **Schema Fixes** | Of those, how many carry the more specific `SCHEMA_FIX` tag — a narrower classification than a generic incident. This can legitimately read `0` if no record has been given that precise tag yet; it reflects real data state, not a bug. |
| **Resolved** | Of all records (any type), how many have been marked `RESOLVED` via the Memory view's status toggle — independent of category, this tracks whether the underlying issue was closed out. |

Each card is clickable and navigates to a filtered view of the Memory list
showing exactly the records it counted.

## Architecture

```text
┌─────────────┐   ┌──────────────┐   ┌───────────────┐   ┌─────────┐   ┌──────────────┐
│  detector.py│──▶│ diagnoser.py │──▶│   recall.py   │──▶│ fixer.py│──▶│memory_writer.py│
│    Agent    │   │    Agent     │   │     Agent     │   │  Agent  │   │    Agent     │
└─────────────┘   └──────────────┘   └───────────────┘   └─────────┘   └──────────────┘
       │                  │                   │                              │
       ▼                  ▼                   ▼                              ▼
              DataHub MCP Server — lineage, schema, vector search, write-back
                              │
                              ▼
                    DataHub Graph (IncidentMemory)
```

Every stage reads and/or writes through DataHub's MCP Server:
- **Read**: schema snapshots, lineage traversal, vector-indexed similarity search
- **Write**: a custom `IncidentMemory` structured object persisted back to the
  graph after every resolution, so the knowledge compounds with every run

## Tech Stack

- Backend: FastAPI, Python 3.10+
- Agent orchestration: LangChain / LangGraph
- LLM: Groq LLaMA
- Embeddings: Sentence-Transformers (sentence-transformers>=3.0.0, numpy>=1.24.0)
- Data platform: DataHub (MCP Server, Agent Context Kit - acryl-datahub)
- Frontend: Vanilla JS, Three.js, D3.js

## Setup

### Prerequisites
- Docker Desktop (for local DataHub) — see [DataHub docs](https://docs.datahub.com)
- Python 3.10+

### 1. Clone and install
```bash
git clone https://github.com/AmitK241/Anamnesis.git
cd Anamnesis
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
```

### 2. Start DataHub locally
```bash
pip install acryl-datahub
datahub docker quickstart
datahub datapack load showcase-ecommerce
```

### 3. Configure environment
Create `.env` in the project root:
```
DATAHUB_GMS_SERVER=http://localhost:8080
DATAHUB_GMS_TOKEN=<your personal access token from DataHub UI Settings>
```

### 4. Run the backend
```bash
cd backend
uvicorn api.main:app --reload --port 8888
```

### 5. Run the frontend
```bash
cd frontend
python3 -m http.server 3000
```
*(The frontend runs on `http://localhost:3000`, communicating with the backend on port `8888`)*

### 6. (Optional) Seed the demo scenario
```bash
python -m backend.seed_demo_data
```

Then open `http://localhost:3000`.

## Project Structure

```
Anamnesis/
├── backend/
│   ├── agents/
│   │   ├── detector.py
│   │   ├── diagnoser.py
│   │   ├── fixer.py
│   │   ├── memory_writer.py
│   │   └── recall.py
│   ├── api/
│   │   └── main.py
│   ├── core/
│   │   ├── datahub_client.py
│   │   └── memory_store.py
│   └── seed_demo_data.py
├── frontend/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── memory-graph.js
│   └── cubes-bg.js
├── docs/
│   ├── demo_script.md
│   └── demo_urns.md
├── examples/
│   └── sample_schema_diff.json
└── README.md
```

## Roadmap

This hackathon submission focuses on two memory types (schema-break
resolution and cross-incident recall) to keep the demo tight and fully
verified end-to-end. The same `IncidentMemory` framework is designed to
extend to:

- **PR-review memory** — recalling how similar code changes were reviewed
  and what concerns were raised previously
- **ML-drift memory** — connecting upstream schema/data changes to
  downstream model performance degradation, using DataHub's ML lineage
- **Migration memory** — recalling how similar schema migrations were
  planned and executed previously

The core write-back pattern (structured memory objects persisted to
DataHub's graph, recalled via vector search) generalizes to any DataHub
Agent Context Kit workflow, not just schema incidents.

## License

Apache 2.0 — see [LICENSE.md](LICENSE.md)

## Team / Author

Amit Kumar (GitHub: AmitK241)
