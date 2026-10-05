"""The RAG service: the one place documents are indexed and searched.

    ingest_knowledge_base()   documents -> text -> chunks -> vectors -> store
    search_policies(question) question -> vector -> similarity -> top chunks

Everything that needs document retrieval calls `search_policies()`: the
`search_hr_policies` MCP tool today, and anything added later. There is
deliberately no second copy of this logic - a duplicate retrieval path is the
fastest way to end up with two systems that disagree about what the policy says.

**Text extraction is reused, not rewritten.** PDFs and DOCX files go through
`app/ai/cv_extraction.py`, the same module the CV feature uses; that is where
knowledge of file formats lives. This module only adds plain text and Markdown,
which need no library.

**Nothing here logs document contents.** Policy text is not as sensitive as a
CV, but the habit is worth keeping: the log lines carry counts, file names and
scores.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ai.cv_extraction import CvExtractionError, extract_cv_text
from app.rag.chunking import chunk_text
from app.rag.embeddings import EmbeddingError, get_embedding_backend
from app.rag.store import SearchHit, StoredChunk, VectorStore

logger = logging.getLogger("smarthr.rag")

#: Where source documents live. `demo/` is invented test material; `company/`
#: is the real thing. The folder is what marks a document, so a file cannot be
#: mislabelled by forgetting a header.
KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge"
DEMO_DIR = KNOWLEDGE_ROOT / "demo"
COMPANY_DIR = KNOWLEDGE_ROOT / "company"

SUPPORTED_SUFFIXES = {".md", ".txt", ".pdf", ".docx"}

#: How many chunks a search returns. Small on purpose: the point of retrieval
#: is to send a model the few passages that matter, not the whole document.
DEFAULT_TOP_K = 4

#: Below this similarity a chunk is treated as "not really about this".
#: Without it, an off-topic question still returns the least-irrelevant
#: paragraph, and a model handed a paragraph tends to answer from it - which is
#: exactly how a confident wrong answer about a policy gets produced.
#:
#: **The threshold is per backend, because the two score on different scales.**
#: Sparse lexical overlap gives low numbers where anything above noise is
#: meaningful; dense OpenAI embeddings put *everything* in the same broad band,
#: so an entirely unrelated question still scores ~0.4 and 0.12 would admit it.
#: Measured against this corpus:
#:
#:     backend        covered question    absent topic     threshold
#:     local-lexical  (tuned previously)                   0.12
#:     openai         0.539 - 0.757       0.242 - 0.464    0.50
#:
#: The openai figure sits in the gap between the lowest covered question
#: ("what happens if I am late?", 0.539) and the highest absent one ("company
#: car allowance", 0.464). **Re-measure this if the documents change** - it is
#: calibrated against the corpus, not a universal constant.
MIN_SCORE_BY_BACKEND = {
    "local-lexical": 0.12,
    "openai": 0.50,
}

#: The lexical value, kept as the name other modules import and as the fallback
#: for an unrecognised backend.
DEFAULT_MIN_SCORE = 0.12


def min_score_for(backend_name: str | None) -> float:
    """The relevance floor for the backend that built the current index."""
    return MIN_SCORE_BY_BACKEND.get(backend_name or "", DEFAULT_MIN_SCORE)


@dataclass
class RetrievedChunk:
    """One passage, ready to be shown to a model or a person."""

    text: str
    citation: str
    document_title: str
    document_path: str
    is_demo: bool
    heading: str | None
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "citation": self.citation,
            "document_title": self.document_title,
            "document_path": self.document_path,
            "is_demo": self.is_demo,
            "heading": self.heading,
            "score": round(self.score, 4),
        }


@dataclass
class RetrievalResult:
    """What a search produced, plus enough context to explain an empty result."""

    question: str
    chunks: list[RetrievedChunk]
    embedding_backend: str
    embedding_note: str
    indexed: bool
    chunk_count: int
    error_code: str | None = None
    error: str | None = None

    @property
    def found(self) -> bool:
        return bool(self.chunks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "found": self.found,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "sources": sorted({chunk.citation for chunk in self.chunks}),
            "contains_demo_content": any(chunk.is_demo for chunk in self.chunks),
            "embedding_backend": self.embedding_backend,
            "embedding_note": self.embedding_note,
            "indexed": self.indexed,
            "indexed_chunk_count": self.chunk_count,
            "error_code": self.error_code,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Step 1: documents -> text
# ---------------------------------------------------------------------------

def _read_document(path: Path) -> str:
    """Plain text from a source document, whatever its format."""
    suffix = path.suffix.lower()

    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="replace")

    if suffix in {".pdf", ".docx"}:
        # Reuse the CV feature's extractor - one place knows file formats.
        return extract_cv_text(path.name, path.read_bytes()).text

    raise ValueError(f"{path.name}: unsupported document type '{suffix}'")


def _title_of(path: Path, text: str) -> str:
    """A readable document name: the first heading, else the file name."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            # Drop the demo prefix; is_demo already records that, and repeating
            # it inside every citation makes them unreadable.
            for marker in ("DEMO SmartHR HR Policy - ", "DEMO SmartHR HR Policy -"):
                if title.startswith(marker):
                    return title[len(marker):].strip()
            return title

    return path.stem.replace("-", " ").replace("_", " ").title()


