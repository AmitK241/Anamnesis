"""
Anamnesis – FastAPI Application
================================

REST API for querying and managing the Anamnesis memory layer.

Endpoints:
  GET  /health                       – Health check (DataHub + memory store)
  GET  /api/memories                 – List/search stored memories
  GET  /api/memories/{id}            – Get a single memory record
  POST /api/memories                 – Manually add a memory record
  PATCH /api/memories/{id}           – Update a memory record (e.g. mark resolved)
  DELETE /api/memories/{id}          – Delete a memory record

  POST /api/detect                   – Run schema detector for a dataset
  POST /api/diagnose                 – Run diagnoser for a detected diff
  POST /api/detect-and-diagnose      – Combined one-shot endpoint
  POST /api/recall                   – Find semantically similar past incidents
  POST /api/fix                      – Generate a fix for a detected schema break
  POST /api/write-memory             – Write pipeline output as IncidentMemory to DataHub
  POST /api/full-loop                – Run ENTIRE pipeline in one call (demo magic button)

  GET  /                             – Anamnesis dashboard (frontend)

Start dev server:
  cd d:\\Anamnesis
  .venv\\Scripts\\uvicorn backend.api.main:app --reload --port 8888
  Then open: http://localhost:8888
"""

from __future__ import annotations

import logging
import os
import pathlib
import urllib.request
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
except ImportError:
    raise RuntimeError("FastAPI not installed. Run: pip install fastapi uvicorn")

from backend.agents.detector import SchemaDetector
from backend.agents.diagnoser import Diagnoser
from backend.agents.fixer import FixerAgent
from backend.agents.memory_writer import MemoryWriterAgent
from backend.agents.recall import MemoryRecallAgent
from backend.core.datahub_client import DataHubAdapter
from backend.core.memory_store import MemoryRecord, MemoryStore, MemoryType, get_store

os.environ["OMP_NUM_THREADS"] = "1"

@asynccontextmanager
async def lifespan(app_: FastAPI):
    """Lifecycle hooks (currently empty)."""
    yield


