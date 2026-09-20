"""Scores one job posting against one profile's structured resume.

Claude produces sub-scores for each weighted factor plus matched/missing
skills and a short rationale; the weighted rollup itself is plain
arithmetic here, not left to the model, so scores stay comparable across
jobs and profiles (see plan: "Job Match Score" rubric)."""

import html
import re
from datetime import datetime

from analysis.ai_client import complete_json
from config import settings

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
    # ANTHROPIC_MODEL_FAST (Haiku by default): this is a high-volume, bounded
    # -output classification call against a fixed JSON schema, not open-ended
    # writing — doesn't need Sonnet-level reasoning. Sonnet stays the default
    # for resume parsing/tailoring/prep generation (low-volume, higher-stakes).
    # max_tokens bumped from 1200: a truncated response used to crash the
    # whole batch (json.JSONDecodeError, uncaught) — see main.py's per-posting
    # try/except for the other half of that fix.
    result = complete_json(SYSTEM_PROMPT, user_prompt, max_tokens=1500, model=settings.ANTHROPIC_MODEL_FAST)

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
    "Swift", "Ruby", "PHP", "SQL", "Verilog", "VHDL", "SystemVerilog", "MATLAB", "Bash", "Perl",
    "Julia", "Assembly", "TCL", "Groovy", "Objective-C", "Solidity", "Simulink",
    # Web / backend
    "React", "Angular", "Vue", "Node.js", "Django", "Flask", "FastAPI", "Spring", "GraphQL",
    "REST", "gRPC", "Microservices", "Express", "Next.js", "Ruby on Rails", "ASP.NET", ".NET",
    # Data / ML
    "TensorFlow", "PyTorch", "scikit-learn", "Pandas", "NumPy", "Spark", "Hadoop", "Kafka",
    "Airflow", "NoSQL", "MongoDB", "PostgreSQL", "MySQL", "Redis", "Elasticsearch", "Keras",
    "JAX", "Hugging Face", "LangChain", "XGBoost", "OpenCV", "NLTK", "spaCy", "Databricks",
    "Snowflake", "dbt", "Tableau", "Power BI", "Looker", "Machine Learning", "Deep Learning",
    "Computer Vision", "NLP", "LLM", "Reinforcement Learning",
    # Cloud / infra
    "AWS", "Azure", "GCP", "Kubernetes", "Docker", "Terraform", "Jenkins", "CI/CD", "Linux", "Git",
    "Ansible", "Puppet", "Chef", "Helm", "Istio", "Prometheus", "Grafana", "Nginx", "CloudFormation",
    "Serverless", "Lambda", "SRE", "DevOps",
    # Hardware / EE — chip design, verification, physical design
    "RISC-V", "ARM", "ASIC", "FPGA", "RTL", "UVM", "DFT", "Synthesis", "Place and Route",
    "Timing Closure", "PCIe", "DDR", "LPDDR", "HBM", "SoC", "Embedded Systems", "Firmware",
    "Cadence", "Synopsys", "Mentor Graphics", "Xilinx", "Vivado", "Quartus", "ModelSim", "VCS",
    "Questa", "SPICE", "HSPICE", "Virtuoso", "Innovus", "Genus", "ICC2", "PrimeTime",
    "Static Timing Analysis", "STA", "DRC", "LVS", "Tapeout", "GDSII", "Floorplanning",
    "Clock Tree Synthesis", "JTAG", "Scan Chain", "ATPG", "BIST", "Formal Verification",
    "SVA", "Constrained Random", "Coverage-Driven Verification", "AXI", "AHB", "APB", "I2C",
    "SPI", "UART", "Ethernet", "USB", "HDMI", "MIPI", "NoC", "Microarchitecture", "Pipeline",
    "Out-of-Order", "Superscalar", "Branch Prediction", "Cache Coherence", "MESI",
    "Memory Controller", "DMA", "Power Management", "Low Power Design", "UPF", "Clock Gating",
    "Signal Integrity", "Analog Design", "Mixed Signal", "PLL", "ADC", "DAC", "RF Design",
    "Photonics", "Quantum Computing", "CMOS", "FinFET", "GaN", "SiC", "Yield Analysis", "Wafer",
    "Foundry", "Process Node", "Lithography",
    # Testing / QA
    "Selenium", "Cypress", "Jest", "PyTest", "JUnit", "TestNG", "Postman", "Load Testing",
    # Databases
    "Oracle", "Cassandra", "DynamoDB", "MariaDB",
    # General / process
    "Agile", "Scrum", "Kanban", "Waterfall", "Six Sigma", "Lean", "SAFe", "TDD", "Project Management",
    "Leadership", "Mentoring", "Stakeholder Management", "Technical Writing", "PMP",
    # Healthcare IT / clinical informatics — EHR platforms, interoperability
    # standards, implementation/testing lifecycle, compliance. Added after a
    # real gap: this vocabulary was 100% software/hardware-engineering terms,
    # so a clinical-informatics resume had ~0 keyword overlap with anything,
    # health-IT postings included — the free scorer couldn't tell it what
    # skills it even had.
    "EHR", "EMR", "Epic", "Cerner", "Oracle Health", "eClinicalWorks", "Netsmart",
    "MEDITECH", "Veradigm", "Allscripts", "NextGen", "Greenway", "athenahealth",
    "HL7", "FHIR", "Interoperability", "Clinical Informatics", "Health Informatics",
    "Clinical Workflow", "Workflow Optimization", "Go-Live", "UAT", "Upgrade Testing",
    "Clinical Documentation", "Population Health", "Care Coordination",
    "Revenue Cycle", "Claims Processing", "HIPAA", "ICD-10", "CPT", "HITRUST",
    "Epic Certification", "KPI Reporting", "Data Mapping",
    "Requirements Gathering", "Process Mapping", "Change Management",
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


