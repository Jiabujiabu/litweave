"""Measures precision AFTER applying process_papers' actual rerank+truncate
step, using the labels we already collected -- no new API calls needed.

candidates_raw_cache.json has the pre-translation English pool (title,
summary, url, source) per topic, straight from collect_candidates.py.
candidates_to_label_zh.xlsx has the final relevance verdict per row, joined
back by URL (stable across both files; only cosmetic fields were translated).

This tells us whether the 46% raw-pool precision already reported understates
the pipeline's actual delivered quality (which only ever ships the top
TOP_K_PAPERS after semantic rerank), before making any code changes.

Usage:
    python eval/rerank_precision.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nodes import _get_embedder, TOP_K_PAPERS  # noqa: E402
from score_labels import _rows_from_xlsx, RELEVANT_TRUE, RELEVANT_FALSE  # noqa: E402

import numpy as np

CACHE_PATH = os.path.join(os.path.dirname(__file__), "candidates_raw_cache.json")
XLSX_PATH = os.path.join(os.path.dirname(__file__), "candidates_to_label_zh.xlsx")


def cosine(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)


def main():
    with open(CACHE_PATH, encoding="utf-8") as f:
        raw_cache = json.load(f)

    xlsx_rows = _rows_from_xlsx(XLSX_PATH)
    url_to_relevant = {}
    for r in xlsx_rows:
        val = str(r.get("relevant", "")).strip().lower()
        if val in RELEVANT_TRUE:
            url_to_relevant[r["url"]] = True
        elif val in RELEVANT_FALSE:
            url_to_relevant[r["url"]] = False

    embedder = _get_embedder()

    per_topic_results = []
    total_top10_relevant = 0
    total_top10_count = 0
    total_pool_relevant = 0
    total_pool_count = 0

    for entry in raw_cache:
        topic = entry["topic"]
        papers = entry["papers"]
        labeled_papers = [p for p in papers if p.get("url") in url_to_relevant]
        if not labeled_papers:
            continue

        topic_vec = embedder.encode([topic])[0]
        paper_vecs = embedder.encode([p["summary"] for p in labeled_papers])
        scored = sorted(
            zip(paper_vecs, labeled_papers),
            key=lambda pair: cosine(topic_vec, pair[0]),
            reverse=True,
        )
        ranked = [p for _, p in scored]
        top10 = ranked[:TOP_K_PAPERS]

        pool_relevant = sum(1 for p in labeled_papers if url_to_relevant[p["url"]])
        top10_relevant = sum(1 for p in top10 if url_to_relevant[p["url"]])

        pool_precision = pool_relevant / len(labeled_papers)
        top10_precision = top10_relevant / len(top10) if top10 else 0.0

        per_topic_results.append({
            "topic": topic,
            "pool_precision": pool_precision,
            "top10_precision": top10_precision,
            "pool_n": len(labeled_papers),
            "top10_n": len(top10),
            "top10_relevant": top10_relevant,
        })

        total_top10_relevant += top10_relevant
        total_top10_count += len(top10)
        total_pool_relevant += pool_relevant
        total_pool_count += len(labeled_papers)

    print("=" * 78)
    print(f"{'topic':<45} {'pool P':>8} {'top-10 P':>10}")
    print("=" * 78)
    for r in per_topic_results:
        print(f"{r['topic'][:44]:<45} {r['pool_precision']:>7.2f} {r['top10_precision']:>9.2f}  "
              f"({r['top10_relevant']}/{r['top10_n']})")

    print("=" * 78)
    print(f"Overall RAW POOL precision:  {total_pool_relevant}/{total_pool_count} = {total_pool_relevant/total_pool_count:.2%}")
    print(f"Overall TOP-{TOP_K_PAPERS} precision (after rerank): {total_top10_relevant}/{total_top10_count} = {total_top10_relevant/total_top10_count:.2%}")
    print("=" * 78)


if __name__ == "__main__":
    main()
