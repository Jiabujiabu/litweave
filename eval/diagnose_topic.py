"""Runs the real graph for ONE topic and dumps the final papers + LLM judge
verdicts/reasons, for diagnosing a specific regression instead of guessing.

Usage:
    python eval/diagnose_topic.py "Social media use and adolescent mental health"
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from run_eval import run_case  # noqa: E402
from llm_judge import judge_chunk  # noqa: E402


def main():
    topic = sys.argv[1]
    final_state = run_case({"topic": topic})
    papers = final_state["collected_papers"]
    print(f"domain: {final_state.get('domain')}")
    print(f"research_directions: {final_state.get('research_directions')}")
    print()

    rows = [{"title": p["title"], "summary": p.get("summary", "")} for p in papers]
    judgments = judge_chunk(topic, rows)
    judgment_by_idx = {j["index"]: j for j in judgments}

    for i, p in enumerate(papers):
        j = judgment_by_idx.get(i, {})
        print(f"[{j.get('relevant', '?')}] {p['source']:16s} {p['title'][:70]}")
        print(f"      reason: {j.get('reason', '(none)')}")
        print(f"      abstract: {p.get('summary', '')[:150]}")
        print()


if __name__ == "__main__":
    main()
