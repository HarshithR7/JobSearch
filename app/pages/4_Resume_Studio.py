import anthropic
import streamlit as st

from app_common import inject_apple_theme, select_profile
from database.session import get_session
from database.models import JobPosting, Company, ResumeVersion
from database.repositories import job_repo
from analysis import resume_tailor
from analysis.ai_client import AIUnavailableError

st.set_page_config(page_title="Resume Studio", page_icon="📄", layout="wide")
inject_apple_theme()
st.title("📄 Resume Studio")

profile = select_profile()
if profile is None:
    st.stop()

if not profile.resume_structured:
    st.warning("Add a resume for this profile on the Profiles page first.")
    st.stop()

with get_session() as db:
    postings = job_repo.list_live(db, limit=500)
    options = {}
    for p in postings:
        company = db.get(Company, p.company_id)
        options[f"{p.title} — {company.name if company else '?'} (id {p.id})"] = p.id

if not options:
    st.info("No live postings yet — run `python main.py scan-jobs` first.")
    st.stop()

label = st.selectbox("Pick a job to tailor for", list(options.keys()))
job_id = options[label]

if st.button("Generate tailored resume"):
    with get_session() as db:
        posting = db.get(JobPosting, job_id)
        try:
            with st.spinner("Tailoring with Claude (constrained to your master resume — no invented content)..."):
                tailored = resume_tailor.generate_tailored_content(
                    profile.resume_structured, posting.title, posting.raw_description or posting.title
                )
            text = resume_tailor.to_plain_text(tailored)
            docx_bytes = resume_tailor.render_docx(
                tailored, profile.name, profile.email or ""
            )
            version = ResumeVersion(profile_id=profile.id, job_posting_id=posting.id, generated_text=text, model_used="claude")
            db.add(version)
            db.flush()
            st.session_state["last_tailored_text"] = text
            st.session_state["last_tailored_docx"] = docx_bytes
            st.session_state["last_tailored_version_id"] = version.id
        except (AIUnavailableError, anthropic.APIError, ValueError) as exc:
            st.error(str(exc))

if st.session_state.get("last_tailored_text"):
    st.success(f"Saved as resume_version id={st.session_state['last_tailored_version_id']}")
    st.text_area("Tailored resume (plain text)", st.session_state["last_tailored_text"], height=400)
    st.download_button(
        "Download as .docx",
        data=st.session_state["last_tailored_docx"],
        file_name=f"{profile.name.replace(' ', '_')}_tailored_resume.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

st.divider()
st.subheader("📚 Past tailored resumes")
st.caption("Every generated version is saved permanently (resume_version table) — "
           "this is the only place to see one again after you leave this page.")

with get_session() as db:
    versions = list(
        db.query(ResumeVersion)
        .filter(ResumeVersion.profile_id == profile.id)
        .order_by(ResumeVersion.created_at.desc())
        .all()
    )
    version_postings = {}
    if versions:
        posting_ids = {v.job_posting_id for v in versions if v.job_posting_id}
        for p in db.query(JobPosting).filter(JobPosting.id.in_(posting_ids)).all():
            company = db.get(Company, p.company_id)
            version_postings[p.id] = (p, company)

if not versions:
    st.caption("None yet — generate one above.")
else:
    for v in versions:
        posting, company = version_postings.get(v.job_posting_id, (None, None))
        label = f"id {v.id} — {v.created_at.strftime('%Y-%m-%d %H:%M UTC')}"
        if posting:
            label += f" — {posting.title} @ {company.name if company else '?'}"
        with st.expander(label):
            st.text_area("Text", v.generated_text, height=250, key=f"past_resume_{v.id}", label_visibility="collapsed")
            st.download_button(
                "Download as .txt",
                data=v.generated_text,
                file_name=f"{profile.name.replace(' ', '_')}_resume_v{v.id}.txt",
                mime="text/plain",
                key=f"download_past_{v.id}",
            )
