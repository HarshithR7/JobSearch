import pandas as pd
import streamlit as st

from app_common import inject_apple_theme
from database.session import get_session
from database.repositories import company_repo
from database.models import Company

st.set_page_config(page_title="Companies", page_icon="🏢", layout="wide")
inject_apple_theme()
st.title("🏢 Companies")
st.caption("Replaces the startups2.xlsx workflow — seeded from your spreadsheet, "
           "grown by discovery collectors (RemoteOK/HN), and editable below.")

with get_session() as db:
    companies = company_repo.list_all(db)

if not companies:
    st.info("No companies yet. Run `python -m scripts.seed_companies` to import your spreadsheet.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total companies", len(companies))
c2.metric("With known ATS", sum(1 for c in companies if c.ats_type not in ("unknown", "none")))
c3.metric("Needs review", sum(1 for c in companies if c.needs_review))
c4.metric("H-1B history on record", sum(1 for c in companies if c.visa_sponsor_known))
st.write("")

tiers = sorted({c.priority_tier for c in companies if c.priority_tier})
techs = sorted({c.technology_tag for c in companies if c.technology_tag})

col1, col2, col3 = st.columns(3)
tier_filter = col1.multiselect("Priority tier", tiers)
tech_filter = col2.multiselect("Technology", techs)
needs_review_only = col3.checkbox("Needs review only")

filtered = [
    c for c in companies
    if (not tier_filter or c.priority_tier in tier_filter)
    and (not tech_filter or c.technology_tag in tech_filter)
    and (not needs_review_only or c.needs_review)
]

df = pd.DataFrame(
    [
        {
            "id": c.id,
            "Name": c.name,
            "Tier": c.priority_tier,
            "Technology": c.technology_tag,
            "Country": c.country,
            "ATS": c.ats_type,
            "Website": c.website,
            "Visa sponsor known": c.visa_sponsor_known,
            "Needs review": c.needs_review,
            "Notes": c.legacy_notes,
        }
        for c in filtered
    ]
)

st.caption(f"{len(filtered)} of {len(companies)} companies")
edited = st.data_editor(
    df,
    hide_index=True,
    disabled=["id", "Name", "Technology", "Country", "ATS", "Website"],
    column_config={
        "Tier": st.column_config.SelectboxColumn(options=["Tier 1 Primary", "Tier 2 High-Potential", "Tier 3 Startup", "Tier 4 Research"]),
    },
    key="companies_editor",
)

if st.button("Save tier/notes edits"):
    with get_session() as db:
        for _, row in edited.iterrows():
            company = db.get(Company, int(row["id"]))
            if company is None:
                continue
            company.priority_tier = row["Tier"]
            company.needs_review = bool(row["Needs review"])
            company.legacy_notes = row["Notes"]
    st.success("Saved.")
    st.rerun()
