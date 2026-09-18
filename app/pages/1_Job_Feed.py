import sys
from pathlib import Path

# See app/app.py for why this is here — Streamlit Community Cloud doesn't
# add the project root to sys.path the way local `python -m streamlit`
# does, causing ModuleNotFoundError on deploy for root-level modules like
# app_common even though the same code runs fine locally.
_root = Path(__file__).resolve().parent
while not (_root / "app_common.py").exists() and _root != _root.parent:
    _root = _root.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from collections import Counter
from datetime import datetime, timedelta, timezone

import anthropic
import streamlit as st

from sqlalchemy import select

from app_common import inject_apple_theme, select_profile
from database.session import get_session
from database.models import JobPosting, Company
from database.repositories import match_repo, application_repo
from analysis import gap_advisor
from analysis.ai_client import AIUnavailableError
from analysis.job_matcher import detect_experience_signal, detect_work_auth_flags, is_likely_us_posting, strip_html

# Free-text visa_status values that mean "does not need employer
# sponsorship" — anything else (F1, OPT, STEM OPT, H-1B, blank, ...) is
# treated as sponsorship-relevant for the no-sponsorship warning below.
NO_SPONSORSHIP_NEEDED_STATUSES = {"us citizen", "citizen", "green card", "permanent resident", "pr", "gc"}

# Sources that are third-party job boards rather than a company's own ATS
# — the closest honest equivalent in this data model to "External" jobs.
EXTERNAL_SOURCES = {"remoteok", "hn_hiring"}

APPLIED_STATUSES = {"applied", "oa", "recruiter_screen", "interview", "final", "offer", "rejected"}

BAND_LABEL = {
    "apply_immediately": "Apply Immediately",
    "strong": "Strong Match",
    "worth_considering": "Worth Considering",
    "stretch": "Stretch",
    "low_priority": "Low Priority",
}
BAND_COLOR = {
    "apply_immediately": "#16a34a",
    "strong": "#22c55e",
    "worth_considering": "#eab308",
    "stretch": "#f97316",
    "low_priority": "#9ca3af",
}

st.set_page_config(page_title="Job Feed", page_icon="🔥", layout="wide")
inject_apple_theme()

st.markdown("""
<style>
.jc-pill {
    display: inline-block; padding: 2px 10px; border-radius: 999px;
    font-size: 0.78rem; font-weight: 600; margin: 0 6px 6px 0; white-space: nowrap;
}
.jc-pill-green { background: #dcfce7; color: #15803d; }
.jc-pill-red { background: #fee2e2; color: #b91c1c; }
.jc-pill-yellow { background: #fef9c3; color: #a16207; }
.jc-pill-gray { background: #f1f5f9; color: #475569; }
.jc-pill-blue { background: #dbeafe; color: #1d4ed8; }
.jc-ring-wrap { text-align: center; }
.jc-band-label { text-align: center; font-size: 0.75rem; font-weight: 700; margin-top: 2px; }
.jc-title { font-size: 1.05rem; font-weight: 700; margin: 2px 0 0 0; }
.jc-sub { color: #64748b; font-size: 0.85rem; margin-bottom: 6px; }
</style>
""", unsafe_allow_html=True)

st.title("🔥 Job Feed")

profile = select_profile()
if profile is None:
    st.stop()

if not profile.resume_structured:
    st.warning("This profile has no parsed resume yet — add one on the Profiles page, "
               "then run `python main.py match-jobs --profile " + profile.name + "` to score jobs.")
    st.stop()


def _score_ring_svg(score: int, band: str, size: int = 64) -> str:
    color = BAND_COLOR.get(band, "#9ca3af")
    radius = size / 2 - 6
    circumference = 2 * 3.14159265 * radius
    offset = circumference * (1 - max(0, min(100, score)) / 100)
    c = size / 2
    return f"""
    <svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
      <circle cx="{c}" cy="{c}" r="{radius}" stroke="#e5e7eb" stroke-width="6" fill="none"/>
      <circle cx="{c}" cy="{c}" r="{radius}" stroke="{color}" stroke-width="6" fill="none"
              stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{offset:.1f}"
              stroke-linecap="round" transform="rotate(-90 {c} {c})"/>
      <text x="{c}" y="{c + 5}" text-anchor="middle" font-size="{size * 0.26:.0f}"
            font-weight="700" fill="{color}">{score}%</text>
    </svg>
    """.strip()


