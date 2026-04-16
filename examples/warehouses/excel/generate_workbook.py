"""Generate budget.xlsx from fixture data.

Excel files are binary, so we don't check them in — regenerate with:
    python generate_workbook.py

Requires openpyxl: `pip install openpyxl`
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook


ROWS = [
    ("dept", "line_item", "budgeted", "spent", "as_of"),
    ("Engineering", "Salaries",       420000, 418500, "2026-04-15"),
    ("Engineering", "Cloud",          80000,  74200,  "2026-04-15"),
    ("Engineering", "Tooling",        25000,  22100,  "2026-04-15"),
    ("Marketing",   "Ads",            150000, 142000, "2026-04-15"),
    ("Marketing",   "Events",         60000,  31500,  "2026-04-15"),
    ("Marketing",   "Content",        40000,  38900,  "2026-04-15"),
    ("Sales",       "Salaries",       310000, 309000, "2026-04-15"),
    ("Sales",       "Travel",         45000,  19800,  "2026-04-15"),
    ("Ops",         "Office",         30000,  28500,  "2026-04-15"),
    ("Ops",         "Legal",          55000,  47000,  "2026-04-15"),
    ("Ops",         "Software",       35000,  34800,  "2026-04-15"),
    ("Finance",     "Audit",          70000,  68000,  "2026-04-15"),
]


def main() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Budget"
    for row in ROWS:
        ws.append(row)
    out = Path(__file__).parent / "budget.xlsx"
    wb.save(out)
    print(f"Wrote {out} ({len(ROWS) - 1} rows + header)")


if __name__ == "__main__":
    main()
