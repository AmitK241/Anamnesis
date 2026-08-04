"""
backend/scratch_probe_similarity.py
--------------------------------------
BEFORE writing the seed script, probe the actual similarity scores that
our embedding model will produce for the 3 planned demo incidents.
This lets us validate that the story is convincing before recording.

Real fields confirmed from DataHub schema audit:

  orders    : order_status (NUMBER), delivery_type (STRING),
              payment_method_code (STRING), order_mode (STRING)
  customers : customer_class (STRING), mailshot (NUMBER),
              credit_limit (NUMBER), suggestions (STRING)
  products  : product_status (STRING), list_price (NUMBER),
              min_price (NUMBER), catalog_url (STRING)

Story design (using REAL fields):
  Incident 1 (orders)    — order_status DROPPED  +  delivery_type type-changed
  Incident 2 (customers) — customer_class DROPPED  (same break pattern: status field)
  Incident 3 (products)  — list_price type-changed + min_price DROPPED
                           (different break: pricing columns, not status fields)

Run: python -m backend.scratch_probe_similarity
"""
import sys
import io as _io

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from backend.core.embeddings import embed_incident_text, cosine_similarity

# ---------------------------------------------------------------------------
# Incident text definitions — what embed_incident_text() will actually encode
# ---------------------------------------------------------------------------

INC1 = dict(
    label="Incident 1 — orders: order_status DROPPED (pure column removal, status field)",
    root_cause=(
        "The orders table had the `order_status` classification column dropped after "
        "a schema migration to a new order-management platform. Downstream ETL pipelines, "
        "reporting dashboards, and BI queries that filter on order status began failing "
        "with missing column errors. The business-state field deletion went uncoordinated "
        "across consumer teams."
    ),
    missing_fields=["order_status"],
    type_changes=[],
)

INC2 = dict(
    label="Incident 2 — customers: customer_class DROPPED (pure column removal, classification field)",
    root_cause=(
        "The customers table lost the `customer_class` classification column following "
        "a CRM system upgrade that consolidated customer segmentation logic into a "
        "separate microservice. Downstream personalisation pipelines and loyalty-tier "
        "queries that rely on the customer classification field began returning NULL "
        "segments. This column deletion was not communicated to downstream consumer teams."
    ),
    missing_fields=["customer_class"],
    type_changes=[],
)

INC3 = dict(
    label="Incident 3 — products: min_price DROPPED + list_price type-changed (pricing+type break)",
    root_cause=(
        "The products table had the `min_price` pricing column removed as part of a "
        "pricing-engine financial overhaul that moved minimum pricing rules to a "
        "dedicated pricing microservice. Additionally, `list_price` was changed from "
        "a numeric type to a string type to support multi-currency display formatting, "
        "breaking aggregation and financial reporting queries that rely on numeric arithmetic. "
        "Both the monetary field deletion and the incompatible type change occurred "
        "together during the same schema migration."
    ),
    missing_fields=["min_price"],
    type_changes=[{"field": "list_price", "was": "NUMBER", "now": "STRING"}],
)

# ---------------------------------------------------------------------------
# Compute embeddings
# ---------------------------------------------------------------------------
print("=" * 65)
print("  Probing demo-story similarity scores")
print("  (loading all-MiniLM-L6-v2 — ~1s after first run)")
print("=" * 65)

incidents = [INC1, INC2, INC3]
vecs = []
for inc in incidents:
    print(f"\n  Computing embedding for: {inc['label']}")
    print(f"    missing_fields : {inc['missing_fields']}")
    print(f"    type_changes   : {inc['type_changes']}")
    v = embed_incident_text(
        root_cause=inc["root_cause"],
        missing_fields=inc["missing_fields"],
        type_changes=inc["type_changes"],
    )
    vecs.append(v)
    print(f"    dim={len(v)}  first3={[round(x,4) for x in v[:3]]}")

v1, v2, v3 = vecs

print("\n" + "=" * 65)
print("  SIMILARITY SCORES")
print("=" * 65)
s12 = cosine_similarity(v1, v2)
s13 = cosine_similarity(v1, v3)
s23 = cosine_similarity(v2, v3)
print(f"\n  Inc1 vs Inc2 (orders-status vs customers-class, SIMILAR): {s12:.4f}")
print(f"  Inc1 vs Inc3 (status/type vs pricing,         DIFFERENT): {s13:.4f}")
print(f"  Inc2 vs Inc3 (customers-class vs pricing,     DIFFERENT): {s23:.4f}")

# Evaluate the story
print("\n" + "=" * 65)
print("  STORY EVALUATION")
print("=" * 65)
ok_12 = s12 >= 0.80
ok_13 = s13 < s12 - 0.05   # Inc3 must score noticeably lower than Inc2
ok_23 = s23 < s12 - 0.05

if ok_12:
    print(f"  ✅ Inc1 vs Inc2 = {s12:.4f}  (≥0.80 — strong recall hit for demo payoff)")
else:
    print(f"  ❌ Inc1 vs Inc2 = {s12:.4f}  (too low — need ≥0.80 for convincing payoff)")

if ok_13:
    print(f"  ✅ Inc1 vs Inc3 = {s13:.4f}  ({s12-s13:.4f} below Inc1-Inc2 — shows nuance)")
else:
    print(f"  ⚠️  Inc1 vs Inc3 = {s13:.4f}  (gap from Inc1-Inc2 is only {s12-s13:.4f} — may be too close)")

if ok_23:
    print(f"  ✅ Inc2 vs Inc3 = {s23:.4f}  ({s12-s23:.4f} below Inc1-Inc2 — shows nuance)")
else:
    print(f"  ⚠️  Inc2 vs Inc3 = {s23:.4f}  (gap from Inc1-Inc2 is only {s12-s23:.4f})")

# Final verdict
if ok_12 and (ok_13 or ok_23):
    print("\n  ✅ STORY IS CONVINCING — proceed with seed_demo_data.py")
else:
    print("\n  ❌ STORY NEEDS ADJUSTMENT — see notes above")
    print("     Suggested fixes:")
    if not ok_12:
        print("       • Make Inc1/Inc2 more lexically similar (same field-type wording)")
    if not ok_13 and not ok_23:
        print("       • Make Inc3 more lexically distinct (e.g. use financial/pricing vocabulary)")
print()
