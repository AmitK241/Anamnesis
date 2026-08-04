# -*- coding: utf-8 -*-
from __future__ import annotations
"""
Anamnesis – Demo Scenario Script
===================================

Simulates a schema-break incident on a DataHub dataset to demonstrate the
full Anamnesis memory loop:

  1. Capture baseline schema for the 'orders' dataset
  2. Simulate a breaking change (field removal)
  3. Detect the change via SchemaDetector
  4. Diagnose impact via Diagnoser (lineage traversal + memory search)
  5. Show how future agents can query the memory to avoid repeat mistakes

Run:
    .venv\\Scripts\\python backend/demo_scenario.py
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import json
import logging
import time
from unittest.mock import MagicMock, patch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _make_mock_datahub(with_lineage: bool = True):
    """Create a mock DataHub adapter for offline demo."""
    dh = MagicMock()
    dh.health.return_value = True

    # Baseline schema: orders table with 5 fields
    baseline_fields = [
        {"fieldPath": "order_id",      "type": "STRING",  "description": "Primary key"},
        {"fieldPath": "customer_id",   "type": "STRING",  "description": "FK to customers"},
        {"fieldPath": "amount",        "type": "NUMBER",  "description": "Order total"},
        {"fieldPath": "currency",      "type": "STRING",  "description": "ISO 4217 currency code"},
        {"fieldPath": "created_at",    "type": "STRING",  "description": "Timestamp"},
    ]

    # "Current" schema after a breaking change: 'currency' field was removed!
    current_fields = [
        {"fieldPath": "order_id",      "type": "STRING",  "description": "Primary key"},
        {"fieldPath": "customer_id",   "type": "STRING",  "description": "FK to customers"},
        {"fieldPath": "amount",        "type": "NUMBER",  "description": "Order total"},
        {"fieldPath": "created_at",    "type": "STRING",  "description": "Timestamp"},
        {"fieldPath": "region",        "type": "STRING",  "description": "New: order region"},
    ]

    # First call returns baseline, second returns current (post-break)
    dh.get_schema.side_effect = [baseline_fields, current_fields]

    if with_lineage:
        dh.get_lineage.return_value = {
            "data": {
                "entity": {
                    "urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,ecommerce.orders,PROD)",
                    "type": "DATASET",
                    "name": "orders",
                    "lineage": {
                        "relationships": [
                            {"entity": {"urn": "urn:li:dataset:(...revenue_dashboard)", "type": "DASHBOARD", "name": "revenue_dashboard"}},
                            {"entity": {"urn": "urn:li:dataset:(...orders_monthly)", "type": "DATASET",   "name": "orders_monthly"}},
                        ]
                    },
                }
            }
        }
    else:
        dh.get_lineage.return_value = {}

    return dh, baseline_fields, current_fields


def run_demo(offline: bool = True):
    print("\n" + "=" * 60)
    print("  ANAMNESIS DEMO - Schema Break Memory Loop")
    print("=" * 60)

    from backend.agents.detector import SchemaDetector
    from backend.agents.diagnoser import Diagnoser
    from backend.core.memory_store import MemoryStore

    # Use a temp memory store so demo is isolated
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        store_path = f.name

    try:
        store = MemoryStore(path=store_path)
        mock_dh, baseline_fields, current_fields = _make_mock_datahub()

        detector = SchemaDetector(datahub=mock_dh, store=store)
        diagnoser = Diagnoser(datahub=mock_dh, store=store)

        DATASET_URN = "urn:li:dataset:(urn:li:dataPlatform:snowflake,ecommerce.orders,PROD)"

        # -- Step 1: Capture baseline ------------------------------------------
        print("\n[>>] Step 1: Capturing schema baseline for 'orders' dataset...")
        detector.capture_baseline(DATASET_URN)
        print(f"   [OK] Baseline captured ({len(baseline_fields)} fields)")

        # -- Step 2: Detect schema break ---------------------------------------
        print("\n[>>] Step 2: Running SchemaDetector (schema break injected)...")
        detection = detector.detect(DATASET_URN, auto_capture_baseline=False)

        print(f"   has_changes : {detection['has_changes']}")
        print(f"   is_breaking : {detection['is_breaking']}")
        print(f"   diff summary: {detection['diff']['summary']}")
        print(f"   memory_id   : {detection.get('memory_id')}")

        # -- Step 3: Diagnose impact -------------------------------------------
        print("\n[>>] Step 3: Running Diagnoser (lineage traversal + memory search)...")
        diagnosis = diagnoser.diagnose(
            dataset_urn=DATASET_URN,
            diff=detection["diff"],
            memory_id=detection.get("memory_id"),
        )

        print(f"   downstream_count : {diagnosis['downstream_count']}")
        print(f"   past_fixes_found : {diagnosis['past_fixes_found']}")
        print(f"   incident_memory_id: {diagnosis['incident_memory_id']}")
        print("\n   Remediation Plan:")
        for step in diagnosis["remediation_plan"]:
            print(f"      {step}")

        # -- Step 4: Query memory ----------------------------------------------
        print("\n[>>] Step 4: Querying Anamnesis memory...")
        all_records = store.all()
        print(f"   Total records in memory: {len(all_records)}")
        for rec in all_records:
            print(f"   [{rec.type.value}] {rec.title} (severity={rec.severity}, resolved={rec.resolved})")

        # -- Step 5: Mark resolved ---------------------------------------------
        if diagnosis.get("incident_memory_id"):
            print(f"\n[>>] Step 5: Marking incident as resolved...")
            store.update(diagnosis["incident_memory_id"], resolved=True)
            rec = store.get(diagnosis["incident_memory_id"])
            print(f"   [OK] Incident {rec.id[:8]}... is now resolved={rec.resolved}")

        print("\n" + "=" * 60)
        print("  ✅ Anamnesis demo complete – memory layer working!")
        print("=" * 60 + "\n")

    finally:
        os.unlink(store_path)


if __name__ == "__main__":
    run_demo()
