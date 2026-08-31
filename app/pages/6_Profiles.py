import streamlit as st

from config import settings
from database.session import get_session
from database.models import Profile
from database.repositories import profile_repo
from analysis import resume_parser
from analysis.ai_client import AIUnavailableError

st.set_page_config(page_title="Profiles", page_icon="👤", layout="wide")
st.title("👤 Profiles")

with get_session() as db:
    profiles = profile_repo.list_all(db)

if profiles:
    st.subheader("Existing profiles")
    for p in profiles:
        with st.expander(f"{p.name} — {'resume parsed' if p.resume_structured else 'no resume yet'}"):
            st.write(f"**Email:** {p.email or '—'}")
            st.write(f"**Target roles:** {', '.join(p.target_roles or []) or '—'}")
            st.write(f"**Target tech tags:** {', '.join(p.target_tech_tags or []) or '—'}")
            st.write(f"**Visa status:** {p.visa_status or '—'}")
            st.write(f"**GitHub:** {p.github_username or '—'}")

st.divider()
st.subheader("Create / update a profile")

with st.form("profile_form"):
    name = st.text_input("Name", placeholder="Harshith")
    email = st.text_input("Email", placeholder="you@example.com")
    target_roles = st.text_input("Target roles (comma-separated)", placeholder="RISC-V Verification Engineer, ASIC Design Engineer")
    target_tech_tags = st.text_input("Target technology tags (comma-separated)", placeholder="RISC-V, ASIC, AI accelerator")
    visa_status = st.text_input("Visa status (optional, helps prioritize sponsor-known companies)")
    location_preference = st.text_input("Location preference", placeholder="Remote / Bay Area / open to relocation")
    github_username = st.text_input("GitHub username (feeds project recommendations)", value=settings.GITHUB_USERNAME)

    st.markdown("**Resume** — paste text or upload a .docx. This becomes the immutable master resume every tailored version is constrained to.")
    resume_text_input = st.text_area("Paste resume text", height=200)
    resume_file = st.file_uploader("...or upload a .docx", type=["docx"])

    submitted = st.form_submit_button("Save profile")

if submitted:
    if not name.strip():
        st.error("Name is required.")
    else:
        raw_text = resume_text_input.strip()
        if resume_file is not None:
            raw_text = resume_parser.extract_text_from_docx(resume_file.read())

        with get_session() as db:
            profile = profile_repo.get_by_name(db, name.strip())
            if profile is None:
                profile = Profile(name=name.strip())
                db.add(profile)

            profile.email = email.strip() or None
            profile.target_roles = [r.strip() for r in target_roles.split(",") if r.strip()] or None
            profile.target_tech_tags = [t.strip() for t in target_tech_tags.split(",") if t.strip()] or None
            profile.visa_status = visa_status.strip() or None
            profile.location_preference = location_preference.strip() or None
            profile.github_username = github_username.strip() or None

            if raw_text:
                profile.resume_raw_text = raw_text
                try:
                    with st.spinner("Parsing resume with Claude..."):
                        profile.resume_structured = resume_parser.parse_resume_text(raw_text)
                    st.success("Resume parsed and saved.")
                except AIUnavailableError as exc:
                    st.warning(f"Resume text saved, but not parsed yet: {exc}")

        st.success(f"Profile '{name}' saved.")
        st.rerun()