MIN_REQUIRED_KEYWORDS = 5  # below this, len(matched)/len(job_required) is noise, not a score


def _confidence_cap(n_required: int) -> int:
    """A perfect ratio (matched == required) isn't fully trustworthy on a
    thin keyword sample — 5/5 matched still only means 5 recognized terms
    out of everything a real posting actually asks for. Caps the reachable
    score by how much evidence backs it, so a 100 requires real breadth of
    matched vocabulary, not a lucky small sample. User: "fix the free
    score run, more rigid for scoring.\""""
    if n_required < 7:
        return 80
    if n_required < 10:
        return 90
    return 100

_EXPERIENCE_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_PRESENT_RE = re.compile(r"\bpresent\b|\bcurrent\b|\bnow\b", re.IGNORECASE)

# A "10+ years experience" requirement means professional experience, not
# internship/TA time — counting those equally would misrepresent an early-
# career candidate as more senior than they are (caught via a real report:
# "because i have internship, teaching assistant" experience, not the years
# a naive full-resume span would suggest).
_NON_PROFESSIONAL_TITLE_MARKERS = ("intern", "teaching assistant", "student assistant", "research assistant")


def estimate_years_experience(resume_structured: dict) -> int | None:
    """Sums each qualifying entry's own (end - start) duration — not an
    overall min-to-max span across all entries, which would count a gap
    between jobs (e.g. internship ends 2022, next role starts 2025) as
    3 years of experience that was never actually worked. Excludes
    internship/TA/research-assistant titles. Still a rough parse of
    free-text resume dates, not exact — feeds a bounded penalty, never a
    hard cutoff."""
    total_years = 0
    counted_any = False
    for exp in resume_structured.get("experience", []) or []:
        title_lower = (exp.get("title", "") or "").lower()
        if any(marker in title_lower for marker in _NON_PROFESSIONAL_TITLE_MARKERS):
            continue
        dates_text = exp.get("dates", "") or ""
        years_found = [int(y) for y in _EXPERIENCE_YEAR_RE.findall(dates_text)]
        if _PRESENT_RE.search(dates_text):
            years_found.append(datetime.now().year)
        if len(years_found) >= 2:
            total_years += max(0, max(years_found) - min(years_found))
            counted_any = True
    return total_years if counted_any else None


