import re

with open('backend/seed_demo_data_v2.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the broken imports and URNs
content = re.sub(
    r"# ── Real DataHub URNs \(confirmed from audit\) ──────────────────────────────────.*?ORDERS_URN    =",
    "# ── Real DataHub URNs (confirmed from audit) ──────────────────────────────────\nORDERS_URN    =",
    content,
    flags=re.DOTALL
)

with open('backend/seed_demo_data_v2.py', 'w', encoding='utf-8') as f:
    f.write(content)
