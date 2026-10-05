"""Step 2 of the pipeline: splitting a document into chunks.

    document text  ->  [chunk, chunk, chunk, ...]

**Why split at all?** Two reasons, and both matter.

First, a whole policy document is too big to hand to a model for every
question, and most of it is irrelevant to any one question. Second, and less
obvious: search works better on small pieces. If you turn a 2000-word document
into a single point in "meaning space", that point is an average of everything
it says, and it will not sit close to any specific question. A paragraph about
sick leave, on its own, sits very close to "how many sick days do I get?".

**The strategy here** is paragraph-packing with overlap:

* Split the text on blank lines, which in a policy document means paragraphs,
  headings and list blocks.
* Pack consecutive paragraphs together until adding the next one would exceed
  `CHUNK_SIZE` characters.
* Carry the last `CHUNK_OVERLAP` characters of each chunk into the start of the
  next one.

Overlap exists so a sentence that straddles a boundary is not lost to both
sides. Without it, "...entitled to 21 working days | of paid annual leave..."
could split so that neither chunk answers the question.

Headings are tracked as the text is walked, and the current heading is stored
with the chunk. That is what lets an answer say *Leave Policy, section 3. Sick
leave* rather than just naming the file.
"""

import re
from dataclasses import dataclass

#: Target chunk size in characters. Big enough to hold a whole policy clause,
#: small enough that a retrieved chunk is mostly about one thing. Characters
#: rather than tokens keeps this readable and dependency-free; roughly 900
#: characters is about 150-200 English words.
CHUNK_SIZE = 900

#: How much of the end of one chunk is repeated at the start of the next.
CHUNK_OVERLAP = 150

#: A chunk shorter than this is not worth indexing on its own (a stray heading,
#: a one-word line); it is merged into the previous chunk instead.
MIN_CHUNK_SIZE = 80

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass
class Chunk:
    """One retrievable piece of a document."""

    text: str
    #: The nearest heading above this chunk, e.g. "3. Sick leave". Used in
    #: citations so a reader can find the passage in the original document.
    heading: str | None
    #: 0-based position within the document, for stable ordering and ids.
    index: int


def _split_paragraphs(text: str) -> list[tuple[str, str | None]]:
    """Paragraphs, each tagged with the heading in force above it."""
    blocks: list[tuple[str, str | None]] = []
    current_heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        joined = "\n".join(buffer).strip()
        if joined:
            blocks.append((joined, current_heading))
        buffer.clear()

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()

        # Markdown blockquotes are document callouts - the "this is a DEMO
        # document" notice, editor's notes - not policy text. Indexing them
        # actively hurts: the same notice appears in every document, so it is
        # a block of generic words that every question matches a little, and a
        # citation pointing at a disclaimer answers nothing.
        if line.startswith(">"):
            continue

        heading_match = _HEADING.match(line)

        if heading_match:
            # A heading ends the paragraph before it and becomes the label for
            # everything that follows.
            flush()
            level = len(heading_match.group(1))
            title = heading_match.group(2)

            if level == 1:
                # The H1 is the document's title, not a section within it.
                # Recording it as a section heading would produce citations
                # like "Leave Policy, Leave Policy".
                current_heading = None
                continue

            current_heading = title
            # Keep the heading text in the body too: "Sick leave" is a strong
            # search signal for a question about sick leave.
            buffer.append(title)
            continue

        if not line.strip():
            flush()
            continue

        buffer.append(line.rstrip())

    flush()
    return blocks


def chunk_text(text: str) -> list[Chunk]:
    """Split a document into overlapping chunks.

    Deterministic: the same document always produces the same chunks, so
    re-indexing an unchanged file is a no-op rather than a reshuffle.
    """
    chunks: list[Chunk] = []
    current: list[str] = []
    current_heading: str | None = None
    current_length = 0

    def flush() -> None:
        nonlocal current, current_length
        body = "\n\n".join(current).strip()

        if not body:
            current, current_length = [], 0
            return

        if chunks and len(body) < MIN_CHUNK_SIZE:
            # Too small to stand alone - fold it into the previous chunk.
            chunks[-1].text = f"{chunks[-1].text}\n\n{body}"
        else:
            chunks.append(Chunk(text=body, heading=current_heading, index=len(chunks)))

        current, current_length = [], 0

    for paragraph, heading in _split_paragraphs(text):
        # A heading change is a natural topic boundary, so close the chunk if
        # there is already meaningful content in it.
        if heading != current_heading and current_length >= MIN_CHUNK_SIZE:
            flush()

        if current_length + len(paragraph) > CHUNK_SIZE and current:
            tail = "\n\n".join(current)[-CHUNK_OVERLAP:] if CHUNK_OVERLAP else ""
            flush()
            if tail.strip():
                current.append(tail.strip())
                current_length = len(tail)

        current_heading = heading
        current.append(paragraph)
        current_length += len(paragraph) + 2

    flush()

    # Re-number after any merges so index always matches position.
    for position, chunk in enumerate(chunks):
        chunk.index = position

    return chunks
