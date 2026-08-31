"""Shared helpers for Streamlit pages, kept at the project root (not
inside app/) deliberately: Streamlit's multipage execution model runs
app/pages/*.py as standalone scripts, and importing this as `app.common`
collides with the main entrypoint being app/app.py — Python ends up with
`app` bound to that non-package script module, so `from app.common import
...` fails with "'app' is not a package". A bare top-level import from
the project root (already on sys.path — see any page's `database.*`
imports) sidesteps the collision entirely."""

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
