"""Step 4 of the pipeline: storing vectors and searching them.

    [chunk + vector, chunk + vector, ...]  ->  search(question_vector)  ->  top matches

**Why a JSON file and not pgvector.** pgvector was the first choice and it was
checked, not assumed:

    SELECT * FROM pg_available_extensions WHERE name ILIKE '%vector%';
    -> 0 rows

The server is PostgreSQL 18.6 and the pgvector extension is **not installed**,
so `CREATE EXTENSION vector` fails. Installing it is a server-side job - binaries
onto the database host, not something an application can do - and SmartHR has no
migration tool (no Alembic; the schema comes from `smarthr_backup.sql`). Weighed
against a corpus of four short policy documents, that is a lot of infrastructure
for a search that a laptop does in under a millisecond.

So the index is a single JSON file. At this size that is not a compromise: the
whole corpus is a few dozen chunks, brute-force cosine over them is exact (no
approximation, unlike an ANN index) and instant, and the file can be opened and
read by a human, which matters on a learning project.

**This is behind `VectorStore`, so it is swappable.** The service above only
calls `add`, `search`, `clear` and `stats`. Moving to pgvector later means
writing a `PgVectorStore` with those four methods; nothing else changes. The
point at which that becomes worth doing is roughly when the corpus outgrows
memory or several servers need to share one index - thousands of documents,
not four.
"""

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("smarthr.rag")

#: Where the index lives. Beside the code, like `uploads/`.
INDEX_PATH = Path(__file__).resolve().parents[2] / "rag_index" / "index.json"


@dataclass
class StoredChunk:
    """A chunk, its vector, and everything needed to cite it."""

    id: str
    text: str
    #: Sparse: bucket -> weight. JSON turns the integer keys into strings, so
    #: `_load` converts them back.
    vector: dict[int, float]
    #: Display name of the source document, e.g. "Leave Policy".
    document_title: str
    #: Path relative to knowledge/, e.g. "demo/leave-policy.md".
    document_path: str
    #: True when the document came from knowledge/demo/. Carried all the way to
    #: the answer so demo policy is never presented as real policy.
    is_demo: bool
    heading: str | None = None
    chunk_index: int = 0

    def citation(self) -> str:
        """How this chunk is credited in an answer."""
        label = f"DEMO SmartHR HR Policy - {self.document_title}" if self.is_demo \
            else self.document_title
        return f"{label}, {self.heading}" if self.heading else label


def _chunk_from_json(row: dict[str, Any]) -> "StoredChunk":
    """Rebuild a chunk, turning JSON's string vector keys back into ints."""
    data = dict(row)
    data["vector"] = {int(k): float(v) for k, v in (row.get("vector") or {}).items()}
    return StoredChunk(**data)


@dataclass
class SearchHit:
    chunk: StoredChunk
    #: Cosine similarity, 0.0 to 1.0. Higher is more relevant.
    score: float


@dataclass
class VectorIndex:
    """What gets written to disk."""

    backend: str
    dimensions: int
    chunks: list[StoredChunk] = field(default_factory=list)
    #: Anything the embedding backend learned from this corpus - for the
    #: lexical backend, its IDF weights. Stored with the index so a question is
    #: scored with exactly the weights the chunks were scored with. Score a
    #: query with different weights and the numbers are quietly meaningless.
    backend_state: dict[str, Any] = field(default_factory=dict)


def cosine_similarity(a: dict[int, float], b: dict[int, float]) -> float:
    """How alike two vectors are, from -1 to 1.

    Both sides are already normalised to length 1 by `embeddings.py`, so the
    dot product *is* the cosine - no division needed. Intuitively: it measures
    whether two vectors point the same way, ignoring how long they are, which
    is why a short question can match a long paragraph.

    The vectors are sparse, so only buckets present in *both* contribute -
    everything else multiplies by zero. Iterating the shorter one (normally the
    question) keeps this proportional to the question's length, not the
    vocabulary's.
    """
    if len(a) > len(b):
        a, b = b, a

    return sum(value * b[bucket] for bucket, value in a.items() if bucket in b)


