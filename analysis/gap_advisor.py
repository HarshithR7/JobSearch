"""Ties the skill gaps aggregated across a profile's job_match rows to
concrete project ideas on their existing public GitHub repos — 'add X to
repo Y' rather than 'learn Kubernetes' in the abstract."""

from collections import Counter

from analysis.ai_client import complete_json
from collectors.http_utils import get_json

SYSTEM_PROMPT = """You recommend concrete additions to a candidate's EXISTING GitHub repos \
that would close their most common job-skill gaps — not brand new project ideas, unless none \
of their current repos are a reasonable fit for a gap. Output ONLY a JSON object, no markdown:
{
  "recommendations": [
    {
      "repo": "existing repo name, or 'NEW' if nothing existing fits",
      "addition": "concrete, specific thing to build/add",
      "skills_closed": ["skill1", "skill2"],
      "why": "1 sentence: how many/which target jobs this helps with"
    }
  ]
}
Give 3-5 recommendations, prioritized by how many skill gaps (by frequency given) each closes. \
Be concrete and technical, not generic ("add tests" is too vague; "add a RVV vector-extension \
compliance test suite using riscv-tests" is the right level of specificity)."""


def fetch_public_repos(github_username: str) -> list[dict]:
    data = get_json(f"https://api.github.com/users/{github_username}/repos?per_page=100&sort=updated")
    if not isinstance(data, list):
        return []
    return [
        {"name": r["name"], "description": r.get("description"), "language": r.get("language"), "topics": r.get("topics", [])}
        for r in data
        if not r.get("fork")
    ]


def recommend_projects(github_username: str, missing_skills: list[str]) -> dict:
    """missing_skills should be the flattened list of missing_skills across
    all of a profile's job_match rows — frequency signals which gaps recur
    across the most target jobs, which is what makes a recommendation
    worth prioritizing."""
    repos = fetch_public_repos(github_username)
    gap_counts = Counter(s.lower() for s in missing_skills)
    ranked_gaps = gap_counts.most_common(15)

    user_prompt = (
        f"EXISTING PUBLIC REPOS:\n{repos}\n\n"
        f"MISSING SKILLS ACROSS TARGET JOBS (skill: number of jobs requiring it):\n{ranked_gaps}"
    )
    return complete_json(SYSTEM_PROMPT, user_prompt, max_tokens=2500)
