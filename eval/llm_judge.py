"""LLM-assisted pre-labeling for candidates_to_label.csv.

Batches papers per topic (chunks of CHUNK_SIZE) and asks the configured LLM
provider (via nodes.call_llm -- respects LLM_PROVIDER in .env; MOCK mode
can't judge relevance meaningfully, so a real key is required) to judge
topical relevance from title + abstract. Writes two new columns,
llm_suggestion (y/n) and llm_reason, into the CSV -- 'relevant' is left for
you to fill in (copy the suggestion or override it). This is an LLM-as-judge
pre-filter to review, not a replacement for a human final call: the whole
point of keeping 'relevant' separate is so score_labels.py measures your
actual judgment, and (as a side effect) an agreement rate between the two is
a legitimate write-up point.

Usage:
    python eval/llm_judge.py
"""

import csv
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nodes import call_llm, MOCK_MODE  # noqa: E402

CHUNK_SIZE = 8
CSV_PATH = os.path.join(os.path.dirname(__file__), "candidates_to_label.csv")


def load_rows():
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def judge_chunk(topic: str, chunk: list[dict]) -> list[dict]:
    if MOCK_MODE or os.getenv("ALLOW_PAID_EVAL") != "1":
        raise RuntimeError("Real judge requires explicit ALLOW_PAID_EVAL=1 and configured budgets; mock is not an evaluation result")
    papers_text = "\n".join(
        f"{i}. Title: {r['title']}\n   Abstract: {r['summary'] or '(no abstract available)'}"
        for i, r in enumerate(chunk)
    )
    prompt = f"""Topic: {topic}

For each paper below, judge whether a graduate student writing a literature
review on this exact topic would consider it directly relevant (not just
superficially related by a shared keyword). Respond with ONLY a JSON array,
one object per paper, in the same order, each shaped like:
{{"index": <int>, "relevant": "y" or "n", "reason": "<one short clause, <15 words>"}}

Papers:
{papers_text}"""

    from model_access import local_model_session
    with local_model_session():
        content = call_llm(
            [
                {"role": "system", "content": "You are a research librarian judging topical relevance. Return ONLY a JSON array, no other text."},
                {"role": "user", "content": prompt},
            ],
            task="filter", language="en",
        )
    content = content.strip().strip("```json").strip("```").strip()
    results = json.loads(content)
    if not isinstance(results, list) or len(results) != len(chunk) or not all(isinstance(j, dict) for j in results):
        raise ValueError("incomplete judge response")
    indices = [j.get("index") for j in results]
    if any(type(i) is not int for i in indices) or set(indices) != set(range(len(chunk))) or len(set(indices)) != len(indices):
        raise ValueError("unknown, duplicate or missing judge indices")
    if any(j.get("relevant") not in ("y", "n") or not isinstance(j.get("reason"), str) for j in results):
        raise ValueError("invalid judge labels")
    return sorted(results, key=lambda j:j["index"])


def main():
    if MOCK_MODE:
        print("No real API key configured for the selected LLM_PROVIDER -- LLM-as-judge needs a real model, can't run in MOCK mode.")
        return

    rows = load_rows()
    by_topic = defaultdict(list)
    for idx, r in enumerate(rows):
        by_topic[r["topic"]].append((idx, r))

    suggestions = {}  # row index -> (relevant, reason)

    for topic, indexed_rows in by_topic.items():
        print(f"\n=== {topic} ({len(indexed_rows)} papers) ===")
        for start in range(0, len(indexed_rows), CHUNK_SIZE):
            chunk = indexed_rows[start:start + CHUNK_SIZE]
            chunk_rows = [r for _, r in chunk]
            print(f"  judging papers {start+1}-{start+len(chunk)}...")
            try:
                judgments = judge_chunk(topic, chunk_rows)
            except (json.JSONDecodeError, Exception) as e:
                print(f"  chunk failed ({e}), leaving suggestions blank for this batch")
                continue
            for j in judgments:
                local_idx = j.get("index")
                if local_idx is None or not (0 <= local_idx < len(chunk)):
                    continue
                global_idx = chunk[local_idx][0]
                suggestions[global_idx] = (j.get("relevant", ""), j.get("reason", ""))

    for idx, r in enumerate(rows):
        rel, reason = suggestions.get(idx, ("", ""))
        r["llm_suggestion"] = rel
        r["llm_reason"] = reason

    fieldnames = ["topic", "domain", "source", "title", "summary", "url", "relevant", "llm_suggestion", "llm_reason"]
    from evaluation import save_run
    directory = save_run({"harness":"legacy_model_judge"}, rows, [], mode="real_network")
    output_path = directory / "model_suggestions.csv"
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    filled = sum(1 for idx in range(len(rows)) if idx in suggestions)
    print(f"\n{filled}/{len(rows)} rows got an LLM suggestion, written to {output_path}")
    print("Review llm_suggestion/llm_reason and fill in 'relevant' for each row (agree or override).")


if __name__ == "__main__":
    main()
