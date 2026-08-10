"""Re-measures precision using the SAME already-collected candidates and
labels, but filtered down to whatever the PRODUCTION graph would actually
route to for each topic's domain (see route_after_arxiv/is_sufficient in
graph.py) -- instead of the experiment's "always query all 3 sources" pool.

collect_candidates.py deliberately bypassed routing to test the Semantic
Scholar hypothesis; that inflated the candidate pool with sources production
would never query for a given domain (e.g. arXiv for humanities topics,
which is 100% STEM and contributes zero relevant results). This script
undoes that bypass post-hoc, using data we already have -- no new API calls.

Usage:
    python eval/production_precision.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

from nodes import _get_embedder, TOP_K_PAPERS  # noqa: E402
from graph import SUFFICIENT_THRESHOLD  # noqa: E402
from score_labels import _rows_from_xlsx, RELEVANT_TRUE, RELEVANT_FALSE  # noqa: E402

CACHE_PATH = os.path.join(os.path.dirname(__file__), "candidates_raw_cache.json")
XLSX_PATH = os.path.join(os.path.dirname(__file__), "candidates_to_label_zh.xlsx")


def cosine(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)


def production_pool(domain: str, papers: list[dict]) -> list[dict]:
    """Mirrors route_after_arxiv/is_sufficient/route_by_domain in graph.py."""
    by_source = {"arXiv": [], "CrossRef": [], "Semantic Scholar": []}
    for p in papers:
        by_source.setdefault(p.get("source", ""), []).append(p)

    if domain == "humanities":
        pool = list(by_source["CrossRef"])
    else:  # cs and interdisciplinary: query both (variant under test -- production
           # today only does this for interdisciplinary; cs is arXiv-only)
        pool = by_source["arXiv"] + by_source["CrossRef"]

    if len(pool) < SUFFICIENT_THRESHOLD:
        pool = pool + by_source["Semantic Scholar"]

    # dedupe by URL, preserving first occurrence (matches process_papers)
    seen, deduped = set(), []
    for p in pool:
        url = p.get("url", "")
        if url and url in seen:
            continue
        seen.add(url)
        deduped.append(p)
    return deduped


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

    total_top10_relevant = total_top10_count = 0
    total_pool_relevant = total_pool_count = 0
    rows_out = []

    for entry in raw_cache:
        topic, domain, papers = entry["topic"], entry["domain"], entry["papers"]
        pool = production_pool(domain, papers)
        labeled_pool = [p for p in pool if p.get("url") in url_to_relevant]
        if not labeled_pool:
            continue

        topic_vec = embedder.encode([topic])[0]
        paper_vecs = embedder.encode([p["summary"] for p in labeled_pool])
        ranked = [p for _, p in sorted(
            zip(paper_vecs, labeled_pool),
            key=lambda pair: cosine(topic_vec, pair[0]),
            reverse=True,
        )]
        top10 = ranked[:TOP_K_PAPERS]

        pool_relevant = sum(1 for p in labeled_pool if url_to_relevant[p["url"]])
        top10_relevant = sum(1 for p in top10 if url_to_relevant[p["url"]])

        rows_out.append((topic, domain, len(labeled_pool), pool_relevant, len(top10), top10_relevant))
        total_pool_relevant += pool_relevant
        total_pool_count += len(labeled_pool)
        total_top10_relevant += top10_relevant
        total_top10_count += len(top10)

    print("=" * 90)
    print(f"{'topic':<45} {'domain':<15} {'pool P':>10} {'top-10 P':>10}")
    print("=" * 90)
    for topic, domain, pool_n, pool_rel, top10_n, top10_rel in rows_out:
        pool_p = pool_rel / pool_n if pool_n else 0
        top10_p = top10_rel / top10_n if top10_n else 0
        print(f"{topic[:44]:<45} {domain:<15} {pool_p:>9.2f} {top10_p:>9.2f}  ({top10_rel}/{top10_n})")

    print("=" * 90)
    print(f"Overall PRODUCTION-ROUTED pool precision: {total_pool_relevant}/{total_pool_count} = {total_pool_relevant/total_pool_count:.2%}")
    print(f"Overall PRODUCTION-ROUTED top-{TOP_K_PAPERS} precision:  {total_top10_relevant}/{total_top10_count} = {total_top10_relevant/total_top10_count:.2%}")
    print("=" * 90)


if __name__ == "__main__":
    main()
