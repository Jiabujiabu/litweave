"""Offline evaluation harness for the academic research agent.

Runs the full LangGraph pipeline (real network calls, real/MOCK LLM calls per
.env) against a hand-labeled test set, then reports:
  - retrieval precision/recall against the labeled relevant papers
  - which source (arXiv / CrossRef / Semantic Scholar) contributed the hits
  - citation-check outcome (did verify_citations need retries?)

Not part of the production graph -- this is a standalone script so eval logic
never touches the runtime path.

Usage:
    python eval/run_eval.py
"""

import json
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langgraph.types import Command

from graph import app


def load_test_set(path=None):
    path = path or os.path.join(os.path.dirname(__file__), "test_set.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalize_url(url: str) -> str | None:
    if not url:
        return None
    u = url.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    u = u.rstrip("/")
    u = re.sub(r"v\d+$", "", u)  # strip arXiv version suffix (v1, v2, ...)
    return u


def find_match(gold: dict, retrieved_papers: list[dict]) -> dict | None:
    """Returns the retrieved paper matching `gold`, or None. URL match takes
    priority (more robust to title formatting differences); falls back to
    normalized title equality."""
    gold_url = normalize_url(gold.get("url", ""))
    gold_title = normalize_title(gold["title"])

    if gold_url:
        for p in retrieved_papers:
            if normalize_url(p.get("url", "")) == gold_url:
                return p

    for p in retrieved_papers:
        if normalize_title(p.get("title", "")) == gold_title:
            return p

    return None


def run_case(case: dict) -> dict:
    """Explicit paid batch eval simulates both gates; decisions are batch_auto, not human labels."""
    from nodes import MOCK_MODE
    if MOCK_MODE or os.getenv("ALLOW_PAID_EVAL") != "1":
        raise RuntimeError("Real evaluation requires a configured provider and explicit ALLOW_PAID_EVAL=1 with RESEARCH_* budgets. Use eval/replay.py for offline fixtures.")
    config = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 100}
    payload = {
        "topic": case["topic"],
        "iteration_count": 0,
        "citation_retry_count": 0,
        "language": "en",
    }

    from model_access import local_model_session
    with local_model_session():
        while True:
            interrupted = False
            for chunk in app.stream(payload, config=config, stream_mode="updates"):
                if "__interrupt__" in chunk:
                    interrupted = True
                    break
            if not interrupted:
                break
            gate = app.get_state(config).interrupts[0].value
            if gate.get("kind")=="papers":
                limit=app.get_state(config).values["settings"]["max_papers"]
                included={p["paper_id"] for p in [p for p in gate["papers"] if p.get("relevance_status")=="accepted"][:limit]}
                response={"action":"confirm", "decision_source":"batch_auto", "decisions":{
                    p["paper_id"]:{"decision":"keep" if p["paper_id"] in included else "exclude", "reason":"automated evaluation, not a human label"}
                    for p in gate["papers"]}}
                if not any(d["decision"]=="keep" for d in response["decisions"].values()):
                    response={"action":"end"}
            elif gate.get('kind')=='directions':
                options=gate.get('directions',[])
                response={'action':'generate','selected_ids':[d['direction_id'] for d in options[:2]]} if options else {'action':'end'}
            else:
                response={"action":"accept"}
            payload = Command(resume=response)

    return app.get_state(config).values


def evaluate(test_set_path=None):
    test_set = load_test_set(test_set_path)
    if not test_set:
        raise ValueError("No test cases to evaluate; metrics are unavailable")
    results = []

    for case in test_set:
        print(f"\n=== {case['topic']} ===")
        final_state = run_case(case)
        retrieved = final_state["collected_papers"]
        gold_papers = case["relevant_papers"]

        hits = []
        for gold in gold_papers:
            match = find_match(gold, retrieved)
            if match:
                hits.append(match)

        precision = len(hits) / len(retrieved) if retrieved else 0.0
        recall = len(hits) / len(gold_papers) if gold_papers else 0.0

        source_counts: dict[str, int] = {}
        for p in hits:
            source_counts[p.get("source", "unknown")] = source_counts.get(p.get("source", "unknown"), 0) + 1

        result = {
            "topic": case["topic"],
            "domain": final_state.get("domain"),
            "domain_hint": case.get("domain_hint"),
            "retrieved_count": len(retrieved),
            "gold_count": len(gold_papers),
            "hits": len(hits),
            "reference_set_hit_fraction": round(precision, 2),
            "known_set_coverage": round(recall, 2),
            "hit_sources": source_counts,
            "citation_retry_count": final_state.get("citation_retry_count", 0),
        }
        results.append(result)
        print(f"  domain classified as: {result['domain']} (expected: {result['domain_hint']})")
        print(f"  precision={result['reference_set_hit_fraction']}  recall={result['known_set_coverage']}  "
              f"hits={result['hits']}/{result['gold_count']}  hit sources={source_counts}")
        print(f"  citation retries: {result['citation_retry_count']}")

    avg_p = sum(r["reference_set_hit_fraction"] for r in results) / len(results)
    avg_r = sum(r["known_set_coverage"] for r in results) / len(results)
    avg_retries = sum(r["citation_retry_count"] for r in results) / len(results)

    combined_sources: dict[str, int] = {}
    for r in results:
        for src, count in r["hit_sources"].items():
            combined_sources[src] = combined_sources.get(src, 0) + count

    domain_mismatches = [r for r in results if r["domain_hint"] and r["domain"] != r["domain_hint"]]

    print("\n" + "=" * 60)
    print(f"Average reference-set hit fraction: {avg_p:.2f}")
    print(f"Average known-set coverage:    {avg_r:.2f}")
    print(f"Average citation retries per report: {avg_retries:.2f}")
    print(f"Hit counts by source (across all topics): {combined_sources}")
    print(f"Domain classification mismatches: {len(domain_mismatches)}/{len(results)}")
    for r in domain_mismatches:
        print(f"  - '{r['topic']}': classified as {r['domain']}, expected {r['domain_hint']}")
    print("=" * 60)

    from evaluation import save_run
    out_path = save_run({"harness":"legacy_reference_set", "approval":"automated_evaluation"}, test_set, results, mode="real_network")
    print(f"New run directory: {out_path}")

    return results


if __name__ == "__main__":
    evaluate()
