import anthropic
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

existing_names = {p.name for p in profiles}
editing_name = st.session_state.get("profiles_editing_name")
edit_profile = next((p for p in profiles if p.name == editing_name), None) if editing_name else None

if profiles:
    st.subheader("Existing profiles")
    for p in profiles:
        with st.expander(f"{p.name} — {'resume parsed' if p.resume_structured else 'no resume yet'}"):
            st.write(f"**Email:** {p.email or '—'}")
            st.write(f"**Target roles:** {', '.join(p.target_roles or []) or '—'}")
            st.write(f"**Target tech tags:** {', '.join(p.target_tech_tags or []) or '—'}")
            st.write(f"**Visa status:** {p.visa_status or '—'}")
            st.write(f"**GitHub:** {p.github_username or '—'}")

            col1, col2 = st.columns(2)
            if col1.button("Edit", key=f"edit_{p.id}"):
                st.session_state["profiles_editing_name"] = p.name
                st.session_state.pop("profiles_pending_delete", None)
                st.rerun()

            if st.session_state.get("profiles_pending_delete") == p.id:
                st.warning(f"Delete **{p.name}**? This also removes their job matches, "
                           f"applications, and tailored resume versions — cannot be undone.")
                dcol1, dcol2 = st.columns(2)
                if dcol1.button("Yes, delete permanently", key=f"confirm_delete_{p.id}"):
                    with get_session() as db:
                        profile_repo.delete_profile(db, p.id)
                    st.session_state.pop("profiles_pending_delete", None)
                    if editing_name == p.name:
                        st.session_state.pop("profiles_editing_name", None)
                    st.success(f"Deleted '{p.name}'.")
                    st.rerun()
                if dcol2.button("Cancel", key=f"cancel_delete_{p.id}"):
                    st.session_state.pop("profiles_pending_delete", None)
                    st.rerun()
            elif col2.button("Delete", key=f"delete_{p.id}"):
                st.session_state["profiles_pending_delete"] = p.id
                st.rerun()

st.divider()

if edit_profile:
    st.subheader(f"Editing: {edit_profile.name}")
    if st.button("Cancel edit / start a new profile instead"):
        st.session_state.pop("profiles_editing_name", None)
        st.rerun()
else:
    st.subheader("Create a new profile")
    if existing_names:
        st.caption("Existing profiles: " + ", ".join(sorted(existing_names))
                   + ". Pick your own name to create a separate profile — reusing "
                   "one of these updates that person's profile instead. To edit an "
                   "existing profile, use the Edit button above instead of retyping it here.")

with st.form("profile_form"):
    name = st.text_input("Name", value=edit_profile.name if edit_profile else "",
                          placeholder="Harshith", disabled=edit_profile is not None)
    if edit_profile:
        st.caption("Name can't be changed here — delete and recreate this profile to rename it.")
    email = st.text_input("Email", value=(edit_profile.email if edit_profile else "") or "", placeholder="you@example.com")
    target_roles = st.text_input(
        "Target roles (comma-separated)",
        value=", ".join(edit_profile.target_roles or []) if edit_profile else "",
        placeholder="RISC-V Verification Engineer, ASIC Design Engineer",
    )
    target_tech_tags = st.text_input(
        "Target technology tags (comma-separated)",
        value=", ".join(edit_profile.target_tech_tags or []) if edit_profile else "",
        placeholder="RISC-V, ASIC, AI accelerator",
    )
    visa_status = st.text_input(
        "Visa status (optional, helps prioritize sponsor-known companies)",
        value=(edit_profile.visa_status if edit_profile else "") or "",
    )
    location_preference = st.text_input(
        "Location preference",
        value=(edit_profile.location_preference if edit_profile else "") or "",
        placeholder="Remote / Bay Area / open to relocation",
    )
    github_username = st.text_input(
        "GitHub username (feeds project recommendations)",
        value=(edit_profile.github_username if edit_profile else None) or settings.GITHUB_USERNAME,
    )

    st.markdown("**Resume** — paste text or upload a .docx. This becomes the immutable master resume every tailored version is constrained to.")
    if edit_profile and edit_profile.resume_raw_text:
        st.caption("Leave blank to keep the current resume as-is; paste/upload only to replace it.")
    resume_text_input = st.text_area(
        "Paste resume text", value=(edit_profile.resume_raw_text if edit_profile else "") or "", height=200,
    )
    resume_file = st.file_uploader("...or upload a .docx to replace it", type=["docx"])

    submitted = st.form_submit_button("Save profile")


def _save_profile(name_clean: str, raw_text: str) -> None:
    with get_session() as db:
        profile = profile_repo.get_by_name(db, name_clean)
        if profile is None:
            profile = Profile(name=name_clean)
            db.add(profile)

        profile.email = email.strip() or None
        profile.target_roles = [r.strip() for r in target_roles.split(",") if r.strip()] or None
        profile.target_tech_tags = [t.strip() for t in target_tech_tags.split(",") if t.strip()] or None
        profile.visa_status = visa_status.strip() or None
        profile.location_preference = location_preference.strip() or None
        profile.github_username = github_username.strip() or None

        if raw_text and raw_text != (profile.resume_raw_text or ""):
            profile.resume_raw_text = raw_text
            try:
                with st.spinner("Parsing resume with Claude..."):
                    profile.resume_structured = resume_parser.parse_resume_text(raw_text)
                st.success("Resume parsed and saved.")
            except (AIUnavailableError, anthropic.APIError, ValueError) as exc:
                # Covers missing key (AIUnavailableError), any API-side failure
                # (no credits, rate limit, outage — anthropic.APIError), and
                # malformed model output (json.JSONDecodeError is a ValueError).
                # Without this the exception would propagate out of get_session()
                # and roll back the whole profile save, not just the parse step.
                st.warning(f"Resume text saved, but not parsed yet: {exc}")

    st.session_state.pop("profiles_pending_overwrite", None)
    st.session_state.pop("profiles_editing_name", None)
    st.success(f"Profile '{name_clean}' saved.")
    st.rerun()


if submitted:
    name_clean = name.strip()
    if not name_clean:
        st.error("Name is required.")
    else:
        raw_text = resume_text_input.strip()
        if resume_file is not None:
            raw_text = resume_parser.extract_text_from_docx(resume_file.read())

        is_editing_self = edit_profile is not None and edit_profile.name == name_clean
        if name_clean in existing_names and not is_editing_self and st.session_state.get("profiles_pending_overwrite") != name_clean:
            # A different person typing an already-taken name would otherwise
            # silently overwrite that person's profile (get_by_name treats
            # same name == same person) — require an explicit confirm click.
            st.session_state["profiles_pending_overwrite"] = name_clean
            st.session_state["profiles_pending_raw_text"] = raw_text
        else:
            _save_profile(name_clean, raw_text)

pending_name = st.session_state.get("profiles_pending_overwrite")
if pending_name:
    st.warning(f"A profile named **{pending_name}** already exists. Saving will update "
               f"that profile, not create a separate one — if this isn't your existing "
               f"profile, go back and pick a different name instead.")
    col1, col2 = st.columns(2)
    if col1.button(f"Yes, update '{pending_name}'"):
        _save_profile(pending_name, st.session_state.get("profiles_pending_raw_text", ""))
    if col2.button("Cancel"):
        st.session_state.pop("profiles_pending_overwrite", None)
        st.session_state.pop("profiles_pending_raw_text", None)
        st.rerun()