# Real cosine-similarity distribution for this resume against a random
# 100-posting sample: min 0.48, p50 0.70, max 0.78 — bge-small embeddings
# for "related professional text" cluster in a tight band, not the full
# -1..1 range, so raw cosine similarity isn't directly a 0-100 score.
# Rescaled against that observed range instead of guessed thresholds.
SEMANTIC_SIM_FLOOR = 0.45
SEMANTIC_SIM_CEILING = 0.80


def _semantic_score(similarity: float) -> int:
    scaled = (similarity - SEMANTIC_SIM_FLOOR) / (SEMANTIC_SIM_CEILING - SEMANTIC_SIM_FLOOR) * 100
    return max(0, min(100, round(scaled)))


def score_job_free(
    resume_structured: dict, job_title: str, job_description: str, company_context: str = "",
    resume_embedding: list[float] | None = None, job_embedding: list[float] | None = None,
) -> dict:
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
        ratio_score = round(100 * len(matched) / len(job_required))
        cap = _confidence_cap(len(job_required))
        overall = min(ratio_score, cap)
        rationale = (
            f"Free keyword match: {len(matched)}/{len(job_required)} recognized skill "
            f"keywords in this posting also appear in your resume."
        )
        if ratio_score > cap:
            rationale += f" Capped at {cap}% — only {len(job_required)} recognized keywords is thin evidence for a higher score."
    elif job_required:
        overall = 50
        rationale = (
            f"Only {len(job_required)} recognized skill keyword(s) found in this posting "
            f"— too few for a reliable score, defaulting to neutral."
        )
    else:
        overall = 50
        rationale = "No recognized skill keywords found in this posting — score defaults to neutral."

    # Experience-gap penalty: keyword overlap alone doesn't catch "10+ years
    # of semiconductor experience" on a posting that also happens to share
    # 5/6 recognized skill keywords with the resume (real case: scored 83%
    # with zero awareness of the years requirement). -8 points per year
    # short, capped at -50 — bounded because estimate_years_experience() is
    # a rough parse of free-text resume dates, not exact; this discounts a
    # likely-severe mismatch, it doesn't zero the job out on an estimate
    # that could be off by a year or two.
    #
    # Only applied when len(job_required) >= MIN_REQUIRED_KEYWORDS, i.e. we
    # already have a real ratio-based score — applying it to the "too few
    # keywords" neutral-50 fallback compounds two different uncertainties
    # into false confidence (caught in testing: Etched's Mechanical Engineer
    # posting, 1 recognized keyword, went from an honest "not enough
    # signal" 50 to a falsely confident 0 once the penalty stacked on top).
    keyword_score = overall
    experience_penalty = 0
    if len(job_required) >= MIN_REQUIRED_KEYWORDS:
        experience = detect_experience_signal(job_title, job_description)
        candidate_years = estimate_years_experience(resume_structured)
        required_years = experience.get("min_years_required")
        if required_years and candidate_years is not None and candidate_years < required_years:
            gap = required_years - candidate_years
            experience_penalty = min(50, gap * 8)
            overall -= experience_penalty
            rationale += (
                f" Adjusted -{experience_penalty} for an estimated experience gap "
                f"(~{candidate_years}y in your resume vs {required_years}+y required)."
            )

    overall = max(0, min(100, overall))

    # Semantic-similarity blend: catches conceptual matches the fixed
    # vocabulary can't ("Tomasulo algorithm with reorder buffer" <->
    # "out-of-order execution" — 0.74 cosine similarity, zero shared
    # keywords). Weighted more heavily when the keyword signal was weak
    # (nothing real to defer to) and more lightly when it was solid
    # (keyword+experience-penalty backbone stays dominant, semantic is an
    # adjustment, not a replacement).
    semantic_score = None
    if resume_embedding is not None and job_embedding is not None:
        from analysis.embeddings import cosine_similarity
        similarity = cosine_similarity(resume_embedding, job_embedding)
        semantic_score = _semantic_score(similarity)
        if len(job_required) < MIN_REQUIRED_KEYWORDS:
            overall = round(0.3 * overall + 0.7 * semantic_score)
        else:
            overall = round(0.7 * overall + 0.3 * semantic_score)
        overall = max(0, min(100, overall))
        rationale += f" Semantic similarity: {semantic_score}/100."

    return {
        "overall_score": overall,
        "sub_scores": {
            "keyword_overlap": keyword_score, "experience_penalty": experience_penalty,
            "semantic_similarity": semantic_score,
        },
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


# --- Experience-level screening (free, regex-based) ------------------------
# score_job_free() only checked technical-keyword overlap — it had no concept
# of seniority or years-of-experience at all, so a posting requiring "8+
# years" for a "Sr. Staff" role could hit 100% on 3/3 keyword matches. Used
# for both a UI badge (detect_experience_signal alone) and a bounded penalty
# inside score_job_free (see estimate_years_experience + the penalty there).
#
# 0-3 filler words allowed between "of" and "experience" — "10+ years of
# semiconductor experience" was missed by an earlier version of this regex
# that only allowed a fixed relevant/professional/related qualifier; caught
# on a real posting (Tenstorrent TPM) where the years requirement went
# completely undetected as a result.
YEARS_REQUIRED_RE = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?years?\s+(?:of\s+)?(?:[a-zA-Z/-]+\s+){0,3}experience",
    re.IGNORECASE,
)

