import streamlit as st

from database.session import get_session
from database.repositories import profile_repo

st.set_page_config(page_title="Career Command Center", page_icon="🎯", layout="wide")

st.sidebar.title("🎯 Career Command Center")

with get_session() as db:
    profiles = profile_repo.list_all(db)
    profile_names = [p.name for p in profiles]

if profile_names:
    selected = st.sidebar.selectbox("Profile", profile_names, key="active_profile")
    st.session_state["active_profile_name"] = selected
else:
    st.sidebar.info("No profiles yet — create one on the Profiles page.")

st.title("Job Search Portal")
st.markdown(
    """
Use the pages in the sidebar:

- **Job Feed** — today's live postings, ranked by match score
- **Companies** — your ~300-company tracker
- **Applications** — pipeline board
- **Resume Studio** — tailor a resume for a specific job
- **Prep Center** — books/topics/Q&A per role
- **Profiles** — manage who's using this portal and their resumes
"""
)

if not profile_names:
    st.warning("Start on the **Profiles** page to create your profile and upload a resume.")
