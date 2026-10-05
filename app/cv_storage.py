"""Where uploaded CV files are put on disk.

The `cvs` table stores a `file_path`, so the bytes have to live somewhere. They
go under `uploads/cvs/` beside the application, never inside the served
frontend, and never under a name the client chose.

Two rules matter here:

* **The stored name is generated, not supplied.** A client-supplied name is the
  classic path-traversal vector (`../../app/main.py`) and can also collide with
  an existing file. The original name is kept separately in `cvs.file_name`
  for display; the bytes sit under a random name plus the real extension.
* **Nothing is ever executed.** Files are written, read back as bytes and
  parsed for text. No extension is registered, nothing is served from this
  directory, and the extension is taken from the detected file type rather
  than from the upload.
"""

import re
import secrets
import unicodedata
from datetime import datetime
from pathlib import Path

#: app/cv_storage.py -> app -> SmartHR
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CV_UPLOAD_DIR = PROJECT_ROOT / "uploads" / "cvs"


def display_filename(raw: str | None) -> str:
    """A safe version of the client's filename, for `cvs.file_name`.

    Kept readable because it is what HR sees in the candidates table, but
    stripped of anything that could be mistaken for a path.
    """
    name = unicodedata.normalize("NFKC", (raw or "").strip())
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.lstrip(".") or "cv"
    # cvs.file_name is varchar(255).
    return name[:255]


def store_cv_file(data: bytes, file_type: str) -> str:
    """Write the upload and return the path recorded in `cvs.file_path`.

    The returned path is relative to the project root, so the row stays valid
    if the project is moved.
    """
    CV_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    stored_name = f"{stamp}-{secrets.token_hex(8)}.{file_type}"
    destination = CV_UPLOAD_DIR / stored_name

    destination.write_bytes(data)

    return str(Path("uploads") / "cvs" / stored_name).replace("\\", "/")
