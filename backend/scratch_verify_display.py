from backend.core.embeddings import format_similarity, similarity_label

scores = [
    ("Inc2 -> Inc1 (Strong payoff)",   0.9068),
    ("Inc3 -> Inc1 (Related nuance)",  0.8772),
    ("Inc3 -> Inc2 (Related nuance)",  0.8445),
]

print("=== VERIFICATION: Display format for seeded demo incidents ===")
print()
for label, score in scores:
    display = format_similarity(score)
    pct = round(score * 100, 1)
    slabel = similarity_label(score)
    print(f"  {label}")
    print(f"    raw float : {score:.4f}   (unchanged, used for logic)")
    print(f"    pct       : {pct}%")
    print(f"    label     : {slabel}")
    print(f"    display   : {display}")
    print()

print("=== Expected on-screen output (per demo script) ===")
print("  Incident 2 -> Incident 1 : 90.7% match -- Strong Match  (green badge)")
print("  Incident 3 -> Incident 1 : 87.7% match -- Related Match (amber badge)")
print("  Incident 3 -> Incident 2 : 84.5% match -- Related Match (amber badge)")
