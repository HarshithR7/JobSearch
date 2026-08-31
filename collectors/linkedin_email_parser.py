"""Parses LinkedIn's own 'new jobs for you' alert emails, which Harshith
receives normally in his own inbox — this reads his own mailbox via IMAP,
it does not automate anything against LinkedIn's servers.

Setup (one-time, manual, documented in README):
1. In LinkedIn job-alert settings, keep email alerts on for target searches.
2. In Gmail, create a filter that applies a label (e.g. "LinkedIn-Alerts")
   to mail from *@linkedin.com, or set up a forwarding rule to a dedicated
   inbox.
3. Create a Gmail App Password and set IMAP_USER/IMAP_APP_PASSWORD/IMAP_LABEL
   in .env.

LinkedIn's alert-email HTML isn't a documented/stable format, so extraction
here is heuristic (regex + BeautifulSoup on job-view links) and best-effort
by design — a job that doesn't parse cleanly is still recorded with
whatever was recoverable and flagged in the Companies page for a human
glance, rather than silently dropped or guessed at.
"""

import email
import hashlib
import imaplib
import re
from email.message import Message

from bs4 import BeautifulSoup

from config import settings, logger
from database.session import get_session
from database.repositories import company_repo, job_repo
from database.models import LinkedInAlertEmail

JOB_LINK_RE = re.compile(r"linkedin\.com/comm/jobs/view/(\d+)|linkedin\.com/jobs/view/(\d+)")


def _connect() -> imaplib.IMAP4_SSL | None:
    if not (settings.IMAP_USER and settings.IMAP_APP_PASSWORD):
        logger.info("IMAP_USER/IMAP_APP_PASSWORD not set — skipping LinkedIn email parsing")
        return None
    conn = imaplib.IMAP4_SSL(settings.IMAP_HOST)
    conn.login(settings.IMAP_USER, settings.IMAP_APP_PASSWORD)
    return conn


def _extract_html(msg: Message) -> str | None:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore")
        return None
    if msg.get_content_type() == "text/html":
        return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore")
    return None


def _parse_jobs_from_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    seen_ids = set()

    for anchor in soup.find_all("a", href=True):
        match = JOB_LINK_RE.search(anchor["href"])
        if not match:
            continue
        job_id = match.group(1) or match.group(2)
        if job_id in seen_ids:
            continue
        seen_ids.add(job_id)

        title = anchor.get_text(strip=True)
        if not title:
            continue

        # Company/location conventionally follow in a nearby text block,
        # e.g. "Company Name · City, State". Best-effort only.
        company_name = "Unknown (from LinkedIn alert)"
        block = anchor.find_parent()
        if block:
            following_text = block.get_text(" ", strip=True)
            parts = following_text.split("·")  # LinkedIn uses a middle-dot separator
            if len(parts) >= 2:
                company_name = parts[1].strip()[:255] or company_name

        jobs.append(
            {
                "external_id": job_id,
                "title": title[:500],
                "url": f"https://www.linkedin.com/jobs/view/{job_id}",
                "company_name": company_name,
            }
        )
    return jobs


def fetch_and_ingest(profile_id: int) -> int:
    """Fetches unprocessed messages from IMAP_LABEL, parses job links, and
    records new JobPosting rows tagged source='linkedin_alert'. Returns the
    count of new postings created. Safe to run repeatedly (dedupes by
    message-id and by job external_id)."""
    conn = _connect()
    if conn is None:
        return 0

    new_postings = 0
    try:
        conn.select(f'"{settings.IMAP_LABEL}"')
        status, data = conn.search(None, "ALL")
        if status != "OK":
            return 0
        message_numbers = data[0].split()

        with get_session() as db:
            for num in message_numbers:
                status, msg_data = conn.fetch(num, "(RFC822)")
                if status != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw_msg = email.message_from_bytes(msg_data[0][1])
                message_id = raw_msg.get("Message-ID") or hashlib.sha256(msg_data[0][1]).hexdigest()

                already_seen = db.query(LinkedInAlertEmail).filter_by(message_id=message_id).first()
                if already_seen:
                    continue

                html = _extract_html(raw_msg)
                if html:
                    for job in _parse_jobs_from_html(html):
                        company = company_repo.upsert(db, name=job["company_name"], source="linkedin_alert", needs_review=True)
                        _, is_new = job_repo.upsert_posting(
                            db,
                            company_id=company.id,
                            external_id=job["external_id"],
                            source="linkedin_alert",
                            title=job["title"],
                            url=job["url"],
                        )
                        if is_new:
                            new_postings += 1

                db.add(LinkedInAlertEmail(profile_id=profile_id, message_id=message_id))
    finally:
        conn.logout()

    logger.info(f"LinkedIn email parser: {new_postings} new postings ingested")
    return new_postings
