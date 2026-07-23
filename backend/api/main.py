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

Start dev server:
  cd d:\\Anamnesis
  .venv\\Scripts\\uvicorn backend.api.main:app --reload --port 8888
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
except ImportError:
    raise RuntimeError("FastAPI not installed. Run: pip install fastapi uvicorn")

from backend.agents.detector import SchemaDetector
from backend.agents.diagnoser import Diagnoser
from backend.core.datahub_client import DataHubAdapter
from backend.core.memory_store import MemoryRecord, MemoryStore, MemoryType, get_store

app = FastAPI(
    title="Anamnesis",
    description="Persistent memory layer for AI data agents, built on DataHub",
    version="0.1.0",
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
    auto_capture_baseline: bool = True


class DiagnoseRequest(BaseModel):
    dataset_urn: str
    diff: Dict[str, Any]
    memory_id: Optional[str] = None


class DetectAndDiagnoseRequest(BaseModel):
    dataset_urn: str


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    dh_ok = _dh.health()
    return {
        "status": "ok" if dh_ok else "degraded",
        "datahub_connected": dh_ok,
        "memory_records": _store.count,
        "datahub_server": _dh.server,
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
    """Run schema detector for a dataset."""
    result = _detector.detect(
        dataset_urn=body.dataset_urn,
        auto_capture_baseline=body.auto_capture_baseline,
    )
    return result


@app.post("/api/diagnose")
def diagnose(body: DiagnoseRequest):
    """Run diagnoser for a detected schema diff."""
    result = _diagnoser.diagnose(
        dataset_urn=body.dataset_urn,
        diff=body.diff,
        memory_id=body.memory_id,
    )
    return result


@app.post("/api/detect-and-diagnose")
def detect_and_diagnose(body: DetectAndDiagnoseRequest):
    """Combined: detect schema changes + diagnose impact in one call."""
    detection = _detector.detect(dataset_urn=body.dataset_urn)

    if not detection.get("has_changes"):
        return {"detection": detection, "diagnosis": None}

    diagnosis = _diagnoser.diagnose(
        dataset_urn=body.dataset_urn,
        diff=detection["diff"],
        memory_id=detection.get("memory_id"),
    )
    return {"detection": detection, "diagnosis": diagnosis}
