"""Scores one job posting against one profile's structured resume.

Claude produces sub-scores for each weighted factor plus matched/missing
skills and a short rationale; the weighted rollup itself is plain
arithmetic here, not left to the model, so scores stay comparable across
jobs and profiles (see plan: "Job Match Score" rubric)."""

import html
import re

from analysis.ai_client import complete_json

WEIGHTS = {
    "required_skills": 25,
    "experience": 20,
    "project_relevance": 15,
    "resume_keyword": 10,
    "seniority": 10,
    "industry_fit": 5,
    "location_fit": 5,
    "startup_bonus": 5,
    "interview_potential": 5,
}

BANDS = [
    (90, "apply_immediately"),
    (80, "strong"),
    (70, "worth_considering"),
    (60, "stretch"),
    (0, "low_priority"),
]

SYSTEM_PROMPT = f"""You score how well a candidate's resume matches a job posting. \
Output ONLY a JSON object, no markdown, no commentary. Use exactly this shape:
{{
  "sub_scores": {{"required_skills": 0-100, "experience": 0-100, "project_relevance": 0-100, \
"resume_keyword": 0-100, "seniority": 0-100, "industry_fit": 0-100, "location_fit": 0-100, \
"startup_bonus": 0-100, "interview_potential": 0-100}},
  "matched_skills": [""],
  "missing_skills": [""],
  "rationale": "2-3 sentences: why this score, referencing specifics from the resume and job"
}}
Each sub_score is 0-100 (100 = perfect match on that factor alone). Judge only from the \
resume and job text given — do not assume skills or experience not stated in the resume."""


def band_for(score: int) -> str:
    for threshold, band in BANDS:
        if score >= threshold:
            return band
    return "low_priority"


def score_job(resume_structured: dict, job_title: str, job_description: str, company_context: str = "") -> dict:
    user_prompt = (
        f"RESUME (structured):\n{resume_structured}\n\n"
        f"JOB TITLE: {job_title}\n"
        f"COMPANY CONTEXT: {company_context}\n"
        f"JOB DESCRIPTION:\n{job_description[:6000]}"
    )
    result = complete_json(SYSTEM_PROMPT, user_prompt, max_tokens=1200)

    sub_scores = result["sub_scores"]
    overall = round(sum(sub_scores[factor] * weight for factor, weight in WEIGHTS.items()) / 100)
    overall = max(0, min(100, overall))

    return {
        "overall_score": overall,
        "sub_scores": sub_scores,
        "band": band_for(overall),
        "matched_skills": result.get("matched_skills", []),
        "missing_skills": result.get("missing_skills", []),
        "rationale": result.get("rationale", ""),
    }


# --- Free (no-API-call) scorer -------------------------------------------
# Keyword/skill-overlap matching: zero cost, but cruder than score_job()
# above — no semantic reasoning, no rationale, and "missing_skills" is only
# as good as this vocabulary. Good enough to rank a daily flood of postings
# without spending anything; use score_job() for a genuine second opinion
# on your top candidates.

FREE_SKILL_VOCAB = [
    # Languages
    "Python", "Java", "C++", "C#", "JavaScript", "TypeScript", "Go", "Rust", "Scala", "Kotlin",
    "Swift", "Ruby", "PHP", "SQL", "Verilog", "VHDL", "SystemVerilog", "MATLAB", "Bash",
    # Web / backend
    "React", "Angular", "Vue", "Node.js", "Django", "Flask", "FastAPI", "Spring", "GraphQL",
    "REST", "gRPC", "Microservices",
    # Data / ML
    "TensorFlow", "PyTorch", "scikit-learn", "Pandas", "NumPy", "Spark", "Hadoop", "Kafka",
    "Airflow", "NoSQL", "MongoDB", "PostgreSQL", "MySQL", "Redis", "Elasticsearch",
    # Cloud / infra
    "AWS", "Azure", "GCP", "Kubernetes", "Docker", "Terraform", "Jenkins", "CI/CD", "Linux", "Git",
    # Hardware / EE
    "RISC-V", "ARM", "ASIC", "FPGA", "RTL", "UVM", "DFT", "Synthesis", "Place and Route",
    "Timing Closure", "PCIe", "DDR", "SoC", "Embedded Systems", "Firmware",
    # General / process
    "Agile", "Scrum", "Project Management", "Leadership",
]

_TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(text: str) -> str:
    return _TAG_RE.sub(" ", html.unescape(text or ""))


def strip_html(text: str) -> str:
    """Public wrapper for _clean_text — used by the UI to render a raw
    posting description (some ATS sources, e.g. Greenhouse, store it as
    HTML-escaped markup) without pulling in a full HTML-to-text library."""
    return _clean_text(text)


def _contains_term(term: str, haystack: str) -> bool:
    pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
    return re.search(pattern, haystack, re.IGNORECASE) is not None


def _resume_text(resume_structured: dict) -> str:
    parts = [
        resume_structured.get("summary", "") or "",
        " ".join(resume_structured.get("skills", []) or []),
    ]
    for exp in resume_structured.get("experience", []) or []:
        parts.extend(exp.get("bullets", []) or [])
    for project in resume_structured.get("projects", []) or []:
        parts.append(project.get("name", "") or "")
        parts.extend(project.get("tags", []) or [])
        parts.extend(project.get("bullets", []) or [])
    return " ".join(parts)


MIN_REQUIRED_KEYWORDS = 3  # below this, len(matched)/len(job_required) is noise, not a score


