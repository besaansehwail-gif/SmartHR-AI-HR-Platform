"""Step 3 of the pipeline: turning text into vectors.

    "How many annual leave days?"  ->  [0.013, -0.221, 0.004, ...]  (numbers)

An **embedding** is a list of numbers that represents a piece of text's
meaning. Two texts that mean similar things get similar lists. That is the
whole trick behind semantic search: once text is numbers, "which chunk is most
like this question?" becomes arithmetic.

**An embedding model is not the same thing as an LLM.** The LLM
(`app/ai/provider.py`) takes text and writes text. An embedding model takes
text and returns a fixed-length vector; it cannot answer anything. SmartHR uses
both, for different jobs, and they can come from different vendors.

**Which is why this file is separate from `app/ai/provider.py`.** SmartHR's
configured LLM provider is Anthropic, and *Anthropic does not offer an
embeddings API* - it has no equivalent of `/v1/embeddings`. So the LLM
abstraction cannot be reused for this no matter how much we would like to. The
two backends here are:

* `OpenAiEmbeddings` - a real neural embedding model
  (`text-embedding-3-small`). Used when an OpenAI key is configured. This
  understands meaning: "time off" finds the annual leave clause even though
  those words never appear in it.

* `LexicalEmbeddings` - a local fallback needing no key and no network. It is
  honest arithmetic, not a stub: it hashes words (and word pairs) into a fixed
  number of buckets, weights them, and normalises the result, so cosine
  similarity over these vectors is real similarity. But it matches *words*, not
  *meaning* - ask about "time off" and it will not find "annual leave" unless
  the wording overlaps. It exists so the whole pipeline is runnable and
  testable today, and so SmartHR degrades to weaker retrieval rather than to no
  retrieval.

`describe()` on each backend says which one answered, and that label is carried
all the way to the UI - a reader should never have to guess whether they got
semantic search or keyword-ish search.
"""

import hashlib
import json
import logging
import math
import re
import urllib.error
import urllib.request
from typing import Any, Protocol

from app.ai.config import llm_settings

logger = logging.getLogger("smarthr.rag")

# The local backend gives every distinct term its own slot, learned from the
# corpus during fit(). An earlier version hashed terms into a fixed number of
# buckets instead - which is the standard trick for very large corpora, but
# here it silently broke retrieval: "late" and "30" hashed to the same bucket,
# so "what happens if I am late?" matched the onboarding section "First 30
# days". With a few thousand distinct terms, an explicit vocabulary has no
# collisions at all and costs a few hundred kilobytes.

OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_EMBEDDING_URL = "https://api.openai.com/v1/embeddings"

# Letters and digits only - apostrophes are deliberately NOT kept. Keeping
# them makes "company's" a separate, rare token from "company", and a rare
# token scores high under IDF: a question asking about "the company's policy on
# X" then matches any chunk containing "the company's", regardless of topic.
_WORD = re.compile(r"[a-z0-9]+|[؀-ۿ]+")

#: Ordinary English function words. They carry no topic signal, so they are
#: dropped before hashing.
#:
#: Prepositions like "during" matter more than they look. "During" is rare in
#: this corpus, so IDF scores it as highly distinctive, and the question "what
#: happens during employee onboarding?" then matched "leave during a notice
#: period" on that one word alone. A word being rare is not the same as a word
#: being meaningful.
_STOPWORDS = frozenset("""
a an the and or but if of to in on at for from by with without as is are was
were be been being am do does did doing have has had having i me my we our you
your he she it they them this that these those what which who whom when where
how why can could should would may might will shall must not no nor so than
too very just about into over under again further then once here there all any
both each few more most other some such only own same s t don now
during while per within before after between upon since until against among
through throughout above below off out up down every either neither whether
because although though however therefore thus moreover else ever never always
often usually normally generally also whose whom being get got give given take
taken make made happen happens happened need needs allowed allow allows
according many much
ll ve re im id dont cant wont isnt arent doesnt didnt wasnt werent
""".split())

