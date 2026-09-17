from collections import Counter
from datetime import datetime, timedelta, timezone

import anthropic
import streamlit as st

from app_common import select_profile
from database.session import get_session
from database.models import JobPosting, Company
from database.repositories import match_repo, application_repo
from analysis import gap_advisor
from analysis.ai_client import AIUnavailableError
from analysis.job_matcher import detect_work_auth_flags, strip_html

# Free-text visa_status values that mean "does not need employer
# sponsorship" — anything else (F1, OPT, STEM OPT, H-1B, blank, ...) is
# treated as sponsorship-relevant for the no-sponsorship warning below.
NO_SPONSORSHIP_NEEDED_STATUSES = {"us citizen", "citizen", "green card", "permanent resident", "pr", "gc"}

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

needs_sponsorship = (profile.visa_status or "").strip().lower() not in NO_SPONSORSHIP_NEEDED_STATUSES
if not profile.visa_status:
    needs_sponsorship = None  # unknown — don't assume either way

tech_options = sorted({r["company"].technology_tag for r in rows if r["company"] and r["company"].technology_tag})
col_a, col_b, col_c, col_d = st.columns(4)
tech_filter = col_a.multiselect("Technology", tech_options)
remote_only = col_b.checkbox("Remote only")
min_score = col_c.slider("Minimum match score", 0, 100, 60)
hide_barriers = col_d.checkbox(
    "Hide detected work-auth barriers",
    help="Hides postings with citizenship/clearance requirements or explicit "
         "no-sponsorship language detected in the text. Screening signal only "
         "— verify independently before ruling a job out.",
)

for r in rows:
    r["work_auth"] = detect_work_auth_flags(r["posting"].title, r["posting"].raw_description or "")

filtered = [
    r for r in rows
    if r["match"].overall_score >= min_score
    and (not remote_only or r["posting"].remote_flag)
    and (not tech_filter or (r["company"] and r["company"].technology_tag in tech_filter))
    and (not hide_barriers or not (r["work_auth"]["citizenship_required"] or r["work_auth"]["clearance_required"]
                                    or (r["work_auth"]["no_sponsorship"] and needs_sponsorship)))
]

for r in filtered:
    posting, company, match, work_auth = r["posting"], r["company"], r["match"], r["work_auth"]
    barrier = work_auth["citizenship_required"] or work_auth["clearance_required"] or (work_auth["no_sponsorship"] and needs_sponsorship)
    visa_icon = " 🚫" if barrier else (" 🟢" if work_auth["sponsorship_mentioned"] else "")
    header = f"{match.overall_score}/100 · {BAND_LABEL.get(match.band, match.band)}{visa_icon} — {posting.title} @ {company.name if company else '?'}"
    with st.expander(header):
        st.write(f"Location: {posting.location or '—'} | Remote: {posting.remote_flag or False} | Source: {posting.source}")
        if posting.posted_at:
            st.write(f"Posted: {posting.posted_at.date()}")
        else:
            st.write(f"Posted date not provided by this source — first seen by our scanner: {posting.first_seen_at.date()}")

        st.markdown("**🎯 Match**")
        if match.rationale:
            st.write(match.rationale)
        if match.matched_skills:
            st.markdown("✓ " + ", ".join(match.matched_skills))
        if match.missing_skills:
            st.markdown("⚠ Missing: " + ", ".join(match.missing_skills))

        if posting.raw_description and st.checkbox("Show full job description", key=f"show_desc_{posting.id}"):
            st.write(strip_html(posting.raw_description))

        st.markdown("**🪪 Work authorization** — from posting text only, screening signal, verify independently")
        if work_auth["citizenship_required"] or work_auth["clearance_required"]:
            st.error("⚠️ Possible barrier: " + ", ".join(work_auth["matched_phrases"][:4]))
        elif work_auth["no_sponsorship"] and needs_sponsorship:
            st.error(f"⚠️ Posting says no visa sponsorship (matched: \"{work_auth['matched_phrases'][0]}\") "
                     f"— you're on \"{profile.visa_status}\"")
        elif work_auth["no_sponsorship"]:
            st.caption(f"Posting mentions no sponsorship (matched: \"{work_auth['matched_phrases'][0]}\")")
        elif work_auth["sponsorship_mentioned"]:
            st.success(f"✓ Mentions visa sponsorship (matched: \"{work_auth['matched_phrases'][0]}\")")
        else:
            st.caption("No citizenship/clearance/sponsorship language detected in this posting.")
        if company and company.visa_sponsor_known:
            st.caption("🟢 This company has H-1B LCA filing history on record (historical evidence, not a guarantee for this specific role).")

        col1, col2 = st.columns(2)
        col1.link_button("View posting", posting.url)
        if col2.button("Mark Interested", key=f"interested_{posting.id}"):
            with get_session() as db:
                application = application_repo.get_or_create(db, profile.id, posting.id)
                application_repo.set_status(db, application, "interested")
            st.success("Marked interested — see the Applications page.")

st.divider()
st.subheader("🧩 Skills Gap")
st.caption("Aggregated across all your scored jobs (not just the filtered view above) — "
           "the skills that keep costing you match points.")

all_missing = [s for r in rows for s in (r["match"].missing_skills or [])]
if not all_missing:
    st.caption("No recurring skill gaps found across your scored jobs.")
else:
    gap_counts = Counter(s.lower() for s in all_missing)
    top_gaps = gap_counts.most_common(5)
    gap_cols = st.columns(len(top_gaps))
    for col, (skill, count) in zip(gap_cols, top_gaps):
        col.metric(skill, f"{count} jobs")

    if not profile.github_username:
        st.caption("Add a GitHub username on the Profiles page to get concrete project "
                   "recommendations for closing these gaps.")
    elif st.button("Suggest project additions to close these gaps"):
        try:
            with st.spinner("Checking your GitHub repos and generating recommendations with Claude..."):
                result = gap_advisor.recommend_projects(profile.github_username, all_missing)
            for rec in result.get("recommendations", []):
                with st.container(border=True):
                    st.markdown(f"**{rec.get('repo', '?')}** — {rec.get('addition', '')}")
                    st.caption(rec.get("why", ""))
                    if rec.get("skills_closed"):
                        st.markdown("Closes: " + ", ".join(rec["skills_closed"]))
        except (AIUnavailableError, anthropic.APIError, ValueError) as exc:
            st.warning(f"Couldn't generate recommendations: {exc}")
