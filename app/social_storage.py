"""Where Social Hub images are put on disk, and how they get back out.

This is `cv_storage.py`'s sibling and follows its two rules exactly:

* **The stored name is generated, not supplied.** A client-supplied filename is
  the classic path-traversal vector (`../../app/main.py`) and can collide with
  an existing file. Nothing here ever uses the name the browser sent.
* **The type comes from the file's signature, not its extension.** A `.png`
  that is really a script is refused, and the extension written to disk is the
  one the bytes actually say.

**The one real difference from CVs: these files have to be shown.** A CV is
parsed and never served; a post image is the whole point of a post. So this
module also resolves a stored name back to a path, and `GET /social/media/{name}`
serves it - behind `require_staff`, like every other Social Hub route, so an
Applicant cannot read a colleague's photograph by guessing a URL. The directory
itself is not a static mount: nothing under `uploads/` is reachable except
through that guarded route.

Nothing is ever executed. Files are written as bytes and read back as bytes.
"""

import re
import secrets
from datetime import datetime
from pathlib import Path

#: app/social_storage.py -> app -> SmartHR
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOCIAL_UPLOAD_DIR = PROJECT_ROOT / "uploads" / "social"

#: 4 MB. A post image is decoration on a text post, not a deliverable, and the
#: browser is going to download it on every feed render.
MAX_IMAGE_BYTES = 4 * 1024 * 1024

#: The stored name is `<timestamp>-<random>.<ext>`, so this is what a valid
#: name looks like. Anything else is rejected before a path is built, which is
#: what keeps `..` and absolute paths out of the serving route.
STORED_NAME_RE = re.compile(r"^[0-9]{14}-[0-9a-f]{16}\.(png|jpg|gif|webp)$")

#: Signature -> (extension, media type). Detection is by magic bytes only; the
#: uploaded filename is never consulted.
_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"GIF87a", "gif", "image/gif"),
    (b"GIF89a", "gif", "image/gif"),
]

MEDIA_TYPES: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}


class ImageError(Exception):
    """An upload SmartHR will not store, with a code the router maps to HTTP.

    Codes: empty_file, file_too_large, unsupported_type.
    """

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def detect_image_type(data: bytes) -> str:
    """The file's real type, from its first bytes.

    Raises `ImageError` rather than guessing. WebP is a RIFF container, so it
    is checked as a pair of markers rather than one prefix.
    """
    if not data:
        raise ImageError("The file is empty.", "empty_file")

    if len(data) > MAX_IMAGE_BYTES:
        raise ImageError(
            f"Images must be {MAX_IMAGE_BYTES // (1024 * 1024)} MB or smaller.",
            "file_too_large",
        )

    for signature, extension, _media in _SIGNATURES:
        if data.startswith(signature):
            return extension

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"

    raise ImageError(
        "Only PNG, JPEG, GIF and WebP images can be uploaded.",
        "unsupported_type",
    )


def store_image(data: bytes) -> str:
    """Write the image and return the path recorded on the row.

    The returned path is relative to the project root, so rows stay valid if
    the project is moved - the same convention `cvs.file_path` follows.
    """
    extension = detect_image_type(data)

    SOCIAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    stored_name = f"{stamp}-{secrets.token_hex(8)}.{extension}"

    (SOCIAL_UPLOAD_DIR / stored_name).write_bytes(data)

    return str(Path("uploads") / "social" / stored_name).replace("\\", "/")


def media_name(stored_path: str | None) -> str | None:
    """The bare filename from a stored path, for building a media URL."""
    if not stored_path:
        return None

    return stored_path.replace("\\", "/").rsplit("/", 1)[-1]


def media_url(stored_path: str | None) -> str | None:
    """The URL the browser fetches, or None when there is no image.

    Deliberately returns the API path rather than the disk path: the disk path
    is an implementation detail and is never sent to a client.
    """
    name = media_name(stored_path)

    return f"/social/media/{name}" if name else None


def resolve_media(name: str) -> tuple[Path, str] | None:
    """Locate a stored image by name, or None if there is no such file.

    The name is matched against `STORED_NAME_RE` **before** it is joined to a
    directory, so a traversal attempt never becomes a path at all. The result
    is additionally checked to be inside the upload directory, which catches
    anything the pattern somehow admitted.
    """
    if not STORED_NAME_RE.match(name or ""):
        return None

    candidate = (SOCIAL_UPLOAD_DIR / name).resolve()

    try:
        candidate.relative_to(SOCIAL_UPLOAD_DIR.resolve())
    except ValueError:
        return None

    if not candidate.is_file():
        return None

    extension = candidate.suffix.lstrip(".").lower()

    return candidate, MEDIA_TYPES.get(extension, "application/octet-stream")
