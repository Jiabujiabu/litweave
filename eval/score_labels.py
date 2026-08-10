"""Scores the manually-labeled eval/candidates_to_label.csv (produced by
collect_candidates.py). Computes:
  - overall precision per topic
  - per-source precision overall
  - per-source precision restricted to CS-domain topics specifically,
    to answer: does Semantic Scholar out-perform arXiv for CS topics?

Rows with a blank/unrecognized 'relevant' value are skipped (not counted as
either relevant or irrelevant) -- fill in y/n for every row you want counted.

Usage:
    python eval/score_labels.py
"""

import csv
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RELEVANT_TRUE = {"y", "yes", "1", "true", "相关"}
RELEVANT_FALSE = {"n", "no", "0", "false", "不相关"}

# xlsx columns use Chinese headers -- maps them back to the CSV's English
# field names so both formats feed the same scoring logic below.
XLSX_HEADER_MAP = {
    "主题": "topic", "领域": "domain", "来源": "source",
    "标题": "title", "摘要": "summary", "链接": "url",
    "AI建议": "llm_suggestion", "AI理由": "llm_reason", "你的判断": "relevant",
}
XLSX_DOMAIN_ZH_TO_EN = {"计算机科学/理工": "cs", "人文社科": "humanities", "跨学科": "interdisciplinary"}


def _rows_from_xlsx(path):
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    header_zh = next(rows_iter)
    fields = [XLSX_HEADER_MAP.get(h, h) for h in header_zh]
    rows = []
    for values in rows_iter:
        if all(v is None for v in values):
            continue
        r = dict(zip(fields, (v if v is not None else "" for v in values)))
        r["domain"] = XLSX_DOMAIN_ZH_TO_EN.get(r["domain"], r["domain"])
        rows.append(r)
    return rows


def load_labels(path=None):
    if path is None:
        xlsx_path = os.path.join(os.path.dirname(__file__), "candidates_to_label_zh.xlsx")
        csv_path = os.path.join(os.path.dirname(__file__), "candidates_to_label.csv")
        path = xlsx_path if os.path.exists(xlsx_path) else csv_path

    if str(path).lower().endswith(".xlsx"):
        rows = _rows_from_xlsx(path)
    else:
        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))

    labeled = []
    skipped = 0
    for r in rows:
        val = str(r.get("relevant", "")).strip().lower()
        if val in RELEVANT_TRUE:
            r["relevant"] = True
        elif val in RELEVANT_FALSE:
            r["relevant"] = False
        else:
            skipped += 1
            continue
        labeled.append(r)

    if skipped:
        print(f"Skipped {skipped} unlabeled/ambiguous row(s) (blank 'relevant' column)")
    return labeled


def precision(rows):
    if not rows:
        return None
    return sum(1 for r in rows if r["relevant"]) / len(rows)


def main():
    rows = load_labels()
    if not rows:
        print("No labeled rows found -- fill in the 'relevant' column (y/n) in candidates_to_label.csv first.")
        return

    by_topic = defaultdict(list)
    by_source = defaultdict(list)
    by_source_cs_only = defaultdict(list)

    for r in rows:
        by_topic[r["topic"]].append(r)
        by_source[r["source"]].append(r)
        if r["domain"] == "cs":
            by_source_cs_only[r["source"]].append(r)

    print("=" * 60)
    print("Precision by topic")
    print("=" * 60)
    for topic, topic_rows in by_topic.items():
        p = precision(topic_rows)
        print(f"  {p:.2f}  ({sum(r['relevant'] for r in topic_rows)}/{len(topic_rows)})  {topic}")

    overall_p = precision(rows)
    print(f"\nOverall precision (all topics, all sources): {overall_p:.2f} "
          f"({sum(r['relevant'] for r in rows)}/{len(rows)})")

    print("\n" + "=" * 60)
    print("Precision by source (all topics)")
    print("=" * 60)
    for source, source_rows in sorted(by_source.items()):
        p = precision(source_rows)
        print(f"  {source:20s} {p:.2f}  ({sum(r['relevant'] for r in source_rows)}/{len(source_rows)})")

    print("\n" + "=" * 60)
    print("Precision by source -- CS-domain topics only")
    print("(this is the number that actually tests the Semantic Scholar hypothesis)")
    print("=" * 60)
    if not by_source_cs_only:
        print("  No CS-domain rows found.")
    for source, source_rows in sorted(by_source_cs_only.items()):
        p = precision(source_rows)
        print(f"  {source:20s} {p:.2f}  ({sum(r['relevant'] for r in source_rows)}/{len(source_rows)})")
    print("=" * 60)


if __name__ == "__main__":
    main()
