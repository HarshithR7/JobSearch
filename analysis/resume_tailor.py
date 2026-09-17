"""Generates a tailored resume for one job, constrained to the profile's
structured master resume. Guardrail: the model may only reorder, reword,
and re-emphasize what's already in resume_structured — never invent
employers, skills, technologies, or metrics not present there."""

import io

import docx

from analysis.ai_client import complete_json

SYSTEM_PROMPT = """You tailor a resume for a specific job posting. You may ONLY reorder, \
reword, and re-emphasize content that already exists in the candidate's structured resume \
JSON given below — you must NEVER invent an employer, title, skill, technology, project, \
or metric that isn't already present there. If the job wants something the candidate's \
resume doesn't show, leave it out rather than fabricating it.

Output ONLY a JSON object, no markdown, no commentary. Use exactly this shape:
{
  "summary": "2-3 sentence summary emphasizing the truthful overlap with this job",
  "experience": [{"company": "", "title": "", "dates": "", "bullets": [""]}],
  "projects": [{"name": "", "bullets": [""]}],
  "skills": [""]
}
Reorder skills/bullets to foreground what's relevant to this job; you may rephrase a bullet \
for clarity/emphasis but every fact in it must already be true per the source resume."""


def generate_tailored_content(resume_structured: dict, job_title: str, job_description: str) -> dict:
    user_prompt = (
        f"CANDIDATE'S STRUCTURED RESUME (source of truth — do not go beyond this):\n{resume_structured}\n\n"
        f"JOB TITLE: {job_title}\n"
        f"JOB DESCRIPTION:\n{job_description[:6000]}"
    )
    return complete_json(SYSTEM_PROMPT, user_prompt, max_tokens=4500)


def render_docx(tailored: dict, candidate_name: str, contact_line: str) -> bytes:
    document = docx.Document()
    document.add_heading(candidate_name, level=1)
    document.add_paragraph(contact_line)

    document.add_heading("Summary", level=2)
    document.add_paragraph(tailored.get("summary", ""))

    if tailored.get("experience"):
        document.add_heading("Experience", level=2)
        for job in tailored["experience"]:
            document.add_paragraph(f"{job.get('title', '')} — {job.get('company', '')} ({job.get('dates', '')})", style="Heading 3")
            for bullet in job.get("bullets", []):
                document.add_paragraph(bullet, style="List Bullet")

    if tailored.get("projects"):
        document.add_heading("Projects", level=2)
        for project in tailored["projects"]:
            document.add_paragraph(project.get("name", ""), style="Heading 3")
            for bullet in project.get("bullets", []):
                document.add_paragraph(bullet, style="List Bullet")

    if tailored.get("skills"):
        document.add_heading("Skills", level=2)
        document.add_paragraph(", ".join(tailored["skills"]))

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def render_docx_from_text(generated_text: str, candidate_name: str, contact_line: str) -> bytes:
    """Fallback for resume_version rows saved before the structured
    tailored dict was persisted (only flat generated_text survives) — same
    idea as render_docx() but working from to_plain_text()'s own output
    format, so it round-trips without fabricating structure that isn't
    there. Bullet lines ("- ...") become List Bullet paragraphs, blank
    lines become spacing, everything else is a plain paragraph — no
    Summary/Experience/Projects headers, since flat text doesn't mark
    section boundaries."""
    document = docx.Document()
    document.add_heading(candidate_name, level=1)
    document.add_paragraph(contact_line)
    document.add_paragraph("")

    for line in generated_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            document.add_paragraph(stripped[2:], style="List Bullet")
        else:
            document.add_paragraph(stripped)

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def to_plain_text(tailored: dict) -> str:
    lines = [tailored.get("summary", ""), ""]
    for job in tailored.get("experience", []):
        lines.append(f"{job.get('title', '')} — {job.get('company', '')} ({job.get('dates', '')})")
        lines.extend(f"- {b}" for b in job.get("bullets", []))
        lines.append("")
    for project in tailored.get("projects", []):
        lines.append(project.get("name", ""))
        lines.extend(f"- {b}" for b in project.get("bullets", []))
        lines.append("")
    if tailored.get("skills"):
        lines.append("Skills: " + ", ".join(tailored["skills"]))
    return "\n".join(lines)
