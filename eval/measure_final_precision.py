"""End-to-end precision measurement: runs the ACTUAL graph (post-fix: cs also
queries CrossRef, tighter direction prompts, 6 results/direction instead of
3) for every test topic, takes the real final collected_papers (after
process_papers' dedup+rerank+truncate -- exactly what ships in the report),
and judges relevance with the LLM-as-judge that was already validated at
100% agreement against human labels earlier in this eval. No manual
labeling needed for this round.

Usage:
    python eval/measure_final_precision.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from run_eval import load_test_set, run_case  # noqa: E402
from llm_judge import judge_chunk  # noqa: E402


def main():
    test_set = load_test_set()
    total_relevant = 0
    total_count = 0
    per_topic = []

    for case in test_set:
        topic = case["topic"]
        print(f"\n=== {topic} ===")
        final_state = run_case(case)
        papers = final_state["collected_papers"]
        domain = final_state.get("domain")
        citation_retries = final_state.get("citation_retry_count", 0)

        rows = [{"title": p["title"], "summary": p.get("summary", "")} for p in papers]
        try:
            judgments = judge_chunk(topic, rows)
        except Exception as e:
            print(f"  judge failed ({e}), skipping this topic's precision")
            judgments = []

        relevant = sum(1 for j in judgments if j.get("relevant") == "y")
        total_relevant += relevant
        total_count += len(papers)
        per_topic.append((topic, domain, citation_retries, relevant, len(papers)))
        print(f"  domain={domain}  papers={len(papers)}  relevant={relevant}/{len(papers)}  "
              f"citation_retries={citation_retries}")

    print("\n" + "=" * 78)
    print(f"{'topic':<50} {'domain':<16} {'precision':>10}")
    print("=" * 78)
    for topic, domain, retries, relevant, n in per_topic:
        p = relevant / n if n else 0
        print(f"{topic[:49]:<50} {domain:<16} {p:>9.2f}  ({relevant}/{n})")

    print("=" * 78)
    print(f"Overall final-report precision: {total_relevant}/{total_count} = {total_relevant/total_count:.2%}")
    print("=" * 78)


if __name__ == "__main__":
    main()
