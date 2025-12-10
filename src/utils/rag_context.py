"""
Lightweight helper to fetch context from the existing RAG chain.
Used to give the shell agent concrete knowledge before it plans commands.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import List, Tuple

from src.models import RagSource
from src.rag_chain import get_qa_chain

logger = logging.getLogger("llm_api")


@lru_cache(maxsize=1)
def _get_rag_chain():
    """
    Prefer the globally initialized RAG chain if the router has bootstrapped it;
    otherwise lazily build our own.
    """
    try:
        from src.routers import rag_router

        if getattr(rag_router, "rag_qa", None) is not None:
            return rag_router.rag_qa
    except Exception as e:  # pragma: no cover - best effort fallback
        logger.debug("Could not reuse rag_router chain: %s", e)

    return get_qa_chain()


def fetch_rag_context(
    query: str,
    max_chars: int = 1200,
    max_docs: int = 3,
) -> Tuple[str, List[RagSource]]:
    """
    Run a RAG lookup for the given query and return a compact context string
    plus source metadata for transparency.
    """
    try:
        chain = _get_rag_chain()
        result = chain.invoke({"query": query})
    except Exception as e:
        logger.warning("RAG lookup failed: %s", e)
        return "", []

    docs = (result.get("source_documents") or [])[:max_docs]

    context_chunks: List[str] = []
    sources: List[RagSource] = []

    for doc in docs:
        text = (getattr(doc, "page_content", "") or "").replace("\n", " ").strip()
        if text:
            context_chunks.append(text)

        meta = getattr(doc, "metadata", {}) or {}
        source_name = meta.get("source", "unknown")
        sources.append(RagSource(source=source_name, snippet=text[:80]))

    if not context_chunks and result.get("result"):
        # Use the model's direct answer if no documents were present.
        context_chunks.append(str(result["result"]))

    combined = "\n---\n".join(context_chunks)
    if len(combined) > max_chars:
        combined = combined[:max_chars]

    return combined, sources