def score_job_free(resume_structured: dict, job_title: str, job_description: str, company_context: str = "") -> dict:
    """Zero-cost alternative to score_job() — no Claude call. Scores how many
    recognized skill keywords in the job posting also show up somewhere in
    the resume.

    company_context is accepted for interface parity with score_job() but
    deliberately NOT included in the text scanned for required keywords:
    it's the company's one-line description, not this job's requirements,
    and blending it in caused a real bug — a company description reading
    "transformers on ASIC" made every job at that company (including a
    Mechanical Engineer posting) inherit "ASIC" as a "required" skill,
    scoring 100% off a single spurious match. Found by a user reporting a
    100/100 "Apply Today" score on a job with almost nothing in common
    with their resume.

    That also exposed a second issue: with very few recognized keywords,
    matched/required is a tiny-sample ratio that saturates to 0 or 100 on
    one lucky or unlucky hit (55% of a 1000-posting sample had 0-2
    recognized keywords). Below MIN_REQUIRED_KEYWORDS, this returns a
    neutral 50 instead of a falsely confident extreme."""
    job_text = _clean_text(f"{job_title} {job_description}")
    resume_text = _resume_text(resume_structured)

    job_required = [kw for kw in FREE_SKILL_VOCAB if _contains_term(kw, job_text)]
    matched = [kw for kw in job_required if _contains_term(kw, resume_text)]
    missing = [kw for kw in job_required if kw not in matched]

    if len(job_required) >= MIN_REQUIRED_KEYWORDS:
        overall = round(100 * len(matched) / len(job_required))
        rationale = (
            f"Free keyword match: {len(matched)}/{len(job_required)} recognized skill "
            f"keywords in this posting also appear in your resume."
        )
    elif job_required:
        overall = 50
        rationale = (
            f"Only {len(job_required)} recognized skill keyword(s) found in this posting "
            f"— too few for a reliable score, defaulting to neutral."
        )
    else:
        overall = 50
        rationale = "No recognized skill keywords found in this posting — score defaults to neutral."

    overall = max(0, min(100, overall))
    return {
        "overall_score": overall,
        "sub_scores": {"keyword_overlap": overall},
        "band": band_for(overall),
        "matched_skills": matched,
        "missing_skills": missing,
        "rationale": rationale,
    }


# --- Work authorization screening (free, regex-based) ---------------------
# Deliberately kept separate from the match score, not folded into it: a
# 94%-technical-match job with a citizenship requirement isn't a 94% job for
# someone who needs sponsorship, it's a job they may not be able to take at
# all. These are text-pattern hits against the posting only — a screening
# signal to read and verify, not a legal determination. Absence of a hit
# means "not mentioned in this posting," never "confirmed fine."

CITIZENSHIP_PATTERNS = [
    r"must be a u\.?s\.?\s*citizen",
    r"u\.?s\.?\s*citizenship required",
    r"u\.?s\.?\s*citizens? only",
    r"citizens? of the united states",
    r"permanent resident(?:s)? (?:or u\.?s\.?\s*citizen|required)",
    r"green card holder",
    r"\bu\.?s\.?\s*person\b",
]

CLEARANCE_PATTERNS = [
    r"security clearance",
    r"secret clearance",
    r"top secret",
    r"active clearance",
    r"ability to obtain (?:a |an )?(?:security )?clearance",
    r"\bitar\b",
    r"\bear\b",
    r"export control",
    r"special access program",
]

NO_SPONSORSHIP_PATTERNS = [
    # sponsor(?:ship)? (not just "sponsorship") to also catch "unable to
    # sponsor or take over sponsorship of employment visas" — real phrasing
    # seen in live postings, where "sponsor" (no suffix) is the first hit.
    r"\b(?:no|not able to|unable to|cannot|will not|does not) (?:provide |offer |take over )?(?:visa )?sponsor(?:ship)?\b",
    r"\bsponsorship (?:is )?not available\b",
    r"\bwithout (?:the need for )?(?:visa )?sponsorship\b",
    r"\bdoes not sponsor\b",
]

SPONSORSHIP_POSITIVE_PATTERNS = [
    # \b before the alternation is load-bearing: without it, "unable to
    # sponsor" matches as a bare substring on "able to sponsor" inside
    # "un[able to sponsor]" — exactly backwards (a no-sponsorship posting
    # reads as sponsorship-available). Caught by testing against real
    # postings, not by inspection.
    r"\b(?:will|able to|can) sponsor\b",
    r"\bvisa sponsorship (?:available|provided|offered)\b",
    r"\bh-?1b sponsorship\b",
    r"\bsponsorship (?:is )?available\b",
]


def _pattern_hits(patterns: list[str], text: str) -> list[str]:
    hits = []
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            hits.append(match.group(0))
    return hits


def detect_work_auth_flags(job_title: str, job_description: str) -> dict:
    """Screening signal only, from posting text — not a legal determination.
    Zero cost, no API calls."""
    text = _clean_text(f"{job_title} {job_description}")
    citizenship_hits = _pattern_hits(CITIZENSHIP_PATTERNS, text)
    clearance_hits = _pattern_hits(CLEARANCE_PATTERNS, text)
    no_sponsorship_hits = _pattern_hits(NO_SPONSORSHIP_PATTERNS, text)
    sponsorship_hits = _pattern_hits(SPONSORSHIP_POSITIVE_PATTERNS, text)
    return {
        "citizenship_required": bool(citizenship_hits),
        "clearance_required": bool(clearance_hits),
        "no_sponsorship": bool(no_sponsorship_hits),
        "sponsorship_mentioned": bool(sponsorship_hits),
        "matched_phrases": citizenship_hits + clearance_hits + no_sponsorship_hits + sponsorship_hits,
    }