def _relative_time(dt: datetime | None) -> str:
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    delta = now - dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else now - dt
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return "just now"
    if hours < 24:
        return f"{int(hours)}h ago"
    days = int(hours // 24)
    return f"{days}d ago" if days < 30 else dt.date().isoformat()


def _work_auth_badges(work_auth: dict, needs_sponsorship: bool | None, company: Company | None, experience: dict) -> str:
    pills = []
    if work_auth["citizenship_required"]:
        pills.append('<span class="jc-pill jc-pill-red">⚠ Citizenship required</span>')
    if work_auth["clearance_required"]:
        pills.append('<span class="jc-pill jc-pill-red">⚠ Clearance/export control</span>')
    if work_auth["no_sponsorship"] and needs_sponsorship:
        pills.append('<span class="jc-pill jc-pill-red">⚠ No sponsorship</span>')
    if work_auth["sponsorship_mentioned"]:
        pills.append('<span class="jc-pill jc-pill-green">✓ Sponsorship mentioned</span>')
    if company and company.visa_sponsor_known:
        pills.append('<span class="jc-pill jc-pill-green">H-1B history on record</span>')
    if experience.get("min_years_required"):
        # Flag only, never a score adjustment — the free engine has no way
        # to know the candidate's own years of experience (see: the
        # d-matrix "100% but wants 8+ years" report), so this just makes
        # the requirement visible instead of silently invisible.
        pills.append(f'<span class="jc-pill jc-pill-yellow">⏳ Wants {experience["min_years_required"]}+ yrs exp</span>')
    elif experience.get("senior_title"):
        pills.append('<span class="jc-pill jc-pill-yellow">⏳ Senior-level title</span>')
    return "".join(pills)


def _render_job_card(r: dict, needs_sponsorship: bool | None, status_badge: str | None = None, key_prefix: str = "card") -> None:
    # key_prefix matters: the same posting can legitimately appear in more
    # than one tab (Recommended + Liked, or Recommended + External), and
    # Streamlit widget keys must be unique across the whole script run, not
    # just within one tab — caught by AppTest as a StreamlitDuplicateElementKey
    # before this ever reached a browser.
    posting, company, match = r["posting"], r["company"], r["match"]
    work_auth = r.get("work_auth") or detect_work_auth_flags(posting.title, posting.raw_description or "")
    experience = r.get("experience") or detect_experience_signal(posting.title, posting.raw_description or "")

    with st.container(border=True):
        col_main, col_score = st.columns([5, 1])
        with col_main:
            top_pills = []
            rel = _relative_time(posting.posted_at or posting.first_seen_at)
            if rel:
                top_pills.append(f'<span class="jc-pill jc-pill-blue">{rel}</span>')
            if posting.source in EXTERNAL_SOURCES:
                top_pills.append(f'<span class="jc-pill jc-pill-gray">via {posting.source}</span>')
            us_signal = is_likely_us_posting(posting.location)
            if us_signal is False:
                top_pills.append('<span class="jc-pill jc-pill-gray">🌍 Non-US</span>')
            elif us_signal is None:
                top_pills.append('<span class="jc-pill jc-pill-gray">❔ Location unknown</span>')
            if status_badge:
                top_pills.append(f'<span class="jc-pill jc-pill-gray">{status_badge}</span>')
            st.markdown("".join(top_pills), unsafe_allow_html=True)
            st.markdown(f'<div class="jc-title">{posting.title}</div>', unsafe_allow_html=True)
            loc_bits = [company.name if company else "Unknown company"]
            if posting.location:
                loc_bits.append(posting.location)
            if posting.remote_flag:
                loc_bits.append("Remote")
            st.markdown(f'<div class="jc-sub">{" · ".join(loc_bits)}</div>', unsafe_allow_html=True)
            badges = _work_auth_badges(work_auth, needs_sponsorship, company, experience)
            if badges:
                st.markdown(badges, unsafe_allow_html=True)
        with col_score:
            st.markdown(f'<div class="jc-ring-wrap">{_score_ring_svg(match.overall_score, match.band)}</div>',
                        unsafe_allow_html=True)
            st.markdown(f'<div class="jc-band-label" style="color:{BAND_COLOR.get(match.band, "#9ca3af")}">'
                        f'{BAND_LABEL.get(match.band, match.band)}</div>', unsafe_allow_html=True)

        if match.rationale:
            st.caption(match.rationale)
        skill_pills = "".join(f'<span class="jc-pill jc-pill-green">✓ {s}</span>' for s in (match.matched_skills or []))
        skill_pills += "".join(f'<span class="jc-pill jc-pill-yellow">△ {s}</span>' for s in (match.missing_skills or []))
        if skill_pills:
            st.markdown(skill_pills, unsafe_allow_html=True)

        if posting.raw_description and st.checkbox("Show full job description", key=f"{key_prefix}_show_desc_{posting.id}"):
            st.write(strip_html(posting.raw_description))

        col1, col2 = st.columns(2)
        col1.link_button("View posting", posting.url)
        if col2.button("Mark Interested", key=f"{key_prefix}_interested_{posting.id}"):
            with get_session() as db:
                application = application_repo.get_or_create(db, profile.id, posting.id)
                application_repo.set_status(db, application, "interested")
            st.success("Marked interested — see the Applications page.")


with get_session() as db:
    # No practical cap — every live posting is already scored (the free
    # engine scores all of them), and a low default "Minimum match score"
    # filter below does the real work of keeping the rendered list small.
    # A hardcoded limit=300 here was hiding postings ranked below #300 even
    # when a user dropped that filter to see more (real report: "where are
    # the other 3000 jobs" — all of them were scored, just never fetched).
    matches = match_repo.top_for_profile(db, profile.id, limit=10_000)

    # Bulk-fetch postings/companies instead of one db.get() per match — the
    # per-row loop this replaced was up to 2*len(matches) individual round
    # trips to a remote Postgres instance, which measured at 88 seconds for
    # 3,358 matches (vs 9.6s for everything else on this page combined).
    posting_ids = [m.job_posting_id for m in matches]
    postings_by_id = {p.id: p for p in db.scalars(select(JobPosting).where(JobPosting.id.in_(posting_ids)))}
    company_ids = {p.company_id for p in postings_by_id.values()}
    companies_by_id = {c.id: c for c in db.scalars(select(Company).where(Company.id.in_(company_ids)))}
    matches_by_posting_id = {m.job_posting_id: m for m in matches}

    rows = []
    for m in matches:
        posting = postings_by_id.get(m.job_posting_id)
        if posting is None or posting.status != "live":
            continue
        rows.append({"match": m, "posting": posting, "company": companies_by_id.get(posting.company_id)})

    applications = application_repo.list_for_profile(db, profile.id)
    app_posting_ids = [a.job_posting_id for a in applications if a.job_posting_id not in postings_by_id]
    if app_posting_ids:
        for p in db.scalars(select(JobPosting).where(JobPosting.id.in_(app_posting_ids))):
            postings_by_id[p.id] = p
        missing_company_ids = {p.company_id for p in postings_by_id.values()} - companies_by_id.keys()
        if missing_company_ids:
            for c in db.scalars(select(Company).where(Company.id.in_(missing_company_ids))):
                companies_by_id[c.id] = c

    app_rows = []
    for a in applications:
        posting = postings_by_id.get(a.job_posting_id)
        if posting is None:
            continue
        app_rows.append({
            "application": a, "posting": posting, "company": companies_by_id.get(posting.company_id),
            "match": matches_by_posting_id.get(posting.id),
        })

if not rows:
    st.info("No scored jobs yet. Run `python main.py scan-jobs` then `python main.py match-jobs --profile "
            f"{profile.name}` to populate this page.")
    st.stop()

for r in rows:
    r["work_auth"] = detect_work_auth_flags(r["posting"].title, r["posting"].raw_description or "")
    r["experience"] = detect_experience_signal(r["posting"].title, r["posting"].raw_description or "")

needs_sponsorship = (profile.visa_status or "").strip().lower() not in NO_SPONSORSHIP_NEEDED_STATUSES
if not profile.visa_status:
    needs_sponsorship = None  # unknown — don't assume either way

liked = [r for r in app_rows if r["application"].status == "interested"]
applied = [r for r in app_rows if r["application"].status in APPLIED_STATUSES]
external = [r for r in rows if r["posting"].source in EXTERNAL_SOURCES]

now = datetime.now(timezone.utc)
today = now.date()
apply_today = sum(1 for r in rows if r["match"].band == "apply_immediately")
strong = sum(1 for r in rows if r["match"].band == "strong")
new_today = sum(1 for r in rows if r["posting"].first_seen_at.date() == today)
posted_24h = sum(
    1 for r in rows if r["posting"].posted_at and (now - r["posting"].posted_at.replace(tzinfo=timezone.utc)) < timedelta(hours=24)
)
c1, c2, c3, c4 = st.columns(4)
c1.metric("🔥 Apply Today", apply_today)
c2.metric("⭐ Strong Matches", strong)
c3.metric("🆕 New Today", new_today)
c4.metric("⏰ Posted <24h", posted_24h)

tab_recommended, tab_liked, tab_applied, tab_external = st.tabs([
    f"🎯 Recommended ({len(rows)})",
    f"❤️ Liked ({len(liked)})",
    f"✅ Applied ({len(applied)})",
    f"🌐 External ({len(external)})",
])

with tab_recommended:
    st.caption(f"🟢 skill you have · 🟡 skill gap · 🔴 possible work-auth barrier — "
               f"all {len(rows)} live postings are scored below, filters control what's shown")
    search = st.text_input("🔍 Search by title or company", key="jf_search")

    tech_options = sorted({r["company"].technology_tag for r in rows if r["company"] and r["company"].technology_tag})
    tech_filter = st.multiselect("Technology", tech_options)
    min_score = st.slider("Minimum match score", 0, 100, 60)

    # Defaults to ON when the profile clearly needs sponsorship (visa_status
    # set and not a citizen/green-card equivalent) — repeated real feedback
    # was that non-US postings kept showing up because this was opt-in and
    # easy to forget to click, even though the backend was already
    # correctly flagging them (verified directly: a Bengaluru posting's
    # location string does trip is_likely_us_posting() -> False).
    default_quick_filters = ["US jobs only"] if needs_sponsorship else []
    quick_filters = st.pills(
        "Quick filters",
        ["Remote only", "Hide work-auth barriers", "US jobs only", "Entry-level", "Experienced"],
        selection_mode="multi",
        default=default_quick_filters,
        help="\"Hide work-auth barriers\" hides postings with detected citizenship/clearance "
             "requirements or explicit no-sponsorship language — screening signal only, verify "
             "independently. \"US jobs only\" hides postings with a known non-US location signal; "
             "postings with no location text, or no signal either way, are kept by default. "
             "On by default since your profile's visa status implies you need a US employer. "
             "\"Entry-level\" keeps postings without a senior-sounding title and requiring 3 years "
             "of experience or less (or no years stated). \"Experienced\" keeps the opposite — "
             "senior-sounding titles or 4+ years required. Select both to see everything (same as "
             "neither); across these companies only ~5% of postings are entry-level-titled, so this "
             "filters the senior-heavy majority out of the way instead of making you scroll past it.",
    )
    remote_only = "Remote only" in quick_filters
    hide_barriers = "Hide work-auth barriers" in quick_filters
    us_only = "US jobs only" in quick_filters
    entry_level_only = "Entry-level" in quick_filters
    experienced_only = "Experienced" in quick_filters

    def _is_entry_level(exp: dict) -> bool:
        if exp.get("senior_title"):
            return False
        years = exp.get("min_years_required")
        return years is None or years <= 3

    sort_by = st.radio(
        "Sort by", ["Match score (best first)", "Newest first"],
        horizontal=True, key="jf_sort_by",
    )

    search_lower = search.strip().lower()
    filtered = [
        r for r in rows
        if r["match"].overall_score >= min_score
        and (not remote_only or r["posting"].remote_flag)
        and (not tech_filter or (r["company"] and r["company"].technology_tag in tech_filter))
        and (not hide_barriers or not (r["work_auth"]["citizenship_required"] or r["work_auth"]["clearance_required"]
                                        or (r["work_auth"]["no_sponsorship"] and needs_sponsorship)))
        # Strict (is True, not "is not False") when explicitly toggled on —
        # 57% of top-scored matches turned out to have no location data at
        # all (the generic-careers-page collector never extracts one), and
        # "US jobs only" should mean confirmed US, not "US or unverifiable."
        and (not us_only or is_likely_us_posting(r["posting"].location) is True)
        # Only filters when exactly one of the pair is picked — both or
        # neither selected means "don't care", not "match nothing".
        and (entry_level_only == experienced_only or _is_entry_level(r["experience"]) == entry_level_only)
        and (not search_lower or search_lower in r["posting"].title.lower()
             or (r["company"] and search_lower in r["company"].name.lower()))
    ]

    if sort_by == "Newest first":
        filtered.sort(
            key=lambda r: r["posting"].posted_at or r["posting"].first_seen_at,
            reverse=True,
        )

    st.caption(f"{len(filtered)} of {len(rows)} scored jobs match your filters")

    # Paginated rather than rendering the whole filtered list at once —
    # even after the N+1 query fix, a few thousand full interactive cards
    # (SVG ring + badges + buttons + checkbox each) is real client-side
    # rendering weight for a browser, separate from server-side query time.
    PAGE_SIZE = 50
    if "jf_visible_count" not in st.session_state:
        st.session_state["jf_visible_count"] = PAGE_SIZE
    visible = filtered[: st.session_state["jf_visible_count"]]

    for r in visible:
        _render_job_card(r, needs_sponsorship, key_prefix="rec")

    remaining = len(filtered) - len(visible)
    if remaining > 0:
        if st.button(f"Show {min(PAGE_SIZE, remaining)} more ({remaining} remaining)"):
            st.session_state["jf_visible_count"] += PAGE_SIZE
            st.rerun()

with tab_liked:
    if not liked:
        st.info("Nothing liked yet — click \"Mark Interested\" on a job in Recommended.")
    for r in liked:
        if r["match"]:
            _render_job_card(r, needs_sponsorship, status_badge="❤️ Liked", key_prefix="liked")
        else:
            st.write(f"{r['posting'].title} @ {r['company'].name if r['company'] else '?'} — not yet scored")

with tab_applied:
    if not applied:
        st.info("Nothing applied to yet — track progress from the Applications page once you apply.")
    for r in applied:
        label = r["application"].status.replace("_", " ").title()
        if r["match"]:
            _render_job_card(r, needs_sponsorship, status_badge=label, key_prefix="applied")
        else:
            st.write(f"{r['posting'].title} @ {r['company'].name if r['company'] else '?'} — {label}")
    if applied:
        st.caption("Update status in detail on the Applications page.")

with tab_external:
    st.caption("Postings discovered via RemoteOK/HN Hiring boards rather than a company's own ATS page.")
    if not external:
        st.info("No externally-sourced postings in your current top matches.")
    for r in external:
        _render_job_card(r, needs_sponsorship, key_prefix="ext")

st.divider()
st.subheader("🧩 Skills Gap")
st.caption("Aggregated across all your scored jobs (Recommended tab) — "
           "the skills that keep costing you match points.")

all_missing = [s for r in rows for s in (r["match"].missing_skills or [])]
if not all_missing:
    st.caption("No recurring skill gaps found across your scored jobs.")
else:
    gap_counts = Counter(s.lower() for s in all_missing)
    top_gaps = gap_counts.most_common(5)
    gap_cols = st.columns(len(top_gaps))
    for col, (skill, count) in zip(gap_cols, top_gaps):
        col.metric(skill, f"{count} jobs")

    if not profile.github_username:
        st.caption("Add a GitHub username on the Profiles page to get concrete project "
                   "recommendations for closing these gaps.")
    elif st.button("Suggest project additions to close these gaps"):
        try:
            with st.spinner("Checking your GitHub repos and generating recommendations with Claude..."):
                result = gap_advisor.recommend_projects(profile.github_username, all_missing)
            for rec in result.get("recommendations", []):
                with st.container(border=True):
                    st.markdown(f"**{rec.get('repo', '?')}** — {rec.get('addition', '')}")
                    st.caption(rec.get("why", ""))
                    if rec.get("skills_closed"):
                        st.markdown("Closes: " + ", ".join(rec["skills_closed"]))
        except (AIUnavailableError, anthropic.APIError, ValueError) as exc:
            st.warning(f"Couldn't generate recommendations: {exc}")