SENIOR_TITLE_MARKERS = ("sr.", "sr ", "senior", "staff", "principal", "director", "vp ", "head of", "chief", "lead ")


def detect_experience_signal(job_title: str, job_description: str) -> dict:
    text = _clean_text(f"{job_title} {job_description}")
    years_found = [int(m.group(1)) for m in YEARS_REQUIRED_RE.finditer(text)]
    title_lower = job_title.lower()
    return {
        "min_years_required": max(years_found) if years_found else None,
        "senior_title": any(marker in title_lower for marker in SENIOR_TITLE_MARKERS),
    }


# --- US-location screening (free, keyword-based) ---------------------------
# Collectors pull from global sources (RemoteOK, HN Hiring, some companies'
# own multi-country career pages) — for a profile that specifically needs a
# US employer (e.g. visa sponsorship), a "Remote - Europe" or "Bangalore"
# posting is noise, not a match, no matter how well the skills line up.
# location is free text with no structured country field, so this is a
# denylist of non-US signals rather than a US allowlist — a location with
# no markers defaults to "likely US, unconfirmed" rather than being
# excluded, since most of this dashboard's company base already skews US
# and an incomplete allowlist would false-exclude real US postings.

_NON_US_LOCATION_MARKERS = (
    "united kingdom", "london", "germany", "aachen", "berlin", "munich",
    "netherlands", "amsterdam", "france", "paris", "india", "bangalore",
    "bengaluru", "hyderabad", "pune", "mumbai", "delhi", "china", "beijing",
    "shanghai", "shenzhen", "taiwan", "taipei", "japan", "tokyo",
    "south korea", "seoul", "singapore", "malaysia", "bayan lepas", "canada",
    "toronto", "vancouver", "ontario", "australia", "sydney", "melbourne",
    "israel", "tel aviv", "ireland", "dublin", "switzerland", "zurich",
    "spain", "italy", "sweden", "poland", "mexico", "brazil",
    "remote - europe", "remote - apac", "remote - international", "remote - emea",
)
_UK_RE = re.compile(r"\buk\b", re.IGNORECASE)


def is_likely_us_posting(location: str | None) -> bool | None:
    """True = US signal found or no signal either way (default), False =
    a non-US signal was found, None = no location text at all to judge."""
    if not location:
        return None
    loc_lower = location.lower()
    if _UK_RE.search(loc_lower) or any(marker in loc_lower for marker in _NON_US_LOCATION_MARKERS):
        return False
    return True
