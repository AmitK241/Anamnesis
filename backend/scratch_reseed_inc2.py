"""
backend/scratch_reseed_inc2.py
-------------------------------
Re-seeds Incident 2 (customers/customer_class) back onto the crm_db.customers URN.

The full-loop verification test overwrote ASBQA4 with INC-1785608750783-2WMPS0,
and the subsequent wipe replaced that with __WIPED__.  This script restores a
correct Inc2 IncidentMemory so scratch_verify_scores Probe 3 passes.

The new incident ID will differ from ASBQA4 (timestamps differ), but the
embedding vector and content will be identical — the scores will match.

The script is careful to:
  1. NOT register the customers URN before recall, so Inc1 (orders) is the only
     thing in memory during the Inc2 recall step (matches ~0.97).
  2. Register the customers URN AFTER writing, so Inc3 seeding can find both.

Run: python -m backend.scratch_reseed_inc2
"""
import sys
import io as _io

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from backend.agents.diagnoser import Diagnoser
from backend.agents.fixer import FixerAgent
from backend.agents.memory_writer import MemoryWriterAgent, _register_urn
from backend.agents.recall import MemoryRecallAgent

CUSTOMERS_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:postgres,"
    "b2fd91.crm_db.customers,PROD)"
)

DETECTION = {
    "dataset_urn":     CUSTOMERS_URN,
    "has_break":       True,
    "severity":        "high",
    "missing_fields":  ["customer_class"],
    "type_changes":    [],
    "break_summary":   (
        "1 field(s) were removed: customer_class was dropped from the customers "
        "table following a CRM system upgrade that moved segmentation logic to a "
        "separate microservice."
    ),
}

print("=" * 65)
print("  scratch_reseed_inc2.py")
print("  Re-seeding Incident 2 (customers / customer_class DROPPED)")
print("=" * 65)

# Stage 2: Diagnose
print("\n  [2] Diagnosing...")
diagnoser = Diagnoser()
diagnosis = diagnoser.diagnose(DETECTION)
print(f"      root_cause  : {str(diagnosis.get('root_cause', ''))[:80]}...")
print(f"      confidence  : {diagnosis.get('diagnosis_confidence')}")
print(f"      missing_fields: {diagnosis.get('missing_fields')}")

# Stage 3: Recall — customers URN NOT yet registered, so only Inc1 is visible
print("\n  [3] Recalling similar past incidents (min_similarity=0.60)...")
recall_agent = MemoryRecallAgent()
recall_result = recall_agent.recall_similar_incidents(
    diagnosis=diagnosis,
    top_k=5,
    min_similarity=0.60,
)
n_matches = len(recall_result.get("matches", []))
print(f"      Checked  : {recall_result.get('total_past_incidents_checked', 0)} past incident(s)")
print(f"      Matches  : {n_matches}")
for m in recall_result.get("matches", []):
    print(f"        -> {m.get('incident_id'):30s}  score={m.get('similarity_score', 0):.4f}")

# Stage 4: Fix
print("\n  [4] Generating fix (Groq LLM)...")
fixer = FixerAgent()
try:
    fix_result = fixer.generate_fix(diagnosis=diagnosis, recall_result=recall_result)
except RuntimeError as exc:
    print(f"      WARNING: Fixer failed ({exc}) — using placeholder fix")
    fix_result = {
        "suggested_fix": "# Placeholder: re-add customer_class column or create a compatibility view",
        "mode": "fallback",
        "estimated_time_saved_minutes": 30,
    }
print(f"      mode: {fix_result.get('mode')}  time_saved: {fix_result.get('estimated_time_saved_minutes')}min")

# Stage 5: Write-memory
print("\n  [5] Writing to DataHub memory...")
writer = MemoryWriterAgent()
write_result = writer.write_incident_memory(
    detection=DETECTION,
    diagnosis=diagnosis,
    recall_result=recall_result,
    fix_result=fix_result,
)
incident_id  = write_result.get("incident_id", "?")
verification = write_result.get("verification", "?")
success      = write_result.get("success", False)

if success:
    print(f"\n  OK  Written: {incident_id}")
    print(f"      verification: {verification}")
else:
    print(f"\n  FAIL Write failed: {verification}")
    sys.exit(1)

# Register customers URN so subsequent seeding / recall can find it
_register_urn(CUSTOMERS_URN)
print(f"\n  Registered customers URN for future recall.")

print("\n" + "=" * 65)
print(f"  Inc2 re-seeded as: {incident_id}")
print("  Run scratch_verify_scores to confirm all 3 probes pass.")
print("=" * 65)
