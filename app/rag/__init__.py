"""Retrieval-Augmented Generation over SmartHR's HR documents.

    knowledge/*.md|txt|pdf|docx
        -> service.ingest_knowledge_base()
             -> chunking.chunk_text()      split into passages
             -> embeddings.embed()         passages -> vectors
             -> store.VectorStore          saved to rag_index/index.json

    a question
        -> service.search_policies()
             -> embeddings.embed()         question -> vector
             -> store.search()             cosine similarity, top matches
             -> the passages, with citations

This package sits outside `app/routers/` for the same reason `app/audit.py`,
`app/identity.py` and `app/mcp/` do: it is called by several places, so its
dependencies must point one way. It knows nothing about HTTP, FastAPI or MCP.

It is reached through the `search_hr_policies` MCP tool, so the assistant
retrieves documents the same way it reads live data - by calling a tool. RAG
does not replace MCP here; it is another tool behind it.
"""
