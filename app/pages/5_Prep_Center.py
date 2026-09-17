import sys
from pathlib import Path

# See app/app.py for why this is here.
_root = Path(__file__).resolve().parent
while not (_root / "app_common.py").exists() and _root != _root.parent:
    _root = _root.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import anthropic
import streamlit as st

from app_common import inject_apple_theme
from database.session import get_session
from database.repositories import prep_repo
from analysis import prep_generator
from analysis.ai_client import AIUnavailableError

st.set_page_config(page_title="Prep Center", page_icon="🎤", layout="wide")
inject_apple_theme()
st.title("🎤 Interview Prep Center")

with get_session() as db:
    from database.models import RoleArchetype
    existing = db.query(RoleArchetype).order_by(RoleArchetype.name).all()
    existing_names = [r.name for r in existing]

col1, col2 = st.columns(2)
choice = col1.selectbox("Existing role archetype", ["<new>"] + existing_names)
new_name = col2.text_input("Or enter a new role name", placeholder="RISC-V Verification Engineer")
tech_tag = st.text_input("Primary technology (optional)", placeholder="RISC-V")

role_name = new_name.strip() if choice == "<new>" else choice

if role_name and st.button("Generate / refresh prep content"):
    with get_session() as db:
        archetype = prep_repo.get_or_create_archetype(db, role_name, tech_tag or None)
        try:
            with st.spinner("Generating with Claude..."):
                content = prep_generator.generate_prep_content(role_name, tech_tag or None)
            prep_repo.upsert_content(
                db, role_archetype_id=archetype.id,
                books=content.get("books", []), topics=content.get("topics", []),
                courses=content.get("courses", []), sample_qna=content.get("sample_qna", []),
                model_used="claude",
            )
            st.success("Generated.")
        except (AIUnavailableError, anthropic.APIError, ValueError) as exc:
            st.error(str(exc))

if role_name:
    from database.models import PrepContent

    with get_session() as db:
        archetype = prep_repo.get_or_create_archetype(db, role_name, tech_tag or None)
        content = db.query(PrepContent).filter_by(role_archetype_id=archetype.id).first()

    if content:
        st.subheader("📚 Books")
        for b in content.books or []:
            st.write(f"- {b}")
        st.subheader("🧠 Topics")
        for t in content.topics or []:
            st.write(f"- {t}")
        st.subheader("🎓 Courses / Resources")
        for c in content.courses or []:
            st.write(f"- {c}")
        st.subheader("❓ Sample Q&A")
        for qa in content.sample_qna or []:
            with st.expander(qa.get("q", "")):
                st.write(qa.get("a", ""))
    else:
        st.info("No prep content generated yet for this role — click the button above.")