def discover_documents() -> list[tuple[Path, bool]]:
    """Every indexable document, paired with whether it is demo material."""
    found: list[tuple[Path, bool]] = []

    for directory, is_demo in ((DEMO_DIR, True), (COMPANY_DIR, False)):
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
                found.append((path, is_demo))

    return found


def _embeddable(chunk: "StoredChunk") -> str:
    """What actually gets embedded: the chunk, plus where it came from.

    The body alone is not always enough. The onboarding policy, for instance,
    says "new employee", "induction" and "probation" throughout but only uses
    the word *onboarding* in its title - so a question asking about onboarding
    matched nothing in it until the title was included. Prefixing the document
    title and section heading makes a chunk findable by what it is about, not
    only by the words that happen to be inside it.

    Only the embedded text changes; `chunk.text` is still what gets shown and
    sent to the model, so no citation ever quotes a heading as if it were body
    text.
    """
    parts = [chunk.document_title]

    if chunk.heading:
        parts.append(chunk.heading)

    parts.append(chunk.text)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Ingestion: the whole pipeline, one call
# ---------------------------------------------------------------------------

def ingest_knowledge_base(store: VectorStore | None = None) -> dict[str, Any]:
    """Rebuild the index from everything in `knowledge/`.

    Rebuilds rather than updates: the corpus is small, and a full rebuild
    cannot leave chunks behind from a document that was edited or deleted.
    """
    store = store or VectorStore()
    backend = get_embedding_backend()
    documents = discover_documents()

    if not documents:
        store.clear(backend.name, backend.dimensions)
        store.save()
        return {
            "indexed_documents": 0, "indexed_chunks": 0, "skipped": [],
            "embedding_backend": backend.name,
            "note": "No documents found under knowledge/.",
        }

    store.clear(backend.name, backend.dimensions)
    prepared: list[StoredChunk] = []
    skipped: list[dict[str, str]] = []

    for path, is_demo in documents:
        try:
            text = _read_document(path)
        except (CvExtractionError, ValueError, OSError) as exc:
            logger.warning("RAG skipped document | file=%s reason=%s", path.name, exc)
            skipped.append({"document": path.name, "reason": str(exc)})
            continue

        if not text.strip():
            skipped.append({"document": path.name, "reason": "no text could be read"})
            continue

        title = _title_of(path, text)
        relative = path.relative_to(KNOWLEDGE_ROOT).as_posix()
        chunks = chunk_text(text)

        for chunk in chunks:
            prepared.append(
                StoredChunk(
                    id=f"{relative}#{chunk.index}",
                    text=chunk.text,
                    vector=[],  # filled in below, in one batch
                    document_title=title,
                    document_path=relative,
                    is_demo=is_demo,
                    heading=chunk.heading,
                    chunk_index=chunk.index,
                )
            )

        logger.info(
            "RAG document chunked | file=%s chunks=%s demo=%s",
            relative, len(chunks), is_demo,
        )

    if prepared:
        corpus = [_embeddable(chunk) for chunk in prepared]

        # Backends that learn from the corpus (the lexical one needs IDF
        # weights) are fitted here, before anything is embedded.
        if hasattr(backend, "fit"):
            backend.fit(corpus)

        # One batch call rather than one per chunk - far fewer round trips when
        # the backend is a hosted embedding API.
        vectors = backend.embed(corpus)
        for chunk, vector in zip(prepared, vectors):
            chunk.vector = vector

    store.add(prepared)

    if hasattr(backend, "state"):
        # Saved with the index so a question is scored with the same weights.
        store.set_backend_state(backend.state())

    store.save()

    summary = {
        "indexed_documents": len({c.document_path for c in prepared}),
        "indexed_chunks": len(prepared),
        "demo_documents": sorted({c.document_path for c in prepared if c.is_demo}),
        "real_documents": sorted({c.document_path for c in prepared if not c.is_demo}),
        "skipped": skipped,
        "embedding_backend": backend.name,
        "embedding_note": backend.describe(),
        "index_path": str(store.path),
    }

    logger.info(
        "RAG ingestion complete | documents=%s chunks=%s backend=%s",
        summary["indexed_documents"], summary["indexed_chunks"], backend.name,
    )

    return summary


