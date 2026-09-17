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


def score_job_free(resume_structured: dict, job_title: str, job_description: str, company_context: str = "") -> dict:
    """Zero-cost alternative to score_job() — no Claude call. Scores how many
    recognized skill keywords in the job posting also show up somewhere in
    the resume. Vocabulary-limited: a posting with no recognized keywords
    gets a neutral 50 rather than a real 0-100 judgment."""
    job_text = _clean_text(f"{job_title} {job_description} {company_context}")
    resume_text = _resume_text(resume_structured)

    job_required = [kw for kw in FREE_SKILL_VOCAB if _contains_term(kw, job_text)]
    matched = [kw for kw in job_required if _contains_term(kw, resume_text)]
    missing = [kw for kw in job_required if kw not in matched]

    if job_required:
        overall = round(100 * len(matched) / len(job_required))
        rationale = (
            f"Free keyword match: {len(matched)}/{len(job_required)} recognized skill "
            f"keywords in this posting also appear in your resume."
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
