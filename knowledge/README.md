# SmartHR knowledge base (RAG source documents)

Everything the AI Assistant can quote from lives here. It is indexed by
`app/rag/`, which turns these files into searchable chunks.

```
knowledge/
  demo/      DEMO documents. Invented for development and testing.
  company/   Real company documents. Empty until you add them.
```

## The two folders mean different things

**`demo/`** holds documents written to build and test the retrieval pipeline.
They are **not real policy**. Every one of them is titled "DEMO SmartHR HR
Policy", every chunk indexed from this folder is flagged `is_demo: true`, and
the assistant says "Demo" when it cites them. Nobody should act on them.

**`company/`** holds your organisation's actual documents. It is empty on
purpose - no real policy exists yet, and inventing one would be worse than
having none.

The folder a file sits in is what marks it, so a document cannot be mislabelled
by forgetting a header. Moving a file from `demo/` to `company/` changes how it
is reported, with no code change.

## Adding real documents later

1. Put the files in `knowledge/company/` (`.md`, `.txt`, `.pdf` or `.docx`).
2. Delete the files in `knowledge/demo/`, or leave them - real documents are
   ranked and cited separately either way.
3. Re-index:

   ```powershell
   venv\Scripts\python.exe -m app.rag.ingest
   ```

That is the whole procedure. No code, schema or configuration changes.
