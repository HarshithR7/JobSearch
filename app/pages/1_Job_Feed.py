from datetime import datetime, timedelta, timezone

import streamlit as st

from app.common import select_profile
from database.session import get_session
from database.models import JobPosting, Company
from database.repositories import match_repo, application_repo

st.set_page_config(page_title="Job Feed", page_icon="🔥", layout="wide")
st.title("🔥 Job Feed")

profile = select_profile()
if profile is None:
    st.stop()

if not profile.resume_structured:
    st.warning("This profile has no parsed resume yet — add one on the Profiles page, "
               "then run `python main.py match-jobs --profile " + profile.name + "` to score jobs.")
    st.stop()

BAND_LABEL = {
    "apply_immediately": "🟢 Apply Immediately",
    "strong": "🟢 Strong Opportunity",
    "worth_considering": "🟡 Worth Considering",
    "stretch": "🟠 Stretch",
    "low_priority": "🔴 Low Priority",
}

with get_session() as db:
    matches = match_repo.top_for_profile(db, profile.id, limit=300)
    rows = []
    for m in matches:
        posting = db.get(JobPosting, m.job_posting_id)
        if posting is None or posting.status != "live":
            continue
        company = db.get(Company, posting.company_id)
        rows.append({"match": m, "posting": posting, "company": company})

if not rows:
    st.info("No scored jobs yet. Run `python main.py scan-jobs` then `python main.py match-jobs --profile "
            f"{profile.name}` to populate this page.")
    st.stop()

now = datetime.now(timezone.utc)
today = now.date()
apply_today = sum(1 for r in rows if r["match"].band == "apply_immediately")
strong = sum(1 for r in rows if r["match"].band == "strong")
new_today = sum(1 for r in rows if r["posting"].first_seen_at.date() == today)
posted_24h = sum(
    1 for r in rows if r["posting"].posted_at and (now - r["posting"].posted_at.replace(tzinfo=timezone.utc)) < timedelta(hours=24)
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("🔥 Apply Today", apply_today)
c2.metric("⭐ Strong Matches", strong)
c3.metric("🆕 New Today", new_today)
c4.metric("⏰ Posted <24h", posted_24h)

# rows already sorted by overall_score desc (match_repo.top_for_profile)
top = rows[0]
st.subheader("Top Opportunity")
with st.container(border=True):
    st.markdown(f"**{top['posting'].title}** — {top['company'].name if top['company'] else 'Unknown'}")
    st.markdown(f"Match: **{top['match'].overall_score}/100** — {BAND_LABEL.get(top['match'].band, top['match'].band)}")
    if top["match"].matched_skills:
        st.markdown("✓ " + "  ✓ ".join(top["match"].matched_skills[:8]))
    if top["match"].missing_skills:
        st.markdown("⚠ Missing: " + ", ".join(top["match"].missing_skills[:8]))
    st.link_button("View posting", top["posting"].url)

st.divider()
st.subheader("All scored jobs")

tech_options = sorted({r["company"].technology_tag for r in rows if r["company"] and r["company"].technology_tag})
col_a, col_b, col_c = st.columns(3)
tech_filter = col_a.multiselect("Technology", tech_options)
remote_only = col_b.checkbox("Remote only")
min_score = col_c.slider("Minimum match score", 0, 100, 60)

filtered = [
    r for r in rows
    if r["match"].overall_score >= min_score
    and (not remote_only or r["posting"].remote_flag)
    and (not tech_filter or (r["company"] and r["company"].technology_tag in tech_filter))
]

for r in filtered:
    posting, company, match = r["posting"], r["company"], r["match"]
    header = f"{match.overall_score}/100 · {BAND_LABEL.get(match.band, match.band)} — {posting.title} @ {company.name if company else '?'}"
    with st.expander(header):
        st.write(f"Location: {posting.location or '—'} | Remote: {posting.remote_flag or False} | Source: {posting.source}")
        st.write(f"First seen: {posting.first_seen_at.date()}")
        if match.rationale:
            st.write(match.rationale)
        if match.matched_skills:
            st.markdown("✓ " + ", ".join(match.matched_skills))
        if match.missing_skills:
            st.markdown("⚠ Missing: " + ", ".join(match.missing_skills))
        col1, col2 = st.columns(2)
        col1.link_button("View posting", posting.url)
        if col2.button("Mark Interested", key=f"interested_{posting.id}"):
            with get_session() as db:
                application = application_repo.get_or_create(db, profile.id, posting.id)
                application_repo.set_status(db, application, "interested")
            st.success("Marked interested — see the Applications page.")
