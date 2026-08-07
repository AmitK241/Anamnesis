"""
scratch_matrix.py
Extracts embeddings from DataHub and computes a pairwise similarity matrix.
"""
import os
import json
import numpy as np
from backend.scratch_audit import get_aspect, all_urns_discovered

def cosine_similarity(a, b):
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

def main():
    incidents = []
    
    # We will use all_urns_discovered from scratch_audit
    for urn in all_urns_discovered:
        aspect = get_aspect(urn, "incidentMemory")
        if aspect and aspect.get("incidentId") and aspect.get("incidentId") != "__WIPED__":
            embedding = aspect.get("embeddingVector")
            if embedding:
                incidents.append({
                    "id": aspect["incidentId"],
                    "dataset": urn.split(".")[-1].split(",")[0],  # approximate name
                    "vector": embedding
                })

    print(f"Found {len(incidents)} valid incidents with embeddings.")
    if not incidents:
        return

    # Print the matrix
    print("\nPairwise Similarity Matrix:")
    header = "ID (Dataset)".ljust(45)
    for inc in incidents:
        header += f"{inc['dataset']:15s}"
    print(header)
    print("-" * len(header))

    for inc_row in incidents:
        row_str = f"{inc_row['id']} ({inc_row['dataset']})".ljust(45)
        for inc_col in incidents:
            sim = cosine_similarity(inc_row['vector'], inc_col['vector'])
            row_str += f"{sim:10.4f}     "
        print(row_str)

if __name__ == "__main__":
    main()
