"""Turning an uploaded CV file into plain text.

Deliberately separate from the AI layer: this module knows about file formats
and nothing about language models, and `cv_parser.py` knows about language
models and nothing about file formats. The only thing that crosses between
them is a string.

Nothing here executes, renders or interprets the upload. A PDF is read for its
text layer and a DOCX is read as the zip of XML that it is; neither library is
asked to run embedded content, and the original bytes are never handed to a
model.
"""

import io
import re
import unicodedata
from dataclasses import dataclass

#: Extensions the feature accepts, mapped to the extractor used.
SUPPORTED_EXTENSIONS = (".pdf", ".docx")

#: Uploads above this are refused before anything tries to parse them.
MAX_FILE_BYTES = 5 * 1024 * 1024

#: A CV shorter than this almost certainly failed to extract - a scanned PDF
#: with no text layer is the usual cause - and is worth saying so about.
MIN_USEFUL_CHARACTERS = 120

#: Guard against handing a novel to the model; CVs are not this long.
MAX_TEXT_CHARACTERS = 40_000

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"  # DOCX is a zip container


class CvExtractionError(Exception):
    """Extraction failed for a reason worth telling the user about."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


@dataclass
class ExtractedCv:
    text: str
    file_type: str
    #: Pages for a PDF, paragraphs for a DOCX - reported so the UI can show
    #: that something real was read out of the file.
    unit_count: int
    character_count: int
    word_count: int
    truncated: bool


def _clean(raw: str) -> str:
    """Normalise whitespace without changing any wording.

    PDF extraction produces ragged spacing and stray control characters; both
    waste model context and make the text hard to read if it is shown. Nothing
    is added, removed or reordered beyond whitespace.
    """
    text = unicodedata.normalize("NFKC", raw)
    text = text.replace(" ", " ").replace("\r\n", "\n").replace("\r", "\n")
    # Drop control characters except tab and newline.
    text = "".join(ch for ch in text if ch in "\t\n" or unicodedata.category(ch)[0] != "C")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_file_type(filename: str, data: bytes) -> str:
    """The file's real type, from its signature - the extension only breaks
    ties. A renamed .exe does not become a CV by being called one."""
    if data.startswith(PDF_MAGIC):
        return "pdf"

    if data.startswith(ZIP_MAGIC):
        # .docx is a zip; so are .xlsx, .pptx and plain .zip. The extension
        # decides which zip we are willing to open.
        if (filename or "").lower().endswith(".docx"):
            return "docx"
        raise CvExtractionError(
            "That looks like a zip archive rather than a .docx document.",
            code="unsupported_type",
        )

    suffix = (filename or "").lower()
    if suffix.endswith(".pdf"):
        raise CvExtractionError(
            "The file is named .pdf but does not start with a PDF signature, "
            "so it is not a readable PDF.",
            code="corrupt_file",
        )
    if suffix.endswith(".docx"):
        raise CvExtractionError(
            "The file is named .docx but is not a valid Word document.",
            code="corrupt_file",
        )

    raise CvExtractionError(
        "Only PDF and DOCX CVs are supported.",
        code="unsupported_type",
    )


def _extract_pdf(data: bytes) -> tuple[str, int]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is installed
        raise CvExtractionError(
            "PDF support is not installed on the server (pypdf).",
            code="extractor_missing",
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(data))

        if getattr(reader, "is_encrypted", False):
            # An empty user password is common and harmless to try; a real
            # password is not something we can or should get around.
            try:
                if reader.decrypt("") == 0:
                    raise CvExtractionError(
                        "This PDF is password protected, so its text cannot be read.",
                        code="encrypted_file",
                    )
            except CvExtractionError:
                raise
            except Exception as exc:
                raise CvExtractionError(
                    "This PDF is password protected, so its text cannot be read.",
                    code="encrypted_file",
                ) from exc

        pages = reader.pages
        parts = []

        for page in pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                # One unreadable page should not lose the rest of the CV.
                parts.append("")

        return "\n\n".join(parts), len(pages)

    except CvExtractionError:
        raise
    except Exception as exc:
        raise CvExtractionError(
            "The PDF could not be opened - it may be corrupted.",
            code="corrupt_file",
        ) from exc


def _extract_docx(data: bytes) -> tuple[str, int]:
    try:
        import docx  # python-docx
    except ImportError as exc:  # pragma: no cover - dependency is installed
        raise CvExtractionError(
            "DOCX support is not installed on the server (python-docx).",
            code="extractor_missing",
        ) from exc

    try:
        document = docx.Document(io.BytesIO(data))

        parts = [paragraph.text for paragraph in document.paragraphs]

        # CVs very often keep dates, roles and skills in tables, which are not
        # paragraphs and would otherwise be dropped entirely.
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                line = " | ".join(c for c in cells if c)
                if line:
                    parts.append(line)

        return "\n".join(parts), len(parts)

    except Exception as exc:
        raise CvExtractionError(
            "The Word document could not be opened - it may be corrupted.",
            code="corrupt_file",
        ) from exc


def extract_cv_text(filename: str, data: bytes) -> ExtractedCv:
    """Plain text from an uploaded CV.

    Raises `CvExtractionError` with a `code` the API turns into a message:
    `unsupported_type`, `empty_file`, `file_too_large`, `corrupt_file`,
    `encrypted_file`, `no_text_layer`, `extractor_missing`.
    """
    if not data:
        raise CvExtractionError("The uploaded file is empty.", code="empty_file")

    if len(data) > MAX_FILE_BYTES:
        raise CvExtractionError(
            f"The file is larger than the {MAX_FILE_BYTES // (1024 * 1024)} MB limit.",
            code="file_too_large",
        )

    file_type = detect_file_type(filename, data)

    raw, unit_count = _extract_pdf(data) if file_type == "pdf" else _extract_docx(data)
    text = _clean(raw)

    if len(text) < MIN_USEFUL_CHARACTERS:
        raise CvExtractionError(
            "Almost no text could be read from this file. A scanned CV saved as "
            "an image has no text layer to extract - a text-based PDF or a DOCX "
            "is needed.",
            code="no_text_layer",
        )

    truncated = len(text) > MAX_TEXT_CHARACTERS
    if truncated:
        text = text[:MAX_TEXT_CHARACTERS]

    return ExtractedCv(
        text=text,
        file_type=file_type,
        unit_count=unit_count,
        character_count=len(text),
        word_count=len(text.split()),
        truncated=truncated,
    )
