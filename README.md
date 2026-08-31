# Job Search Portal

A personal job-intelligence + application-preparation platform for Harshith (and a friend), modeled on the [Investment-Tracker](https://github.com/HarshithR7/Investment-Tracker) stack: Streamlit + SQLAlchemy + Neon Postgres + Alembic + GitHub Actions cron.

See `plan.md`-equivalent context in the repo history / conversation this was built from for the full design rationale (data-source legality choices, scoring rubric, guardrails).

## Stack
- Python 3.12+ (works on native Windows or WSL/Ubuntu — no OS-specific code)
- SQLAlchemy ORM + PostgreSQL (Neon)
- Alembic migrations
- Streamlit UI
- Anthropic Claude for resume tailoring, job matching, and interview-prep generation

## Folder guide
- `app/` — Streamlit shell (`app.py`) + pages (Job Feed, Companies, Applications, Resume Studio, Prep Center, Profiles)
- `config/` — pydantic-settings config + logging
- `database/` — engine/session/models/repositories
- `migrations/` — Alembic
- `collectors/` — Greenhouse/Lever/Ashby/SmartRecruiters public ATS APIs, a generic careers-page fallback, RemoteOK/HN discovery, H-1B LCA cross-reference, LinkedIn email-alert parser
- `analysis/` — resume parsing, job matching/scoring, resume tailoring, interview-prep generation, GitHub-tied project recommendations
- `scripts/` — one-time company seeding, bootstrap smoke-check, the daily job-scan pipeline
- `main.py` — CLI orchestrator

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                # then fill in DATABASE_URL and ANTHROPIC_API_KEY
python -m alembic upgrade head
python -m scripts.seed_companies    # one-time import of the startups spreadsheet
```

## Running

```bash
# Daily pipeline (also runs automatically via .github/workflows/daily-job-scan.yml)
python main.py scan-jobs

# Score live postings against a profile's resume (omit --profile for all profiles)
python main.py match-jobs --profile Harshith

# Tailor a resume for a specific job (job-id from the job_posting table / Resume Studio page)
python main.py tailor-resume --profile Harshith --job-id 123

# Generate interview-prep content for a role archetype
python main.py generate-prep --role "RISC-V Verification Engineer" --tech-tag "RISC-V"

# UI
streamlit run app/app.py
```

## Notes
- Data sources deliberately avoid scraping LinkedIn/Indeed directly (ToS + bot-detection risk). See `collectors/linkedin_email_parser.py` for the email-alert-based alternative, and `collectors/careers_generic.py` for the best-effort company-careers-page fallback.
- AI-generated resumes are constrained to a profile's structured master resume (`Profile.resume_structured`) — they reorder/reword, never invent employers, skills, or metrics. Every tailored version is stored, never overwritten (`resume_version` table).
- `requirements-cloud.txt` is the slim dependency set for Streamlit Community Cloud / CI (drops `openpyxl`, `pytest`).
