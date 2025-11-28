"""
RAG チャット用エンドポイント (/rag/chat)。
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.auth import get_current_user
from src.database import get_db
from src.models import RagChatRequest, RagChatResponse, RagSource, User
from src.utils.history_store import save_history
from src.rag_chain import get_qa_chain

logger = logging.getLogger("llm_api")
router = APIRouter(prefix="/rag", tags=["rag"])

rag_qa = None  # LangChain RetrievalQA を起動時にセット


def init_rag_chain():
    """アプリ起動時に一度だけ RAG チェーンを構築する。"""
    global rag_qa
    if rag_qa is None:
        rag_qa = get_qa_chain()
        logger.info("RAG chain initialized")


@router.post("/chat", response_model=RagChatResponse)
def rag_chat(
    req: RagChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    LangChain RetrievalQA (RAG) を使った QA エンドポイント。
    """
    if rag_qa is None:
        raise HTTPException(
            status_code=503,
            detail="RAG chain is not ready.",
        )

    user_id = current_user.username
    session_id = req.session_id or "1"

    # LangChain 0.30 の RetrievalQA は "query" キーのみ受け付ける
    result = rag_qa.invoke({"query": req.question})

    answer: str = result.get("result", "") or ""
    source_docs = result.get("source_documents", []) or []

    history_messages = [
        {"role": "user", "content": req.question},
        {"role": "assistant", "content": answer},
    ]
    save_history(db, user_id, session_id, history_messages)

    sources: List[RagSource] = []
    for doc in source_docs:
        meta = getattr(doc, "metadata", {}) or {}
        source_name = meta.get("source", "unknown")
        snippet = doc.page_content.replace("\n", " ")[:50]
        sources.append(RagSource(source=source_name, snippet=snippet))

    return RagChatResponse(
        answer=answer,
        session_id=session_id,
        sources=sources,
    )
