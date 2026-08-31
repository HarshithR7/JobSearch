"""Scores one job posting against one profile's structured resume.

Claude produces sub-scores for each weighted factor plus matched/missing
skills and a short rationale; the weighted rollup itself is plain
arithmetic here, not left to the model, so scores stay comparable across
jobs and profiles (see plan: "Job Match Score" rubric)."""

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