# ---------------------------------------------------------------------------
# Retrieval: the function every caller uses
# ---------------------------------------------------------------------------

_default_store = VectorStore()


def search_policies(
    question: str,
    top_k: int = DEFAULT_TOP_K,
    min_score: float | None = None,
    store: VectorStore | None = None,
) -> RetrievalResult:
    """Find the passages most relevant to a question.

    Returns an empty result rather than a poor one when nothing clears the
    similarity threshold. "We have nothing on that" is a correct answer, and
    the only honest one when the documents genuinely do not cover a topic.

    `min_score` defaults to the floor for the *active embedding backend* rather
    than to a single constant, because lexical and dense embeddings score on
    different scales - see `MIN_SCORE_BY_BACKEND`. Pass a number to override.
    """
    store = store or _default_store
    backend = get_embedding_backend()
    stats = store.stats()

    if min_score is None:
        min_score = min_score_for(backend.name)

    base = {
        "embedding_backend": backend.name,
        "embedding_note": backend.describe(),
        "indexed": stats["indexed"],
        "chunk_count": stats["chunk_count"],
    }

    if not (question or "").strip():
        return RetrievalResult(question=question, chunks=[], **base,
                               error_code="empty_question",
                               error="Ask a question to search the documents.")

    if not stats["indexed"]:
        return RetrievalResult(
            question=question, chunks=[], **base,
            error_code="not_indexed",
            error=("No documents have been indexed yet. Run "
                   "`python -m app.rag.ingest` to build the index."),
        )

    if stats["embedding_backend"] != backend.name:
        # The index was built with a different embedding model, so its vectors
        # are not comparable with this one's. Refusing beats silently returning
        # nonsense scores.
        return RetrievalResult(
            question=question, chunks=[], **base,
            error_code="backend_mismatch",
            error=(f"The index was built with '{stats['embedding_backend']}' "
                   f"embeddings but '{backend.name}' is configured now. "
                   "Re-run `python -m app.rag.ingest`."),
        )

    if hasattr(backend, "load_state"):
        # Without this the question would be weighted differently from the
        # chunks, and every score would be quietly wrong.
        backend.load_state(store.backend_state())

    try:
        query_vector = backend.embed([question])[0]
    except EmbeddingError as exc:
        logger.warning("RAG query embedding failed | code=%s", exc.code)
        return RetrievalResult(question=question, chunks=[], **base,
                               error_code=exc.code, error=str(exc))

    hits: list[SearchHit] = store.search(query_vector, top_k=top_k, min_score=min_score)

    logger.info(
        "RAG search | chars=%s hits=%s top_score=%s backend=%s",
        len(question), len(hits),
        round(hits[0].score, 4) if hits else None, backend.name,
    )

    return RetrievalResult(
        question=question,
        chunks=[
            RetrievedChunk(
                text=hit.chunk.text,
                citation=hit.chunk.citation(),
                document_title=hit.chunk.document_title,
                document_path=hit.chunk.document_path,
                is_demo=hit.chunk.is_demo,
                heading=hit.chunk.heading,
                score=hit.score,
            )
            for hit in hits
        ],
        **base,
    )


def knowledge_base_status() -> dict[str, Any]:
    """What is indexed right now - for diagnostics and /ai/status."""
    backend = get_embedding_backend()
    stats = _default_store.stats()
    stats["embedding_backend_configured"] = backend.name
    stats["embedding_note"] = backend.describe()
    stats["knowledge_root"] = str(KNOWLEDGE_ROOT)
    return stats


def reset_default_store() -> None:
    """Force the shared store to re-read the index file (used after ingest)."""
    _default_store.invalidate()
