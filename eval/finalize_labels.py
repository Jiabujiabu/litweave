"""Fills any remaining unlabeled rows in candidates_to_label_zh.xlsx with the
AI suggestion, and adds a '标注来源' (label source) column marking each row
as 人工 (human-labeled) or AI外推 (extrapolated from the LLM judge) -- kept
for traceability, since the write-up should disclose this split rather than
present the whole set as human-labeled.

Only run this after check_agreement.py shows high agreement across every
topic on the human-labeled subset -- extrapolating without that check would
make the "relevant" column circular (LLM judged against itself).

Usage:
    python eval/finalize_labels.py
"""

import os
import sys
from copy import copy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from openpyxl import load_workbook

from score_labels import RELEVANT_TRUE, RELEVANT_FALSE  # noqa: E402

XLSX_PATH = os.path.join(os.path.dirname(__file__), "candidates_to_label_zh.xlsx")


def main():
    wb = load_workbook(XLSX_PATH)
    ws = wb.active

    header = [c.value for c in ws[1]]
    col = {name: idx + 1 for idx, name in enumerate(header)}

    source_col = len(header) + 1
    ws.cell(row=1, column=source_col, value="标注来源")
    ws.cell(row=1, column=source_col).font = copy(ws.cell(row=1, column=1).font)
    ws.cell(row=1, column=source_col).fill = copy(ws.cell(row=1, column=1).fill)

    filled, kept = 0, 0
    for row_idx in range(2, ws.max_row + 1):
        verdict_cell = ws.cell(row=row_idx, column=col["你的判断"])
        val = str(verdict_cell.value or "").strip().lower()
        if val in RELEVANT_TRUE or val in RELEVANT_FALSE:
            ws.cell(row=row_idx, column=source_col, value="人工")
            kept += 1
        else:
            suggestion = ws.cell(row=row_idx, column=col["AI建议"]).value
            verdict_cell.value = suggestion
            ws.cell(row=row_idx, column=source_col, value="AI外推")
            filled += 1

    ws.column_dimensions[ws.cell(row=1, column=source_col).column_letter].width = 12

    wb.save(XLSX_PATH)
    print(f"Kept {kept} human-labeled rows, extrapolated {filled} rows from the AI suggestion.")
    print(f"Saved back to {XLSX_PATH}")


if __name__ == "__main__":
    main()
