"""Generates interview-prep material (books, topics, sample Q&A) once per
role archetype (e.g. 'RISC-V Verification Engineer'), cached via
database/repositories/prep_repo.py with a 30-day TTL — not regenerated per
job posting."""

from analysis.ai_client import complete_json

SYSTEM_PROMPT = """You are building interview-preparation material for a specific hardware/ \
software engineering role archetype. Output ONLY a JSON object, no markdown, no commentary. \
Use exactly this shape:
{
  "books": ["Title — Author"],
  "topics": ["topic to study"],
  "courses": ["course or resource name"],
  "sample_qna": [{"q": "question", "a": "concise ideal-answer outline"}]
}
Give 4-6 items per list except sample_qna, which should have 8-12 questions spanning \
technical fundamentals, system/architecture-level questions, and role-specific practical \
questions for this exact role. Be specific to the role/technology named, not generic \
"tell me about yourself" filler."""


def generate_prep_content(role_name: str, tech_tag: str | None = None) -> dict:
    user_prompt = f"Role: {role_name}" + (f"\nPrimary technology: {tech_tag}" if tech_tag else "")
    return complete_json(SYSTEM_PROMPT, user_prompt, max_tokens=2500)
