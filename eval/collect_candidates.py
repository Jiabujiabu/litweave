"""Collects raw candidate papers from ALL THREE sources for every topic in
test_set.json, bypassing the production domain-based routing entirely. This
is a measurement script, not a change to the graph: the goal is to gather
enough labeled data to answer two questions with real numbers instead of
intuition:
  1. What fraction of retrieved papers are actually topically relevant
     (a more meaningful signal than exact-title-hit recall against a
     hand-picked 2-3 paper gold list -- see eval/run_eval.py's results)?
  2. For CS topics specifically, does Semantic Scholar out-perform arXiv,
     as observed anecdotally during manual annotation?

Writes eval/candidates_to_label.csv for manual y/n relevance labeling.
Run eval/score_labels.py afterwards once the "relevant" column is filled in.

Usage:
    python eval/collect_candidates.py
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nodes import decompose_directions, search_arxiv, search_crossref, search_semantic_scholar
from run_eval import load_test_set, normalize_url  # noqa: E402 (path inserted above)


def collect_for_topic(topic: str) -> tuple[str, list[dict]]:
    """Runs decomposition once, then queries all three sources independently
    (domain forced to 'cs' when calling search_crossref/search_semantic_scholar
    so their internal branching always returns a clean list -- see their
    domain-conditional overwrite/append logic in nodes.py)."""
    base_state = {"topic": topic, "language": "en"}
    decomposed = decompose_directions(base_state)
    directions = decomposed["research_directions"]
    domain = decomposed["domain"]

    query_state = {
        "research_directions": directions,
        "domain": "cs",  # forces overwrite/no-append branches in search_crossref/search_semantic_scholar
        "collected_papers": [],
        "language": "en",
    }

    arxiv_papers = search_arxiv(query_state)["collected_papers"]
    crossref_papers = search_crossref(query_state)["collected_papers"]
    semantic_papers = search_semantic_scholar(query_state)["collected_papers"]

    pooled = arxiv_papers + crossref_papers + semantic_papers

    seen_urls = set()
    deduped = []
    for p in pooled:
        url = normalize_url(p.get("url", "")) or p.get("url", "")
        if url and url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(p)

    return domain, deduped


def main():
    test_set = load_test_set()
    rows = []
    raw_cache = []  # full paper dicts incl. summary, keyed by topic -- so a
                     # re-run of downstream steps (LLM judge, CSV rebuild)
                     # never has to hit these rate-limited APIs again

    for case in test_set:
        topic = case["topic"]
        print(f"\n=== {topic} ===")
        domain, papers = collect_for_topic(topic)
        print(f"  domain={domain}  pooled+deduped candidates={len(papers)}")
        raw_cache.append({"topic": topic, "domain": domain, "papers": papers})
        for p in papers:
            rows.append({
                "topic": topic,
                "domain": domain,
                "source": p.get("source", ""),
                "title": p.get("title", ""),
                "summary": (p.get("summary", "") or "")[:400],
                "url": p.get("url", ""),
                "relevant": "",  # fill in y/n (or accept the llm_suggestion column, once populated)
            })

    cache_path = os.path.join(os.path.dirname(__file__), "candidates_raw_cache.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(raw_cache, f, ensure_ascii=False, indent=2)
    print(f"\nRaw results (with full abstracts) cached to {cache_path}")

    out_path = os.path.join(os.path.dirname(__file__), "candidates_to_label.csv")
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["topic", "domain", "source", "title", "summary", "url", "relevant"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)} candidates written to {out_path}")
    print("Run eval/llm_judge.py to pre-fill relevance suggestions, then review and fill in 'relevant'.")


if __name__ == "__main__":
    main()
