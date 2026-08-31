"""H-1B LCA disclosure data cross-reference — flags Company.visa_sponsor_known.

Not a daily collector: the Department of Labor publishes this quarterly at
https://www.dol.gov/agencies/eta/office-foreign-labor-certification/performance
as a downloadable CSV/XLSX ("LCA Disclosure Data"), and the exact URL/filename
changes every quarter, so this module works from a file Harshith downloads
by hand rather than guessing at a URL. Run it manually after each quarterly
refresh:

    python -m collectors.h1b_lca data/lca_disclosure_latest.csv

It expects an "Employer Name" (or similarly-named) column, matches it
case-insensitively against `company.name`, and sets
`company.visa_sponsor_known = True` for matches. Companies with no match
are left as None (unknown), never marked False — absence in one quarter's
data isn't proof a company doesn't sponsor.
"""

import sys

import pandas as pd

from config import logger
from database.session import get_session
from database.repositories import company_repo

EMPLOYER_COLUMN_CANDIDATES = ("employer_name", "employer", "petitioner_name", "employer_business_name")


def _find_employer_column(columns: list[str]) -> str | None:
    normalized = {c.lower().strip().replace(" ", "_"): c for c in columns}
    for candidate in EMPLOYER_COLUMN_CANDIDATES:
        if candidate in normalized:
            return normalized[candidate]
    return None


def cross_reference(csv_path: str) -> int:
    df = pd.read_csv(csv_path, usecols=lambda c: True, low_memory=False, on_bad_lines="skip")
    employer_col = _find_employer_column(list(df.columns))
    if employer_col is None:
        raise ValueError(f"Could not find an employer-name column in {csv_path}; columns were: {list(df.columns)}")

    sponsors = {str(name).strip().lower() for name in df[employer_col].dropna().unique()}

    matched = 0
    with get_session() as db:
        for company in company_repo.list_all(db):
            if company.name.strip().lower() in sponsors:
                company.visa_sponsor_known = True
                matched += 1
    logger.info(f"H1B LCA cross-reference: {matched} companies matched as known visa sponsors")
    return matched


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    cross_reference(sys.argv[1])
