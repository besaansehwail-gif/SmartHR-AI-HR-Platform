"""Build the document index.

    venv\\Scripts\\Activate.ps1
    python -m app.rag.ingest

Run this once to index the documents in `knowledge/`, and again whenever a
document is added, edited or removed, or whenever the embedding backend
changes (for example after adding an OpenAI key).
"""

import logging
import os
import sys

from app.rag.service import ingest_knowledge_base, knowledge_base_status


def main() -> int:
    logging.basicConfig(
        level=os.getenv("SMARTHR_LOG_LEVEL", "INFO"),
        stream=sys.stderr,
        format="%(levelname)-5s %(name)s: %(message)s",
    )

    print("Indexing SmartHR knowledge base")
    print("=" * 58)

    summary = ingest_knowledge_base()

    print(f"  embedding backend : {summary['embedding_backend']}")
    print(f"  {summary.get('embedding_note', '')}")
    print(f"  documents indexed : {summary['indexed_documents']}")
    print(f"  chunks indexed    : {summary['indexed_chunks']}")

    for path in summary.get("demo_documents", []):
        print(f"    DEMO  {path}")
    for path in summary.get("real_documents", []):
        print(f"    REAL  {path}")

    for skip in summary.get("skipped", []):
        print(f"    SKIPPED {skip['document']}: {skip['reason']}")

    print(f"  index written to  : {summary.get('index_path')}")
    print("=" * 58)

    if not summary["indexed_chunks"]:
        print("Nothing was indexed. Put documents in knowledge/demo/ or "
              "knowledge/company/ and run this again.")
        return 1

    status = knowledge_base_status()
    if status["demo_documents"] and not status["real_documents"]:
        print("NOTE: every indexed document is DEMO material. Answers drawn "
              "from it are labelled as demo policy and must not be relied on.")

    print("Done. The AI Assistant can now search these documents.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