class VectorStore:
    """A JSON-file vector store. Swap-in point for pgvector later."""

    def __init__(self, path: Path = INDEX_PATH):
        self.path = path
        self._index: VectorIndex | None = None

    # ---- persistence ----------------------------------------------------

    def _load(self) -> VectorIndex:
        if self._index is not None:
            return self._index

        if not self.path.is_file():
            self._index = VectorIndex(backend="none", dimensions=0, chunks=[])
            return self._index

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._index = VectorIndex(
                backend=raw.get("backend", "unknown"),
                dimensions=int(raw.get("dimensions", 0)),
                chunks=[_chunk_from_json(row) for row in raw.get("chunks", [])],
                backend_state=raw.get("backend_state") or {},
            )
        except Exception:
            # A corrupt index must not take the assistant down; it degrades to
            # "no documents indexed", which the caller reports honestly.
            logger.exception("RAG index could not be read | path=%s", self.path)
            self._index = VectorIndex(backend="unreadable", dimensions=0, chunks=[])

        return self._index

    def save(self) -> None:
        """Write the index atomically, so a crash cannot leave half a file."""
        index = self._load()
        self.path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "backend": index.backend,
            "dimensions": index.dimensions,
            "chunk_count": len(index.chunks),
            "backend_state": index.backend_state,
            "chunks": [asdict(chunk) for chunk in index.chunks],
        }

        handle, temporary = tempfile.mkstemp(
            dir=str(self.path.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=1)
            os.replace(temporary, self.path)
        except Exception:
            if os.path.exists(temporary):
                os.remove(temporary)
            raise

        logger.info(
            "RAG index saved | chunks=%s backend=%s path=%s",
            len(index.chunks), index.backend, self.path,
        )

    # ---- the four operations a store must support -----------------------

    def clear(self, backend: str, dimensions: int) -> None:
        self._index = VectorIndex(backend=backend, dimensions=dimensions, chunks=[])

    def set_backend_state(self, state: dict[str, Any]) -> None:
        self._load().backend_state = state or {}

    def backend_state(self) -> dict[str, Any]:
        return self._load().backend_state

    def add(self, chunks: list[StoredChunk]) -> None:
        self._load().chunks.extend(chunks)

    def search(
        self,
        query_vector: list[float],
        top_k: int = 4,
        min_score: float = 0.0,
    ) -> list[SearchHit]:
        """The most similar chunks, best first.

        Brute force over every chunk. With a corpus this size that is both the
        simplest thing that works and the most accurate - it considers every
        chunk, where an approximate index would not.
        """
        index = self._load()

        hits = [
            SearchHit(chunk=chunk, score=cosine_similarity(query_vector, chunk.vector))
            for chunk in index.chunks
        ]
        hits.sort(key=lambda hit: hit.score, reverse=True)

        # The threshold is what stops an off-topic question returning the
        # least-irrelevant paragraph and having it read as an answer.
        return [hit for hit in hits if hit.score >= min_score][:top_k]

    def stats(self) -> dict[str, Any]:
        index = self._load()
        documents = {chunk.document_path for chunk in index.chunks}

        return {
            "indexed": bool(index.chunks),
            "chunk_count": len(index.chunks),
            "document_count": len(documents),
            "documents": sorted(documents),
            "demo_documents": sorted(
                {c.document_path for c in index.chunks if c.is_demo}
            ),
            "real_documents": sorted(
                {c.document_path for c in index.chunks if not c.is_demo}
            ),
            "embedding_backend": index.backend,
            "dimensions": index.dimensions,
            "index_path": str(self.path),
        }

    def invalidate(self) -> None:
        """Drop the in-memory copy so the next read re-loads from disk."""
        self._index = None