app = FastAPI(
    title="Anamnesis",
    description="Persistent memory layer for AI data agents, built on DataHub",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── singletons ────────────────────────────────────────────────────────────────

_store: MemoryStore = get_store()
_dh: DataHubAdapter = DataHubAdapter()
_detector: SchemaDetector = SchemaDetector(datahub=_dh, store=_store)
_diagnoser: Diagnoser = Diagnoser(datahub=_dh, store=_store)
_recall: MemoryRecallAgent = MemoryRecallAgent(datahub=_dh)
_fixer: FixerAgent = FixerAgent()
_writer: MemoryWriterAgent = MemoryWriterAgent()


# ── pydantic models ───────────────────────────────────────────────────────────

class MemoryIn(BaseModel):
    type: str = "INCIDENT"
    entity_urn: str = ""
    title: str
    summary: str = ""
    detail: Dict[str, Any] = {}
    tags: List[str] = []
    severity: str = "LOW"
    agent_id: str = "anamnesis"


class MemoryPatch(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    severity: Optional[str] = None
    resolved: Optional[bool] = None


class DetectRequest(BaseModel):
    dataset_urn: str
    # Supply a {field_name: type_string} dict to run detect_schema_break().
    # Leave empty to use the legacy in-memory-baseline detect() path.
    known_good_schema: Optional[Dict[str, str]] = None
    # Set to True to run the built-in demo simulation (ignores known_good_schema).
    simulate: bool = False
    auto_capture_baseline: bool = True


class DiagnoseRequest(BaseModel):
    # New-style: pass the detection_result dict from /api/detect directly.
    detection_result: Optional[Dict[str, Any]] = None
    # Legacy-style: pass dataset_urn + diff dict manually.
    dataset_urn: Optional[str] = None
    diff: Optional[Dict[str, Any]] = None
    memory_id: Optional[str] = None


class DetectAndDiagnoseRequest(BaseModel):
    dataset_urn: str


class RecallRequest(BaseModel):
    # Option A: pass a pre-computed diagnosis dict directly
    diagnosis: Optional[Dict[str, Any]] = None
    # Option B: re-run detect+diagnose for this dataset, then recall
    dataset_urn: Optional[str] = None
    simulate: bool = False
    # Recall tuning params
    top_k: int = 3
    min_similarity: float = 0.75


class FixRequest(BaseModel):
    # Option A: pass pre-computed dicts from prior pipeline stages
    diagnosis: Optional[Dict[str, Any]] = None
    recall_result: Optional[Dict[str, Any]] = None
    # Option B: run the full pipeline (detect -> diagnose -> recall -> fix)
    dataset_urn: Optional[str] = None
    simulate: bool = False
    # Recall tuning params (only used in Option B)
    top_k: int = 3
    min_similarity: float = 0.75


class WriteMemoryRequest(BaseModel):
    """Pass all four pipeline stage outputs to write an IncidentMemory to DataHub."""
    detection: Dict[str, Any]
    diagnosis: Dict[str, Any]
    recall_result: Dict[str, Any]
    fix_result: Dict[str, Any]


class FullLoopRequest(BaseModel):
    """Single-call demo endpoint — runs the ENTIRE pipeline end-to-end."""
    dataset_urn: str
    simulate: bool = True          # always True for demo; set False for live detection
    top_k: int = 3
    min_similarity: float = 0.75


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
@app.get("/api/status")
@app.get("/health")
def health_check():
    # Try 127.0.0.1 first, then localhost fallback
    urls = ["http://127.0.0.1:8080/health", "http://localhost:8080/health"]
    is_up = False
    
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    is_up = True
                    break
        except Exception as e:
            continue

    # Return standardized response for frontend matcher
    return {
        "connected": is_up,
        "status": "connected" if is_up else "offline",
        "datahub": "UP" if is_up else "DOWN",
        "message": "DataHub GMS active" if is_up else "DataHub GMS offline"
    }


@app.get("/api/memories")
def list_memories(
    entity_urn: Optional[str] = None,
    memory_type: Optional[str] = None,
    tag: Optional[str] = None,
    resolved: Optional[bool] = None,
    q: Optional[str] = None,
    limit: int = 50,
):
    """List or search memory records."""
    if q:
        records = _store.search(q, limit=limit)
    else:
        mem_type = MemoryType(memory_type) if memory_type else None
        tags = [tag] if tag else None
        records = _store.query(
            entity_urn=entity_urn,
            memory_type=mem_type,
            tags=tags,
            resolved=resolved,
            limit=limit,
        )
    return {"count": len(records), "records": [r.to_dict() for r in records]}


@app.get("/api/memories/{record_id}")
def get_memory(record_id: str):
    rec = _store.get(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Memory record not found")
    return rec.to_dict()


@app.post("/api/memories", status_code=201)
def create_memory(body: MemoryIn):
    record = MemoryRecord(
        type=MemoryType(body.type),
        entity_urn=body.entity_urn,
        title=body.title,
        summary=body.summary,
        detail=body.detail,
        tags=body.tags,
        severity=body.severity,
        agent_id=body.agent_id,
    )
    mem = _store.add(record)
    return mem.to_dict()


@app.patch("/api/memories/{record_id}")
def patch_memory(record_id: str, body: MemoryPatch):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    rec = _store.update(record_id, **updates)
    if not rec:
        raise HTTPException(status_code=404, detail="Memory record not found")
    return rec.to_dict()


@app.delete("/api/memories/{record_id}", status_code=204)
def delete_memory(record_id: str):
    ok = _store.delete(record_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory record not found")


@app.post("/api/detect")
def detect(body: DetectRequest):
    """
    Run the schema detector for a dataset.  Three modes:

    1. simulate=true  — built-in demo: fetches live schema and artificially
                        injects two dropped fields + one type-change.
    2. known_good_schema provided — compare live schema against the supplied
                        baseline dict {field_name: type_string}.
    3. neither         — legacy mode: compare against a previously captured
                        in-memory baseline (auto-captures on first call).
    """
    if body.simulate:
        result = _detector.simulate_schema_break(dataset_urn=body.dataset_urn)
    elif body.known_good_schema:
        result = _detector.detect_schema_break(
            dataset_urn=body.dataset_urn,
            known_good_schema=body.known_good_schema,
        )
    else:
        result = _detector.detect(
            dataset_urn=body.dataset_urn,
            auto_capture_baseline=body.auto_capture_baseline,
        )
    return result


@app.post("/api/diagnose")
def diagnose(body: DiagnoseRequest):
    """
    Run the Diagnoser for a detected schema break.  Two modes:

    1. detection_result provided — new-style: pass the full dict from /api/detect.
       Returns: {root_cause, upstream_sources, downstream_impact, ...}

    2. dataset_urn + diff provided — legacy-style: accepts the old diff dict format.
       Returns: {diff_summary, downstream_entities, remediation_plan, ...}
    """
    if body.detection_result:
        result = _diagnoser.diagnose(body.detection_result)
    elif body.dataset_urn and body.diff is not None:
        result = _diagnoser.diagnose(
            dataset_urn=body.dataset_urn,
            diff=body.diff,
            memory_id=body.memory_id,
        )
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either 'detection_result' or both 'dataset_urn' and 'diff'.",
        )
    return result


@app.post("/api/detect-and-diagnose")
def detect_and_diagnose(body: DetectAndDiagnoseRequest):
    """Combined: simulate a schema break on the dataset, then diagnose it."""
    detection = _detector.simulate_schema_break(dataset_urn=body.dataset_urn)

    if not detection.get("has_break") and not detection.get("has_changes"):
        return {"detection": detection, "diagnosis": None}

    diagnosis = _diagnoser.diagnose(detection)
    return {"detection": detection, "diagnosis": diagnosis}


@app.post("/api/recall")
def recall(body: RecallRequest):
    """
    Find semantically similar past incidents using embeddings + cosine similarity.

    Two modes:

    1. ``diagnosis`` provided — use it directly as the query. Must contain at
       least ``root_cause`` (str); optionally ``missing_fields`` and
       ``type_changes`` for richer embeddings.

    2. ``dataset_urn`` provided (+ optional ``simulate=true``) — runs the
       Schema Detector (simulate mode) followed by the Diagnoser to build the
       diagnosis automatically, then performs recall.

    Returns top-k past incidents above ``min_similarity`` threshold (cosine),
    sorted descending by similarity score.  An empty match list with
    ``no_similar_incidents_found: true`` is returned when no past incidents
    exist or none clear the threshold — this is not an error condition.
    """
    if body.diagnosis is not None:
        diagnosis = body.diagnosis
    elif body.dataset_urn:
        # Run detect → diagnose first
        if body.simulate:
            detection = _detector.simulate_schema_break(dataset_urn=body.dataset_urn)
        else:
            detection = _detector.detect(
                dataset_urn=body.dataset_urn,
                auto_capture_baseline=True,
            )

        if not detection.get("has_break") and not detection.get("has_changes"):
            # No schema break — still run recall with a minimal diagnosis so
            # the caller gets a consistent response shape.
            diagnosis = {
                "dataset_urn": body.dataset_urn,
                "root_cause":  "No schema break detected.",
                "missing_fields": [],
                "type_changes": [],
            }
        else:
            diagnosis = _diagnoser.diagnose(detection)
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either 'diagnosis' dict or 'dataset_urn'.",
        )

    return _recall.recall_similar_incidents(
        diagnosis=diagnosis,
        top_k=body.top_k,
        min_similarity=body.min_similarity,
    )


@app.post("/api/fix")
def fix(body: FixRequest):
    """
    Generate a concrete fix suggestion for a detected schema break.

    Two call modes:

    **Option A** — pass pre-computed pipeline outputs directly::

        {
          "diagnosis": {...},       # from /api/diagnose
          "recall_result": {...}    # from /api/recall  (may be empty / no-matches)
        }

    **Option B** — run the full pipeline in one call::

        {
          "dataset_urn": "urn:li:dataset:...",
          "simulate": true,         # use built-in schema-break simulation
          "top_k": 3,
          "min_similarity": 0.75
        }

    Returns::

        {
          "mode": "adapted" | "generated_fresh",
          "suggested_fix": str,
          "based_on_incident_id": str | null,
          "confidence_note": str,
          "estimated_time_saved_minutes": int | null
        }
    """
    # ── Resolve diagnosis and recall_result ─────────────────────────────────
    if body.diagnosis is not None and body.recall_result is not None:
        # Option A: both supplied directly — use as-is
        diagnosis     = body.diagnosis
        recall_result = body.recall_result

    elif body.dataset_urn:
        # Option B: run the full pipeline
        if body.simulate:
            detection = _detector.simulate_schema_break(dataset_urn=body.dataset_urn)
        else:
            detection = _detector.detect(
                dataset_urn=body.dataset_urn,
                auto_capture_baseline=True,
            )

        if not detection.get("has_break") and not detection.get("has_changes"):
            diagnosis = {
                "dataset_urn": body.dataset_urn,
                "root_cause":  "No schema break detected.",
                "missing_fields": [],
                "type_changes": [],
            }
        else:
            diagnosis = _diagnoser.diagnose(detection)

        recall_result = _recall.recall_similar_incidents(
            diagnosis=diagnosis,
            top_k=body.top_k,
            min_similarity=body.min_similarity,
        )

    elif body.diagnosis is not None:
        # Partial Option A: diagnosis supplied, no recall_result — treat as no matches
        diagnosis = body.diagnosis
        recall_result = {
            "matches": [],
            "no_similar_incidents_found": True,
            "total_past_incidents_checked": 0,
        }

    else:
        raise HTTPException(
            status_code=422,
            detail=(
                "Provide either ('diagnosis' + 'recall_result') "
                "or 'dataset_urn' to run the full pipeline."
            ),
        )

    # ── Generate fix ─────────────────────────────────────────────────────────
    try:
        return _fixer.generate_fix(diagnosis=diagnosis, recall_result=recall_result)
    except RuntimeError as exc:
        # Propagate GROQ_API_KEY-not-set as a clear 503 with the hint
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/write-memory")
def write_memory(body: WriteMemoryRequest):
    """
    Write the full pipeline output into DataHub as a new IncidentMemory aspect.

    Accepts the four pipeline stage outputs directly (detection, diagnosis,
    recall_result, fix_result) and returns a write-confirmation result
    including the generated incident_id and a round-trip read-back
    verification flag.

    This closes the loop: the new incident is immediately discoverable by
    future recall calls against similar schema breaks.

    Returns::

        {
            "success":      bool,
            "incident_id":  str,
            "dataset_urn":  str,
            "written_at":   int,   # epoch millis
            "verification": str    # "confirmed via read-back" or error detail
        }
    """
    try:
        return _writer.write_incident_memory(
            detection=body.detection,
            diagnosis=body.diagnosis,
            recall_result=body.recall_result,
            fix_result=body.fix_result,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/full-loop")
def full_loop(body: FullLoopRequest):
    """
    **Demo magic-button endpoint** — runs the ENTIRE Anamnesis pipeline in a
    single API call and returns all five stage outputs together.

    Pipeline stages (in order):
    1. **Detect**       — simulate (or live-detect) a schema break on ``dataset_urn``.
    2. **Diagnose**     — build root-cause narrative + lineage blast radius.
    3. **Recall**       — find semantically similar past incidents via embeddings.
    4. **Fix**          — generate a concrete fix (adapted or fresh via Groq LLM).
    5. **Write-memory** — persist the new incident back into DataHub.

    Returns::

        {
            "detection":    {...},
            "diagnosis":    {...},
            "recall":       {...},
            "fix":          {...},
            "write_memory": {
                "success":      bool,
                "incident_id":  str,
                "dataset_urn":  str,
                "written_at":   int,
                "verification": str
            }
        }
    """
    # ── Stage 1: Detect ───────────────────────────────────────────────────────
    if body.simulate:
        detection = _detector.simulate_schema_break(dataset_urn=body.dataset_urn)
    else:
        detection = _detector.detect(
            dataset_urn=body.dataset_urn,
            auto_capture_baseline=True,
        )

    # ── Stage 2: Diagnose ─────────────────────────────────────────────────────
    # detect_schema_break/simulate_schema_break return has_break (new-style);
    # legacy detect() returns has_changes — check both so the pipeline is
    # correct regardless of which detection mode was used.
    if detection.get("has_break") or detection.get("has_changes"):
        diagnosis = _diagnoser.diagnose(detection)
        # Ensure missing_fields / type_changes are always present on diagnosis
        if "missing_fields" not in diagnosis:
            diagnosis["missing_fields"] = detection.get("missing_fields", [])
        if "type_changes" not in diagnosis:
            diagnosis["type_changes"] = detection.get("type_changes", [])
    else:
        diagnosis = {
            "dataset_urn":          body.dataset_urn,
            "root_cause":           "No schema break detected.",
            "missing_fields":       [],
            "type_changes":         [],
            "downstream_impact":    [],
            "diagnosis_confidence": "low",
            "break_summary":        "No breaks detected",
        }

    # ── Stage 3: Recall ───────────────────────────────────────────────────────
    recall_result = _recall.recall_similar_incidents(
        diagnosis=diagnosis,
        top_k=body.top_k,
        min_similarity=body.min_similarity,
    )

    # ── Stage 4: Fix ──────────────────────────────────────────────────────────
    try:
        fix_result = _fixer.generate_fix(
            diagnosis=diagnosis,
            recall_result=recall_result,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # ── Stage 5: Write-memory ─────────────────────────────────────────────────
    # Skip the write when no break was detected.  Writing a hollow IncidentMemory
    # (empty root_cause, no missing fields, no fix) is semantically meaningless
    # and causes DataHub to return HTTP 500 when the entity URN is also empty
    # (which it always is for the legacy detect() path that doesn't include
    # dataset_urn in its output dict).
    no_break = (
        not detection.get("has_break")
        and not detection.get("has_changes")
    )
    if no_break:
        write_result = {
            "success":      False,
            "incident_id":  None,
            "dataset_urn":  body.dataset_urn,
            "written_at":   None,
            "verification": "skipped — no schema break was detected; nothing meaningful to persist",
        }
    else:
        write_result = _writer.write_incident_memory(
            detection=detection,
            diagnosis=diagnosis,
            recall_result=recall_result,
            fix_result=fix_result,
        )

    return {
        "detection":    detection,
        "diagnosis":    diagnosis,
        "recall":       recall_result,
        "fix":          fix_result,
        "write_memory": write_result,
    }


@app.get("/api/incidents")
@app.get("/api/graph")
@app.get("/api/constellation")
def get_incidents_graph():
    """
    Returns the Memory Constellation graph — all IncidentMemory records from
    DataHub as force-directed graph nodes + edges derived from their stored
    embedding vectors (cosine similarity, same math as the recall agent).
    """
    import math
    from backend.core.memory_store import get_store

    # Read directly from local MemoryStore as primary source
    store = get_store()
    # Ensure we use memory store records
    records = []
    for rec in store.all():
        if rec.type.name == "INCIDENT":
            detail = rec.detail or {}
            records.append({
                "incident_id": rec.id,
                "dataset_urn": rec.entity_urn,
                "timestamp": rec.created_at * 1000,
                "embedding_vector": detail.get("embedding_vector", []),
                "severity": rec.severity,
                "title": rec.title,
                "type": rec.type.name
            })

    # ── Build nodes ───────────────────────────────────────────────────────────
    def _dataset_short(urn: str) -> str:
        """Extract the middle table-path segment from a DataHub URN."""
        parts = urn.split(",")
        if len(parts) >= 2:
            path = parts[1].strip()
            return path.split(".")[-1] if "." in path else path
        return urn

    nodes = [
        {
            "id":          r["incident_id"],
            "dataset":     _dataset_short(r["dataset_urn"]),
            "dataset_urn": r["dataset_urn"],
            "timestamp_ms": r["timestamp"],
            "severity":    r["severity"],
            "title":       r["title"],
            "type":        r["type"]
        }
        for r in records
        if r.get("incident_id")
    ]

    # ── Build edges via pairwise cosine similarity ────────────────────────────
    def _cosine(a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    def _sim_label(sim: float) -> str:
        if sim >= 0.90:
            return "Strong Match"
        if sim >= 0.80:
            return "Related Match"
        if sim >= 0.65:
            return "Possible Match"
        return "Weak Match"

    MIN_EDGE_SIM = 0.70
    edges = []
    for i, a in enumerate(records):
        for b in records[i + 1:]:
            if not a.get("incident_id") or not b.get("incident_id"):
                continue
            sim = _cosine(a.get("embedding_vector", []), b.get("embedding_vector", []))
            if sim >= MIN_EDGE_SIM:
                edges.append({
                    "source":     a["incident_id"],
                    "target":     b["incident_id"],
                    "similarity": round(sim, 4),
                    "label":      _sim_label(sim),
                })

    # Sort edges strongest-first for stable rendering
    edges.sort(key=lambda e: e["similarity"], reverse=True)

    if not nodes:
        nodes = []
        edges = []

    return {"nodes": nodes, "edges": edges, "memories": records, "count": len(records)}


# ── Static file serving (frontend dashboard) ─────────────────────────────────
# Mount the entire frontend/ directory at "/" so index.html's relative asset
# references (href="style.css", src="app.js") resolve at their natural paths
# without any prefix — no changes needed to index.html.
#
# Routing safety: all @app.get / @app.post routes defined above are registered
# first in Starlette's route table and always matched before this mount.
# Requests to /api/*, /health, /docs, /openapi.json etc. are unaffected.
# Only paths that match no explicit route fall through to this StaticFiles handler.
#
# html=True makes StaticFiles serve index.html automatically for GET /
# so no separate "serve_dashboard" route is required.

_FRONTEND_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend"

if _FRONTEND_DIR.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(_FRONTEND_DIR), html=True),
        name="frontend",
    )
    logger.info("Frontend mounted from %s at /", _FRONTEND_DIR)
else:
    logger.warning(
        "Frontend directory not found at %s — dashboard unavailable", _FRONTEND_DIR
    )
