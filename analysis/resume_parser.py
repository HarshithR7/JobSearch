"""Parses a base resume (docx/pdf/pasted text) into the structured JSON
that is the single source of truth for job_matcher.py and resume_tailor.py.
Never invents content: this only reorganizes what's already on the page."""

import io

import docx

from analysis.ai_client import complete_json

SYSTEM_PROMPT = """You extract structured data from a resume. Output ONLY a JSON object, \
no markdown, no commentary. Use exactly this shape:
{
  "summary": "string",
  "education": [{"school": "", "degree": "", "graduation": ""}],
  "experience": [{"company": "", "title": "", "dates": "", "bullets": [""]}],
  "projects": [{"name": "", "tags": [""], "bullets": [""]}],
  "skills": [""],
  "links": {"github": "", "linkedin": ""}
}
Copy text verbatim where possible — do not paraphrase, summarize, or invent \
anything not present in the source resume."""


def extract_text_from_docx(file_bytes: bytes) -> str:
    document = docx.Document(io.BytesIO(file_bytes))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def parse_resume_text(raw_text: str) -> dict:
    """Calls Claude once to reshape plain resume text into the structured
    schema above. Raises analysis.ai_client.AIUnavailableError if no API
    key is configured."""
    # 3000, then 4500, both truncated mid-string on this resume (a long,
    # project-heavy one) — wasted two real API calls to JSONDecodeError
    # before this. Going generous rather than incrementing by 1500 a third
    # time.
    return complete_json(SYSTEM_PROMPT, raw_text, max_tokens=8000)
