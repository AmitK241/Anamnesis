# Anamnesis 🧠

> **A persistent memory layer for AI data agents, built on DataHub.**
>
> Every schema fix, every incident resolution, every agent decision becomes
> institutional memory that future agents can query and reason over.

Built for the **DataHub Agent Hackathon 2026**.

---

## The Problem

AI data agents suffer from institutional amnesia. Every time a schema breaks, an agent:
1. Re-investigates the same root cause from scratch
2. Misses the fix that worked last time
3. Wastes engineering hours on solved problems

Anamnesis solves this by giving agents **persistent, queryable memory**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Anamnesis Stack                      │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │
│  │ Detector │→ │Diagnoser │→ │  Recall  │→ │ Fixer  │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────┘  │
│       ↓              ↓              ↓            ↓       │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Memory Store (JSON)                  │   │
│  │   INCIDENT | SCHEMA_FIX | DECISION | LESSON      │   │
│  └──────────────────────────────────────────────────┘   │
│                         ↕                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │        DataHub GMS (lineage + schema source)      │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Agent Pipeline

| Agent | Role | Output |
|-------|------|--------|
| **SchemaDetector** | Compares current schema vs. baseline; detects missing fields, type changes, and new additions | `has_break`, `missing_fields`, `type_changes`, `severity` |
| **Diagnoser** | Traverses DataHub lineage to find upstream sources + downstream consumers; searches memory for past fixes | `root_cause`, `downstream_impact`, `diagnosis_confidence` |
| **MemoryRecallAgent** | Embeds the diagnosis into a vector (all-MiniLM-L6-v2) and finds semantically similar past incidents via cosine similarity | `matches[]` with `similarity_score` |
| **FixerAgent** | If a high-similarity past incident is found (≥85%), adapts its fix; otherwise generates a fresh fix via Groq LLM | `suggested_fix`, `mode`, `estimated_time_saved_minutes` |

---

## Quick Start

### Prerequisites

- Python 3.10+
- DataHub running locally (optional — simulation mode works without it)
- `GROQ_API_KEY` in `.env` (for the Fixer agent LLM calls)

### Install

```bash
git clone https://github.com/<you>/anamnesis.git
cd anamnesis

# Create venv and install dependencies
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r backend/requirements.txt
```

### Configure

```bash
# Create .env in project root
echo GROQ_API_KEY=gsk_your_key_here > .env
echo DATAHUB_GMS_SERVER=http://localhost:8080 >> .env
```

### Run the API Server

```bash
.venv\Scripts\python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8888 --reload
```

### Open the Dashboard

Open `frontend/index.html` in your browser. The UI connects to the API at `http://localhost:8888`.

### Run the Offline Demo

Demonstrates the full memory loop without any DataHub or cloud dependency:

```bash
.venv\Scripts\python -m backend.demo_scenario
```

Expected output:
```
============================================================
  ANAMNESIS DEMO - Schema Break Memory Loop
============================================================

[>>] Step 1: Capturing schema baseline for 'orders' dataset...
   [OK] Baseline captured (5 fields)

[>>] Step 2: Running SchemaDetector (schema break injected)...
   has_changes : True
   is_breaking : True
   diff summary: 1 field(s) removed: ['currency']; 1 field(s) added
   memory_id   : <uuid>

[>>] Step 3: Running Diagnoser (lineage traversal + memory search)...
   downstream_count : 2
   past_fixes_found : 0
   incident_memory_id: <uuid>

   Remediation Plan:
      WARNING: 2 downstream consumer(s) affected: revenue_dashboard, orders_monthly
      CRITICAL: Removed field 'currency' → notify downstream owners.
      ...

[>>] Step 4: Querying Anamnesis memory...
   Total records in memory: 3

[>>] Step 5: Marking incident as resolved...
   [OK] Incident <uuid>... is now resolved=True

============================================================
  ✅ Anamnesis demo complete – memory layer working!
============================================================
```

---

## API Reference

