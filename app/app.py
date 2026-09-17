import streamlit as st
from sqlalchemy import func, select

from app_common import inject_apple_theme
from database.session import get_session
from database.repositories import profile_repo, company_repo, application_repo, match_repo
from database.models import JobPosting

st.set_page_config(page_title="Career Command Center", page_icon="🎯", layout="wide")
inject_apple_theme()

st.sidebar.title("🎯 Career Command Center")

with get_session() as db:
    profiles = profile_repo.list_all(db)
    profile_names = [p.name for p in profiles]

if profile_names:
    selected = st.sidebar.selectbox("Profile", profile_names, key="active_profile")
    st.session_state["active_profile_name"] = selected
else:
    st.sidebar.info("No profiles yet — create one on the Profiles page.")

st.markdown('<h1 style="font-size:2.6rem; margin-bottom:0;">Career Command Center</h1>', unsafe_allow_html=True)
st.caption("Your job search, in one place.")

if profile_names:
    with get_session() as db:
        profile = profile_repo.get_by_name(db, selected)
        n_companies = len(company_repo.list_all(db))
        n_live = db.scalar(select(func.count(JobPosting.id)).where(JobPosting.status == "live")) or 0
        matches = match_repo.top_for_profile(db, profile.id, limit=10_000)
        n_strong = sum(1 for m in matches if m.band in ("apply_immediately", "strong"))
        apps = application_repo.list_for_profile(db, profile.id)
        n_pipeline = sum(1 for a in apps if a.status != "discovered")

    st.write("")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏢 Companies tracked", n_companies)
    c2.metric("🔥 Live postings", n_live)
    c3.metric("⭐ Strong matches", n_strong)
    c4.metric("📋 In your pipeline", n_pipeline)
    st.write("")

st.divider()

NAV_ITEMS = [
    ("🔥", "Job Feed", "Today's live postings, ranked by match score", "pages/1_Job_Feed.py"),
    ("🏢", "Companies", "Your company tracker — tiers, tech tags, notes", "pages/2_Companies.py"),
    ("📋", "Applications", "Your pipeline board, one card per application", "pages/3_Applications.py"),
    ("📄", "Resume Studio", "Tailor a resume for a specific job", "pages/4_Resume_Studio.py"),
    ("🎤", "Prep Center", "Books, topics, and sample Q&A per role", "pages/5_Prep_Center.py"),
    ("👤", "Profiles", "Manage who's using this portal and their resumes", "pages/6_Profiles.py"),
]

cols = st.columns(3)
for i, (icon, title, desc, target) in enumerate(NAV_ITEMS):
    with cols[i % 3]:
        with st.container(border=True):
            st.markdown(f"### {icon} {title}")
            st.caption(desc)
            st.page_link(target, label="Open →")

if not profile_names:
    st.warning("Start on the **Profiles** page to create your profile and upload a resume.")
