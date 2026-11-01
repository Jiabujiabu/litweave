"""Exports candidates_to_label.csv as a fully Chinese-language .xlsx for
review: topic, title, abstract, and the LLM's reasoning are all translated.
Adds a dropdown (data validation) on the verdict column so filling it in
Excel is a click, not typing.

Usage:
    python eval/export_excel_zh.py
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from nodes import call_llm, MOCK_MODE  # noqa: E402

CSV_PATH = os.path.join(os.path.dirname(__file__), "candidates_to_label.csv")
XLSX_PATH = os.path.join(os.path.dirname(__file__), "candidates_to_label_zh.xlsx")

DOMAIN_ZH = {"cs": "计算机科学/理工", "humanities": "人文社科", "interdisciplinary": "跨学科"}
SUGGESTION_ZH = {"y": "相关", "n": "不相关"}

PAPER_CHUNK_SIZE = 10  # title+abstract+reason per item -- keep chunks small, each item is sizable
TOPIC_CHUNK_SIZE = 20  # topics are short phrases -- fine to batch more per call


def _chat_json(prompt: str, system: str):
    from model_access import local_model_session
    with local_model_session():
        content = call_llm(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            task="translate", language="zh",
        )
    content = content.strip().strip("```json").strip("```").strip()
    return json.loads(content)


def translate_topics(topics: list[str]) -> dict[str, str]:
    """Translates the small set of distinct topics once each (not once per row)."""
    if MOCK_MODE:
        return {t: t for t in topics}

    mapping = {}
    for start in range(0, len(topics), TOPIC_CHUNK_SIZE):
        chunk = topics[start:start + TOPIC_CHUNK_SIZE]
        numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(chunk))
        prompt = f"""将下面每个研究主题短语翻译成简洁准确的中文，保留专业术语（可保留常见英文缩写如 LLM、RAG 等不翻译）。
只返回一个 JSON 字符串数组，顺序与原文一一对应，不要有其他文字。

{numbered}"""
        try:
            translated = _chat_json(prompt, "你是专业的学术翻译，只返回 JSON 数组。")
            if len(translated) != len(chunk):
                raise ValueError("length mismatch")
        except (json.JSONDecodeError, ValueError):
            translated = chunk
        for orig, zh in zip(chunk, translated):
            mapping[orig] = zh
    return mapping


def translate_papers(rows: list[dict]) -> list[dict]:
    """Returns title_zh/summary_zh/reason_zh per row, same order as `rows`."""
    if MOCK_MODE:
        return [{"title_zh": r["title"], "summary_zh": r["summary"], "reason_zh": r.get("llm_reason", "")} for r in rows]

    results = [None] * len(rows)
    for start in range(0, len(rows), PAPER_CHUNK_SIZE):
        chunk = rows[start:start + PAPER_CHUNK_SIZE]
        numbered = "\n".join(
            f"{i}. Title: {r['title']}\n   Abstract: {r['summary'] or '(no abstract)'}\n   Reason: {r.get('llm_reason', '')}"
            for i, r in enumerate(chunk)
        )
        prompt = f"""将下面每篇论文的标题(title)、摘要(abstract)、以及一句判断理由(reason)分别翻译成简洁准确的中文，
保留专业术语准确性（可保留常见英文缩写如 LLM、RAG、GNN 等不翻译）。
只返回一个 JSON 数组，每个元素形如 {{"index": <int>, "title_zh": "...", "summary_zh": "...", "reason_zh": "..."}}，
顺序与原文一一对应，不要有其他文字。

{numbered}"""
        try:
            judgments = _chat_json(prompt, "你是专业的学术翻译，只返回 JSON 数组。")
        except json.JSONDecodeError:
            judgments = []

        for j in judgments:
            idx = j.get("index")
            if idx is None or not (0 <= idx < len(chunk)):
                continue
            results[start + idx] = {
                "title_zh": j.get("title_zh", chunk[idx]["title"]),
                "summary_zh": j.get("summary_zh", chunk[idx]["summary"]),
                "reason_zh": j.get("reason_zh", chunk[idx].get("llm_reason", "")),
            }

        for i, r in enumerate(chunk):
            if results[start + i] is None:  # chunk failed or an index was missing from the response
                results[start + i] = {"title_zh": r["title"], "summary_zh": r["summary"], "reason_zh": r.get("llm_reason", "")}

        print(f"  translated {min(start + PAPER_CHUNK_SIZE, len(rows))}/{len(rows)} papers")
    return results


def main():
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    print("Translating topics...")
    unique_topics = sorted({r["topic"] for r in rows})
    topic_zh_map = translate_topics(unique_topics)

    print(f"Translating {len(rows)} paper titles/abstracts/reasons to Chinese...")
    translations = translate_papers(rows)

    wb = Workbook()
    ws = wb.active
    ws.title = "候选文献审核"

    headers = ["主题", "领域", "来源", "标题", "摘要", "链接", "AI建议", "AI理由", "你的判断"]
    ws.append(headers)

    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")
    ws.freeze_panes = "A2"

    for r, tr in zip(rows, translations):
        ws.append([
            topic_zh_map.get(r["topic"], r["topic"]),
            DOMAIN_ZH.get(r["domain"], r["domain"]),
            r["source"],
            tr["title_zh"],
            tr["summary_zh"],
            r["url"],
            SUGGESTION_ZH.get(r["llm_suggestion"], r["llm_suggestion"]),
            tr["reason_zh"],
            "",  # 你的判断 -- filled via dropdown
        ])

    widths = {"A": 32, "B": 14, "C": 14, "D": 38, "E": 45, "F": 30, "G": 10, "H": 30, "I": 12}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    dv = DataValidation(type="list", formula1='"相关,不相关"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"I2:I{ws.max_row}")

    wb.save(XLSX_PATH)
    print(f"\nWritten to {XLSX_PATH}")


if __name__ == "__main__":
    main()
