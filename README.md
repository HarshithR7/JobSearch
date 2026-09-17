# Job Search Portal

A personal job-intelligence + application-preparation platform for Harshith (and a friend), modeled on the [Investment-Tracker](https://github.com/HarshithR7/Investment-Tracker) stack: Streamlit + SQLAlchemy + Neon Postgres + Alembic + GitHub Actions cron.

See `plan.md`-equivalent context in the repo history / conversation this was built from for the full design rationale (data-source legality choices, scoring rubric, guardrails).

## Stack
- Python 3.12+ (works on native Windows or WSL/Ubuntu — no OS-specific code)
- SQLAlchemy ORM + PostgreSQL (Neon)
- Alembic migrations
- Streamlit UI
- Anthropic Claude for resume tailoring, job matching, and interview-prep generation

## Run the dashboard

The `.venv` (Windows) and `.venv-wsl` (WSL/Ubuntu) virtualenvs are already set up in this repo with everything installed, and `.env` already has `DATABASE_URL` pointed at the live Neon DB. Pick whichever shell you're in:

**Important: use `python -m streamlit`, not the `streamlit`/`streamlit.exe` binary directly.** The app imports things like `from database.session import ...` and `from app_common import ...` assuming the project root is on `sys.path` — `python -m streamlit` guarantees that (it adds the current directory); invoking the `streamlit` executable/shim directly does not, and fails with `ModuleNotFoundError: No module named 'database'`.

**Windows PowerShell:**
```powershell
cd c:\Users\harsh\JobSearch
.\.venv\Scripts\python.exe -m streamlit run app\app.py
```

**WSL / Ubuntu:**
```bash
cd /mnt/c/Users/harsh/JobSearch
./.venv-wsl/bin/python -m streamlit run app/app.py
```

Either one prints a URL — open **http://localhost:8501** in your browser. First thing you'll see is the sidebar profile switcher (already has "Harshith") and links to Job Feed / Companies / Applications / Resume Studio / Prep Center / Profiles.

**To stop it:** `Ctrl+C` in the terminal it's running in. If you closed that terminal instead and port 8501 is still stuck:
```powershell
# PowerShell — find and stop whatever's holding the port
Get-NetTCPConnection -LocalPort 8501 -State Listen | Select-Object OwningProcess
Stop-Process -Id <OwningProcess> -Force
```
```bash
# WSL/Linux
lsof -ti:8501 | xargs -r kill
```

**Restart after a code change:** Streamlit auto-reloads `app/app.py` and `app/pages/*.py` on save, but not shared modules like `app_common.py` or anything under `database/`/`analysis/`/`collectors/` in an already-running process — stop it (`Ctrl+C`) and re-run the command above if something looks stale or you hit an `ImportError`.

**Nothing showing up on Job Feed?** That page needs a *parsed* resume — go to **Profiles**, and once `ANTHROPIC_API_KEY` has billing credits, paste/upload a resume there (it auto-parses on save). Companies/Applications/Profiles all work today without any AI key.

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

# Score live postings against a profile's resume (omit --profile for all profiles).
# Default engine is "free" — keyword/skill-overlap matching, zero API calls, zero cost,
# scores every live posting. Safe to run daily/in cron.
python main.py match-jobs --profile Harshith

# Higher-quality Claude-scored pass (real per-posting cost — see "Known account-level
# blockers" below for the math; capped at the 500 most-recent live postings). Use this
# selectively on your current shortlist, not as the daily default.
python main.py match-jobs --profile Harshith --engine ai

# Tailor a resume for a specific job (job-id from the job_posting table / Resume Studio page)
python main.py tailor-resume --profile Harshith --job-id 123

# Generate interview-prep content for a role archetype
python main.py generate-prep --role "RISC-V Verification Engineer" --tech-tag "RISC-V"

# UI — see "Run the dashboard" above for why this must be `python -m streamlit`, not the bare `streamlit` command
python -m streamlit run app/app.py
```

## Notes
- Data sources deliberately avoid scraping LinkedIn/Indeed directly (ToS + bot-detection risk). See `collectors/linkedin_email_parser.py` for the email-alert-based alternative, and `collectors/careers_generic.py` for the best-effort company-careers-page fallback.
- AI-generated resumes are constrained to a profile's structured master resume (`Profile.resume_structured`) — they reorder/reword, never invent employers, skills, or metrics. Every tailored version is stored, never overwritten (`resume_version` table).
- `requirements-cloud.txt` is the slim dependency set for Streamlit Community Cloud / CI (drops `openpyxl`, `pytest`).

## Match-jobs cost (why the default engine is "free")
`analysis/job_matcher.score_job()` (Claude-scored) costs real money: roughly 2,450 input +
400 output tokens per posting ≈ **$0.013/posting** at Sonnet-tier pricing. Scoring 500
postings × 2 profiles = 1,000 calls ≈ **$13/run** — and `daily-job-scan.yml` runs *daily*,
not weekly, so left on `--engine ai` that's ~$390/month. `analysis/job_matcher.score_job_free()`
(the default) does keyword/skill-overlap matching against `Profile.resume_structured` with
zero API calls — cruder (no semantic reasoning, no rationale, vocabulary-limited "missing
skills"), but free, and unbounded (scores every live posting, not just the 500 most recent).
Use `--engine ai` selectively on your current shortlist when you want a real second opinion.

## Known account-level blockers (not code issues)
- **Anthropic billing**: `ANTHROPIC_API_KEY` is configured but currently has no credits (confirmed via a live `400 — credit balance too low` response). This blocks resume parsing (Profiles page) — which every downstream feature depends on, including the free matcher (it needs `resume_structured` to exist) — plus `--engine ai` scoring, resume tailoring (Resume Studio), interview prep (Prep Center), and the Skills Gap recommendations (Job Feed). Needs credits added at [console.anthropic.com](https://console.anthropic.com) — note this is the **Developer Platform / API Console**, a separate billing pool from a claude.ai chat subscription (Pro/Team credits there do not apply here). The pages now fail gracefully (a warning, not a crash) when this happens instead of losing unsaved data.
- **GitHub Actions billing**: the repo is pushed to `HarshithR7/JobSearch` (private) with `DATABASE_URL`/`ANTHROPIC_API_KEY` set as Actions secrets, and `daily-job-scan.yml` is registered and does trigger on schedule — but a manual test run (`gh run 35137179261`) failed immediately with *"recent account payments have failed or your spending limit needs to be increased"*. Fix in GitHub → Settings → Billing & plans, then re-run the workflow (or wait for the next 1pm UTC schedule) to confirm. This only affects the automated cron; running the dashboard/CLI locally is unaffected.
