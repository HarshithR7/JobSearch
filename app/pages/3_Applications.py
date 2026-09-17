import streamlit as st

from app_common import inject_apple_theme, select_profile
from database.session import get_session
from database.models import JobPosting, Company, Application
from database.models.application import APPLICATION_STATUSES
from database.repositories import application_repo

st.set_page_config(page_title="Applications", page_icon="📋", layout="wide")
inject_apple_theme()
st.title("📋 Applications")

profile = select_profile()
if profile is None:
    st.stop()

with get_session() as db:
    applications = application_repo.list_for_profile(db, profile.id)
    board = {status: [] for status in APPLICATION_STATUSES}
    for app_row in applications:
        posting = db.get(JobPosting, app_row.job_posting_id)
        company = db.get(Company, posting.company_id) if posting else None
        board.setdefault(app_row.status, []).append({"application": app_row, "posting": posting, "company": company})

if not applications:
    st.info("Nothing tracked yet — mark jobs 'Interested' from the Job Feed page to start a pipeline.")
    st.stop()

STATUS_LABEL = {
    "discovered": "Discovered",
    "interested": "Interested",
    "resume_prepared": "Resume Prepared",
    "applied": "Applied",
    "oa": "OA",
    "recruiter_screen": "Recruiter Screen",
    "interview": "Interview",
    "final": "Final",
    "offer": "🎉 Offer",
    "rejected": "Rejected",
}

for status in APPLICATION_STATUSES:
    items = board.get(status, [])
    if not items:
        continue
    st.subheader(f"{STATUS_LABEL[status]} ({len(items)})")
    for item in items:
        posting, company, app_row = item["posting"], item["company"], item["application"]
        if posting is None:
            continue
        with st.expander(f"{posting.title} — {company.name if company else '?'}"):
            st.write(f"Notes: {app_row.notes or '—'}")
            st.write(f"Follow-up date: {app_row.follow_up_date or '—'}")
            new_status = st.selectbox(
                "Status", APPLICATION_STATUSES, index=APPLICATION_STATUSES.index(app_row.status),
                key=f"status_{app_row.id}",
            )
            note = st.text_input("Note for this status change", key=f"note_{app_row.id}")
            col1, col2 = st.columns(2)
            col1.link_button("View posting", posting.url)
            if col2.button("Update", key=f"update_{app_row.id}"):
                with get_session() as db:
                    application_repo.set_status(db, db.get(Application, app_row.id), new_status, note or None)
                st.rerun()