The FastAPI server exposes these endpoints (port 8888 by default):

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check + DataHub connectivity |
| GET | `/api/memories` | List all memory records (filterable) |
| POST | `/api/memories` | Create a new memory record |
| PATCH | `/api/memories/{id}` | Update a memory record |
| DELETE | `/api/memories/{id}` | Delete a memory record |
| POST | `/api/detect` | Detect schema breaks for a dataset |
| POST | `/api/diagnose` | Diagnose a detected schema break |
| POST | `/api/detect-and-diagnose` | Combined one-shot endpoint |
| POST | `/api/recall` | Find similar past incidents by embedding |
| POST | `/api/fix` | Generate a fix suggestion via Groq LLM |

Full interactive docs: `http://localhost:8888/docs`

---

## Verification Scripts

Run these to verify each agent independently:

```bash
# Verify SchemaDetector (requires API server + optionally DataHub)
.venv\Scripts\python backend/verify_detector.py

# Verify Diagnoser
.venv\Scripts\python backend/verify_diagnoser.py

# Verify Memory Recall (requires DataHub running to seed test aspects)
.venv\Scripts\python backend/verify_recall.py

# Verify Fixer (requires GROQ_API_KEY)
.venv\Scripts\python backend/verify_fixer.py

# Verify custom DataHub aspect round-trip (requires DataHub)
.venv\Scripts\python backend/verify_incident_memory.py
```

---

## Project Structure

```
anamnesis/
├── backend/
│   ├── agents/
│   │   ├── detector.py         # SchemaDetector: change detection
│   │   ├── diagnoser.py        # Diagnoser: root cause + lineage
│   │   ├── recall.py           # MemoryRecallAgent: semantic search
│   │   └── fixer.py            # FixerAgent: LLM-powered fix generation
│   ├── api/
│   │   └── main.py             # FastAPI application
│   ├── core/
│   │   ├── datahub_client.py   # DataHub GraphQL/REST adapter
│   │   ├── memory_store.py     # JSON-backed memory store
│   │   └── embeddings.py       # Sentence-transformer embedding helpers
│   ├── demo_scenario.py        # Offline demo (no DataHub needed)
│   └── requirements.txt
├── frontend/
│   ├── index.html              # Dashboard UI
│   ├── style.css               # Styles
│   └── app.js                  # Frontend logic
├── metadata-models-custom/     # Custom DataHub aspect: incidentMemory
└── docs/
    └── demo_urns.md
```

---

## Custom DataHub Aspect

Anamnesis defines a custom `incidentMemory` aspect for DataHub entities:

```json
{
  "incidentId": "INC-2026-001",
  "rootCause": "fulfillment_status field dropped from orders table",
  "downstreamImpact": ["urn:li:dataset:(...)"],
  "resolutionCodeDiff": "--- a/pipeline.py\n+++ b/pipeline.py\n...",
  "embeddingVector": [0.023, -0.041, ...],  // 384-dim MiniLM vector
  "timeSavedEstimate": 120,
  "timestamp": 1753862400000
}
```

This aspect is stored in DataHub alongside the dataset entity, making it queryable via DataHub's existing search and lineage APIs.

---

## How Memory Recall Works

1. **Embedding** — When an incident is diagnosed, Anamnesis encodes the root cause + field names into a 384-dimensional vector using `all-MiniLM-L6-v2`
2. **Storage** — The vector is stored alongside the incident in the `incidentMemory` aspect
3. **Query** — When a new break occurs, the new diagnosis is embedded and compared to all stored vectors using cosine similarity
4. **Threshold** — Matches with similarity ≥ 0.85 are used to adapt historical fixes (reducing resolution time)
5. **Fresh generation** — If no similar incident exists, the Fixer generates a fresh fix via Groq LLM

---

## Built With

- [DataHub](https://datahubproject.io/) — Knowledge graph for lineage and metadata
- [FastAPI](https://fastapi.tiangolo.com/) — REST API layer
- [Sentence Transformers](https://www.sbert.net/) — `all-MiniLM-L6-v2` for embeddings
- [Groq](https://groq.com/) — Fast LLM inference for fix generation
- [LangChain](https://www.langchain.com/) — Agent orchestration

---

## License

MIT