#: Words that are everywhere in *this* corpus specifically, so they cannot tell
#: one document from another.
#:
#: This is separate from the list above because it is a property of the
#: documents, not of English. In a folder of company HR policies, "company",
#: "employee" and "policy" appear throughout; a question containing them
#: matches everything a little, and with only a few dozen chunks that was
#: enough for "the company's policy on international relocation" - a topic
#: absent from every document - to score above the relevance threshold on the
#: word "company" alone.
#:
#: WORTH REVIEWING when the demo documents are replaced with real ones: a
#: different corpus has different filler. Anything listed here becomes
#: unsearchable, so keep it to words that genuinely appear across the board.
_DOMAIN_STOPWORDS = frozenset("""
company companys employee employees employer staff policy policies procedure
smarthr document documents demo version owner
""".split())

_IGNORED = _STOPWORDS | _DOMAIN_STOPWORDS


class EmbeddingError(Exception):
    """Embedding failed for a reason worth reporting."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


class EmbeddingBackend(Protocol):
    name: str
    dimensions: int

    def embed(self, texts: list[str]) -> list[Vector]:
        ...

    def describe(self) -> str:
        ...

    # Optional. A backend that learns from the corpus (the lexical one, which
    # needs IDF weights) implements these; a hosted model does not need to,
    # because its weights are already trained. The service checks with
    # hasattr() rather than requiring every backend to carry empty stubs.
    #
    # def fit(self, corpus: list[str]) -> None: ...
    # def state(self) -> dict[str, Any]: ...
    # def load_state(self, state: dict[str, Any] | None) -> None: ...


#: A vector is stored **sparsely**: slot -> weight, with zeros left out.
#: A chunk touches a few hundred slots out of a vocabulary of thousands, so
#: listing only the non-zero ones is far smaller than a dense list - and cosine
#: similarity never needs the zeros anyway.
Vector = dict[int, float]


def _normalise(vector: Vector) -> Vector:
    """Scale a vector to length 1.

    Once every vector has length 1, the cosine similarity between two of them
    is just their dot product - which is why `store.py` can score with a single
    multiply-and-add loop and no square roots.
    """
    length = math.sqrt(sum(value * value for value in vector.values()))

    if length == 0:
        return vector

    return {bucket: value / length for bucket, value in vector.items()}


def tokenize(text: str) -> list[str]:
    """Lowercase words, minus the ones that carry no topic signal."""
    return [
        word
        for word in _WORD.findall((text or "").lower())
        if word not in _IGNORED and len(word) > 1
    ]


class LexicalEmbeddings:
    """Local, deterministic, no key required. Matches words, not meaning.

    Two ideas, both worth understanding because they are what make a small
    corpus searchable at all:

    **A vocabulary.** Every distinct term seen during `fit()` gets its own slot
    in the vector. Term 0 might be "annual", term 1 "leave", and so on. A
    chunk's vector records how much of each term it contains.

    **IDF weighting** (inverse document frequency): a term appearing in every
    chunk tells you nothing about which chunk you want. In a folder of HR
    policies, "employee" and "manager" are everywhere; "probation", "overtime"
    and "relocation" are not. IDF scores each term by how *rare* it is, so the
    rare ones dominate. Without it, a question matches every document a little
    through its common words, and the least-irrelevant one comes back looking
    like an answer - the single biggest cause of a confident wrong answer.

    Both are learned once over the corpus at ingest time and stored with the
    index, so a question is scored with exactly the weights its chunks were.
    """

    name = "local-lexical"

    def __init__(self) -> None:
        #: term -> slot. Learned by fit(), restored by load_state().
        self._vocab: dict[str, int] = {}
        #: slot -> IDF weight.
        self._idf: dict[int, float] = {}

    @property
    def dimensions(self) -> int:
        return len(self._vocab)

    def _terms(self, text: str) -> dict[str, float]:
        """Raw term counts for one text, before the vocabulary is applied."""
        counts: dict[str, float] = {}
        words = tokenize(text)

        for word in words:
            counts[word] = counts.get(word, 0.0) + 1.0

        # Word pairs capture a little word order: "annual leave" becomes its
        # own term, so it scores above a chunk that merely says "annual" and
        # "leave" far apart.
        for first, second in zip(words, words[1:]):
            pair = f"{first} {second}"
            counts[pair] = counts.get(pair, 0.0) + 0.5

        return counts

    def fit(self, corpus: list[str]) -> None:
        """Learn the vocabulary and how common each term is.

        A term in every chunk gets a weight near zero; a term in one chunk gets
        the highest weight. Called once during ingestion.
        """
        self._vocab = {}
        document_frequency: dict[int, int] = {}

        for text in corpus:
            for term in self._terms(text):
                slot = self._vocab.setdefault(term, len(self._vocab))
                document_frequency[slot] = document_frequency.get(slot, 0) + 1

        total = len(corpus) or 1

        # Standard smoothed IDF: log((N + 1) / (df + 1)) + 1, which stays
        # positive even for a term present in every chunk.
        self._idf = {
            slot: math.log((total + 1) / (count + 1)) + 1.0
            for slot, count in document_frequency.items()
        }

    def state(self) -> dict[str, Any]:
        """The vocabulary and weights, for storing alongside the index."""
        return {
            "vocab": self._vocab,
            "idf": {str(slot): round(value, 6) for slot, value in self._idf.items()},
        }

    def load_state(self, state: dict[str, Any] | None) -> None:
        """Restore what was learned, so queries match the index's scoring."""
        state = state or {}
        self._vocab = {str(k): int(v) for k, v in (state.get("vocab") or {}).items()}
        self._idf = {int(k): float(v) for k, v in (state.get("idf") or {}).items()}

    def embed(self, texts: list[str]) -> list[Vector]:
        vectors: list[Vector] = []
        fitting = not self._vocab

        for text in texts:
            vector: Vector = {}

            for term, count in self._terms(text).items():
                slot = self._vocab.get(term)

                if slot is None:
                    if not fitting:
                        # A term no document contains cannot match anything, so
                        # it is dropped rather than given a slot of its own.
                        continue
                    slot = self._vocab.setdefault(term, len(self._vocab))

                # log1p dampens repetition: a word said ten times is not ten
                # times as relevant. IDF then scales by how rare it is.
                weight = self._idf.get(slot, 1.0)
                vector[slot] = math.log1p(count) * weight

            vectors.append(_normalise(vector))

        return vectors

    def describe(self) -> str:
        return (
            "local lexical embeddings with IDF weighting (no API key needed). "
            "Matches wording rather than meaning, so a question phrased very "
            "differently from the document may not find it."
        )


