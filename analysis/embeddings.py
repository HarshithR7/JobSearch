"""Semantic-similarity signal, layered on top of (not replacing)
score_job_free's keyword matching — catches conceptual overlap the fixed
vocabulary can't, e.g. "Tomasulo algorithm with reorder buffer" and
"out-of-order execution" score 0.74 cosine similarity despite sharing
zero keywords.

fastembed (ONNX Runtime), not sentence-transformers (PyTorch): chosen
specifically to stay light enough for a Streamlit Community Cloud
deployment — no GPU, no multi-GB PyTorch wheel, ~20MB of dependencies,
model itself ~130MB, downloaded once and cached under ~/.cache/fastembed.
Free, fully local, no API calls."""

import re

MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384

_model = None


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=MODEL_NAME)
    return _model


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def embed_text(text: str) -> list[float]:
    """Single-string convenience wrapper — batch via embed_texts() when
    embedding many documents (model.embed() batches internally, avoid
    calling this in a per-row loop for anything but a one-off like a
    resume)."""
    return next(iter(_get_model().embed([_clean(text)])))


def embed_texts(texts: list[str]) -> list[list[float]]:
    return list(_get_model().embed([_clean(t) for t in texts]))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    import numpy as np
    a, b = np.asarray(a), np.asarray(b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0


def resume_text_for_embedding(resume_structured: dict) -> str:
    """Same fields analysis.job_matcher._resume_text() draws from, kept
    separate rather than imported: that function is tuned for exact
    keyword lookups (skills list weighted equally with prose), this one
    feeds a sentence embedding where natural prose carries more of the
    meaning — summary and bullets first, skills appended after."""
    parts = [resume_structured.get("summary", "") or ""]
    for exp in resume_structured.get("experience", []) or []:
        parts.extend(exp.get("bullets", []) or [])
    for project in resume_structured.get("projects", []) or []:
        parts.append(project.get("name", "") or "")
        parts.extend(project.get("bullets", []) or [])
    parts.append(" ".join(resume_structured.get("skills", []) or []))
    return " ".join(p for p in parts if p)


def job_text_for_embedding(title: str, description: str) -> str:
    return f"{title} {_clean(description)[:2000]}"
