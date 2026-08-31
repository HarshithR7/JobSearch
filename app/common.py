"""Small shared helpers for Streamlit pages. Each page is its own script
execution in Streamlit's multipage model, so the profile selector is
repeated on every page (using the same widget key keeps the choice
in sync across page switches within one session)."""

import streamlit as st

from database.session import get_session
from database.repositories import profile_repo


def select_profile():
    """Renders a profile picker in the sidebar and returns the selected
    Profile object (or None if no profiles exist yet)."""
    with get_session() as db:
        profiles = profile_repo.list_all(db)

    if not profiles:
        st.sidebar.info("No profiles yet — create one on the Profiles page.")
        return None

    names = [p.name for p in profiles]
    selected_name = st.sidebar.selectbox("Profile", names, key="active_profile")

    with get_session() as db:
        return profile_repo.get_by_name(db, selected_name)
