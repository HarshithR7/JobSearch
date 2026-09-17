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

_APPLE_THEME_CSS = """
<style>
:root {
    --apple-bg: #f5f5f7;
    --apple-card: #ffffff;
    --apple-text: #1d1d1f;
    --apple-text-secondary: #6e6e73;
    --apple-blue: #0071e3;
    --apple-blue-hover: #0077ed;
    --apple-radius: 18px;
    --apple-shadow: 0 2px 10px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.05);
}

html, body, [class*="css"], .stMarkdown, .stText {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text",
                 "Segoe UI", Helvetica, Arial, sans-serif !important;
}

.stApp { background: var(--apple-bg); }

[data-testid="stSidebar"] {
    background: rgba(255, 255, 255, 0.85);
    backdrop-filter: blur(24px);
    border-right: 1px solid rgba(0, 0, 0, 0.06);
}

h1 { font-weight: 700 !important; letter-spacing: -0.02em; color: var(--apple-text); }
h2, h3 { font-weight: 600 !important; letter-spacing: -0.01em; color: var(--apple-text); }
p, .stMarkdown, .stCaption { color: var(--apple-text); }

/* Bordered containers (st.container(border=True)) read as cards */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: var(--apple-radius) !important;
    box-shadow: var(--apple-shadow) !important;
    border: 1px solid rgba(0, 0, 0, 0.04) !important;
    background: var(--apple-card) !important;
    transition: box-shadow 0.18s ease, transform 0.18s ease;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.10) !important;
}

/* Buttons */
.stButton > button, .stLinkButton > a, .stFormSubmitButton > button, .stDownloadButton > button {
    border-radius: 980px !important;
    font-weight: 590 !important;
    transition: all 0.15s ease !important;
    border: none !important;
}
.stButton > button:hover, .stLinkButton > a:hover, .stFormSubmitButton > button:hover, .stDownloadButton > button:hover {
    transform: scale(1.03);
}
.stFormSubmitButton > button, .stButton > button[kind="primary"] {
    background: var(--apple-blue) !important;
    color: white !important;
}
.stFormSubmitButton > button:hover, .stButton > button[kind="primary"]:hover {
    background: var(--apple-blue-hover) !important;
}

/* Tabs styled as an iOS segmented control */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: rgba(118, 118, 128, 0.12);
    border-radius: 10px;
    padding: 4px;
    gap: 2px;
}
[data-testid="stTabs"] button[data-baseweb="tab"] {
    border-radius: 8px !important;
    font-weight: 590 !important;
    color: var(--apple-text-secondary) !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    background: white !important;
    color: var(--apple-text) !important;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12);
}

/* Metrics */
[data-testid="stMetricValue"] { font-weight: 700 !important; color: var(--apple-text) !important; }
[data-testid="stMetricLabel"] { color: var(--apple-text-secondary) !important; font-weight: 500 !important; }

/* Pills used across Job Feed */
.jc-pill { border-radius: 980px !important; font-weight: 590 !important; }

/* Inputs */
.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div {
    border-radius: 12px !important;
}

[data-testid="stExpander"] {
    border-radius: 14px !important;
    border: 1px solid rgba(0, 0, 0, 0.06) !important;
}
</style>
"""


def inject_apple_theme() -> None:
    """Shared visual theme across every page — Apple-inspired: soft neutral
    background, SF-style font stack, rounded cards with subtle shadow/hover
    lift, pill buttons, segmented-control tabs. One shared function rather
    than per-page CSS blocks, so styling can't drift between pages. Targets
    Streamlit's documented data-testid attributes (stable across versions)
    rather than generated class names."""
    st.markdown(_APPLE_THEME_CSS, unsafe_allow_html=True)


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
