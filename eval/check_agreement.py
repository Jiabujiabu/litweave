"""Checks human-vs-LLM agreement on whatever subset of candidates_to_label_zh.xlsx
has been labeled so far, broken down by topic -- so we can tell whether it's
safe to extrapolate the LLM's suggestion to the unlabeled rows (high
agreement, spread across topics) or not (agreement untested on some topics,
or too low to trust).

Usage:
    python eval/check_agreement.py
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from score_labels import _rows_from_xlsx, RELEVANT_TRUE, RELEVANT_FALSE  # noqa: E402

XLSX_PATH = os.path.join(os.path.dirname(__file__), "candidates_to_label_zh.xlsx")


def parse_bool(val: str):
    v = str(val).strip().lower()
    if v in RELEVANT_TRUE:
        return True
    if v in RELEVANT_FALSE:
        return False
    return None


def main():
    rows = _rows_from_xlsx(XLSX_PATH)

    by_topic_total = defaultdict(int)
    by_topic_labeled = defaultdict(int)
    by_topic_agree = defaultdict(int)

    overall_labeled = 0
    overall_agree = 0
    disagreements = []

    for r in rows:
        topic = r["topic"]
        by_topic_total[topic] += 1

        human = parse_bool(r.get("relevant", ""))
        if human is None:
            continue

        ai = parse_bool(r.get("llm_suggestion", ""))
        by_topic_labeled[topic] += 1
        overall_labeled += 1
        if human == ai:
            by_topic_agree[topic] += 1
            overall_agree += 1
        else:
            disagreements.append({
                "topic": topic, "title": r["title"],
                "human": "相关" if human else "不相关",
                "ai": "相关" if ai else "不相关" if ai is not None else "(未识别)",
                "ai_reason": r.get("llm_reason", ""),
            })

    print("=" * 70)
    print(f"Labeled so far: {overall_labeled}/{len(rows)} rows")
    print(f"Overall agreement: {overall_agree}/{overall_labeled} "
          f"({overall_agree/overall_labeled:.1%})" if overall_labeled else "No rows labeled yet.")
    print("=" * 70)

    print("\nCoverage and agreement by topic:")
    for topic in by_topic_total:
        labeled = by_topic_labeled[topic]
        total = by_topic_total[topic]
        agree = by_topic_agree[topic]
        agree_str = f"{agree}/{labeled} ({agree/labeled:.0%})" if labeled else "-- not labeled yet --"
        print(f"  {labeled:>3}/{total:<3} labeled | agreement: {agree_str:20s} | {topic}")

    unlabeled_topics = [t for t in by_topic_total if by_topic_labeled[t] == 0]
    if unlabeled_topics:
        print(f"\n{len(unlabeled_topics)} topic(s) have ZERO labels so far -- agreement is untested there:")
        for t in unlabeled_topics:
            print(f"  - {t}")

    if disagreements:
        print(f"\n{len(disagreements)} disagreement(s):")
        for d in disagreements:
            print(f"  [{d['topic']}] human={d['human']} vs ai={d['ai']} -- {d['title'][:60]}")
            print(f"      AI reason: {d['ai_reason']}")

    print("\n" + "=" * 70)
    if overall_labeled and not unlabeled_topics and overall_agree / overall_labeled >= 0.85:
        print("Coverage spans every topic and agreement is high -- reasonable to extrapolate")
        print("the AI suggestion to the remaining unlabeled rows.")
    elif unlabeled_topics:
        print("Some topics have no human labels yet -- label at least a few rows per")
        print("missing topic before extrapolating, agreement elsewhere doesn't cover them.")
    elif overall_labeled:
        print("Agreement is below 85% -- worth reviewing the disagreements above before")
        print("deciding whether to extrapolate.")
    print("=" * 70)


if __name__ == "__main__":
    main()
