"""One-time import of Harshith's existing company research into the
`company` table: the startups spreadsheet (startups2, Analog, Sheet1,
Consultancy sheets — Important/DARPA sheets are strategy notes, not clean
company rows, so they're skipped) plus companies_important.txt.

Usage:
    python -m scripts.seed_companies
    python -m scripts.seed_companies --excel /path/to/startups2.xlsx --text /path/to/companies_important.txt
"""

import argparse
import re
from pathlib import Path

import openpyxl

from config import logger
from database.session import get_session
from database.repositories import company_repo

DEFAULT_EXCEL_CANDIDATES = [
    Path("/mnt/c/Users/harsh/OneDrive/Desktop/JOB/startups2(AutoRecovered).xlsx"),
    Path(r"C:\Users\harsh\OneDrive\Desktop\JOB\startups2(AutoRecovered).xlsx"),
]
DEFAULT_TEXT_CANDIDATES = [
    Path("/mnt/c/Users/harsh/Downloads/companies_important.txt"),
    Path(r"C:\Users\harsh\Downloads\companies_important.txt"),
]

EXCEL_SHEETS = ["startups2", "Analog", "Sheet1"]


def _first_existing(candidates: list[Path]) -> Path | None:
    return next((p for p in candidates if p.exists()), None)


def _seed_from_excel(path: Path) -> int:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    count = 0
    with get_session() as db:
        for sheet_name in EXCEL_SHEETS:
            if sheet_name not in wb.sheetnames:
                continue
            ws = wb[sheet_name]
            rows = ws.iter_rows(values_only=True)
            for row in rows:
                name = row[0] if row else None
                if not name or not isinstance(name, str) or name.strip().lower() == "company":
                    continue
                website = row[1] if len(row) > 1 and isinstance(row[1], str) else None
                tech_tag = row[2] if len(row) > 2 and isinstance(row[2], str) else None
                country = row[3] if len(row) > 3 and isinstance(row[3], str) else None
                founded = row[4] if len(row) > 4 and isinstance(row[4], int) else None
                description = row[5] if len(row) > 5 and isinstance(row[5], str) else None
                # Remaining columns are ad-hoc tracking notes (dates, "applied for...",
                # "no careers page", etc.) — preserved verbatim rather than parsed.
                legacy_notes = " | ".join(str(c) for c in row[6:] if c not in (None, ""))

                company_repo.upsert(
                    db,
                    name=name.strip(),
                    website=website.strip() if website else None,
                    technology_tag=tech_tag,
                    country=country,
                    founded_year=founded,
                    description=description,
                    legacy_notes=legacy_notes or None,
                    source="startups2",
                )
                count += 1
    return count


NAME_DESC_SPLIT = re.compile(r"\s+--?\s+")


def _seed_from_text(path: Path) -> int:
    count = 0
    with get_session() as db:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.lower().startswith("http"):
                continue
            parts = NAME_DESC_SPLIT.split(line, maxsplit=1)
            name = parts[0].strip()
            description = parts[1].strip() if len(parts) > 1 else None
            if not name or len(name) > 120:
                continue
            company_repo.upsert(db, name=name, description=description, source="importlist")
            count += 1
    return count


def run(excel_path: str | None = None, text_path: str | None = None) -> None:
    excel_file = Path(excel_path) if excel_path else _first_existing(DEFAULT_EXCEL_CANDIDATES)
    text_file = Path(text_path) if text_path else _first_existing(DEFAULT_TEXT_CANDIDATES)

    total = 0
    if excel_file:
        n = _seed_from_excel(excel_file)
        logger.info(f"Seeded/updated {n} companies from {excel_file}")
        total += n
    else:
        logger.warning("Startups spreadsheet not found in default locations — pass --excel explicitly")

    if text_file:
        n = _seed_from_text(text_file)
        logger.info(f"Seeded/updated {n} companies from {text_file}")
        total += n
    else:
        logger.warning("companies_important.txt not found in default locations — pass --text explicitly")

    logger.info(f"Seed complete: {total} rows processed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--excel", default=None)
    parser.add_argument("--text", default=None)
    args = parser.parse_args()
    run(args.excel, args.text)
