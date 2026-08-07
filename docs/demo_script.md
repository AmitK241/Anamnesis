# Demo Script — FINAL Seeded State (Pre-Recording, v2 — Rich Constellation)
## Seeded: 2026-08-07T06:12:54Z

## The 7 incidents (in seed order)

1. **INC-1786083135983-FSXGIG** — orders — order_status DROPPED — Critical — 0 recall matches (baseline)
2. **INC-1786083140762-2MYGSG** — customers — customer_class DROPPED — Critical — matches #1, score=90.68%
3. **INC-1786083145747-HRHDVR** — order_items — condition DROPPED — High — matches #1 (97.18%) and #2 (90.35%)
4. **INC-1786083151700-EBMMFI** — products — min_price DROPPED / list_price TYPE CHANGED — Medium — weaker match to #1/#2/#3, score=88.30%
5. **INC-1786083157436-SZ0NOE** — promotions — promotion_name RENAMED — Medium — *Note: Unexpectedly strong match to #3 (97.10%) because the detector summary used the word "removed" instead of just renamed, causing the LLM embedding to associate it tightly with the dropped column cluster.*
6. **INC-1786083161786-UXCBPT** — product_categories — parent_category_id TYPE CHANGED — Low — strongly matches #4 (89.64%) which also contained a type change, distinguishing itself from the pure drops (#1/#2).
7. **INC-1786083173547-UCM84V** — addresses — zipcode TYPE CHANGED — Low — strongly matches #6 (95.46%), creating a clear Type Change sub-cluster.

## Recording order (OPTION B — LOCKED, no live-trigger during recording):
1. Show Dashboard — stat cards now read Total Memories: 7, Incidents: 7, with a real mixed Severity Breakdown (Critical, High, Medium, Low).
2. Show Memory Constellation graph — now visibly richer: a clear 3-node strong cluster (orders/customers/order_items), a couple of connected-but-weaker nodes (products), and one or two more distinct nodes (promotions, and the second product_categories/addresses type-change pair) — call out on camera that this shows the system distinguishing DIFFERENT kinds of relatedness, not just "similar = yes/no". Visuals use an 85% threshold to clearly isolate the "type change" vs "drop" clusters.
3. Show Recent Memories / Severity Breakdown reflecting the real mixed severities
4. Navigate to Pipeline/Detect tab — walk through the 5-stage explanation using Incident 3 (order_items) as the on-screen example of "recall found TWO prior related incidents, not just one" — a stronger demonstration than the original single-match story
5. Show About page
6. Close on Dashboard with final state

**Locked: no live Full Loop trigger happens during the actual recording** — all 7 incidents are pre-seeded and verified. Same reasoning as before: guaranteed-clean, fully rehearsed, zero on-camera risk.
