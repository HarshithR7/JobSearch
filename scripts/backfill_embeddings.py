"""One-time (then incremental) job to compute embeddings for every live
posting that doesn't have one yet. Safe to re-run: only touches postings
with embedding IS NULL, so a scheduled re-run after scan-jobs only
embeds newly-discovered postings, not the whole table again.

    python -m scripts.backfill_embeddings
"""

from config import logger
from database.session import get_session
from database.models import JobPosting
from analysis.embeddings import embed_texts, job_text_for_embedding

BATCH_SIZE = 100


def run() -> int:
    with get_session() as db:
        posting_ids = [
            p.id for p in db.query(JobPosting.id)
            .filter(JobPosting.status == "live", JobPosting.embedding.is_(None))
            .all()
        ]

    if not posting_ids:
        logger.info("backfill_embeddings: nothing to do, every live posting already has an embedding")
        return 0

    logger.info(f"backfill_embeddings: {len(posting_ids)} postings need embeddings")
    total = 0
    for i in range(0, len(posting_ids), BATCH_SIZE):
        batch_ids = posting_ids[i : i + BATCH_SIZE]
        with get_session() as db:
            postings = db.query(JobPosting).filter(JobPosting.id.in_(batch_ids)).all()
            texts = [job_text_for_embedding(p.title, p.raw_description or "") for p in postings]
            vectors = embed_texts(texts)
            for posting, vector in zip(postings, vectors):
                posting.embedding = vector
        total += len(postings)
        logger.info(f"backfill_embeddings: {total}/{len(posting_ids)} embedded")

    return total


if __name__ == "__main__":
    run()