class OpenAiEmbeddings:
    """Real neural embeddings from OpenAI. Requires an OpenAI API key."""

    name = "openai"
    dimensions = 1536

    def __init__(self, api_key: str, model: str = OPENAI_EMBEDDING_MODEL):
        self._api_key = api_key
        self.model = model

    def embed(self, texts: list[str]) -> list[Vector]:
        request = urllib.request.Request(
            OPENAI_EMBEDDING_URL,
            data=json.dumps({"model": self.model, "input": texts}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            raise EmbeddingError(
                f"The embedding provider returned {exc.code}: {body}",
                code="embedding_http_error",
            ) from exc
        except Exception as exc:
            raise EmbeddingError(
                f"Could not reach the embedding provider: {exc}",
                code="embedding_unreachable",
            ) from exc

        rows = payload.get("data") or []

        if len(rows) != len(texts):
            raise EmbeddingError(
                "The embedding provider returned the wrong number of vectors.",
                code="embedding_malformed",
            )

        # Sort by index: the API documents that order is not guaranteed.
        rows.sort(key=lambda row: row.get("index", 0))
        # A neural embedding is dense, but it is held in the same sparse shape
        # so the store has one representation to deal with.
        return [
            _normalise({i: float(v) for i, v in enumerate(row["embedding"])})
            for row in rows
        ]

    def describe(self) -> str:
        return f"OpenAI {self.model} embeddings (semantic search)."


def get_embedding_backend() -> EmbeddingBackend:
    """Pick the best embedding backend the current configuration allows.

    An OpenAI key enables real semantic search. Everything else - including an
    Anthropic key, since Anthropic has no embeddings API - falls back to local
    lexical embeddings, which need nothing.
    """
    settings = llm_settings()

    if settings.provider == "openai" and settings.api_key:
        return OpenAiEmbeddings(settings.api_key)

    # Honour a standalone OpenAI key even when the chat provider is Anthropic:
    # using Claude to write answers and OpenAI to embed is a normal setup.
    from app.ai.config import _setting

    openai_key = _setting("OPENAI_API_KEY")

    if openai_key:
        return OpenAiEmbeddings(openai_key)

    return LexicalEmbeddings()
