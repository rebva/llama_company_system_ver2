"""
チャット系エンドポイント (/chat, /history/search) を担当する router。
"""
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.auth import get_current_user
from src.database import get_db
from src.models import ChatRequest, ChatResponse, HistoryItem, User
from src.utils.history_store import load_history, save_history
from src.utils.llm_backend import call_llm_backend
from src.utils.url_tools import extract_url_and_rest
from src.utils.web_fetch import fetch_url_and_summarize

logger = logging.getLogger("llm_api")
router = APIRouter(tags=["chat"])

# セッション開始時に注入する system メッセージ
BASE_SYSTEM_PROMPT = """
You are a security engineer.
- When the user sends a URL in this session, you MUST remember the page content.
- If the user later asks vague or follow-up questions without a new URL,
you MUST assume they are asking about the last URL and previous discussion.
- Answer in simple Japanese, but keep technical depth.
"""


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    - URL だけ: LLM を使わずページ要約を返す
    - URL + 質問 or URLなし: 既存履歴を保持したまま LLM に渡す
    """
    user_id = current_user.username
    session_id = req.session_id or "default"

    history: list[dict]
    if session_id == "garak-chat-session":
        history = []
    else:
        history = load_history(db, user_id, session_id)

    # DB に system が残っていないセッションでも、必ず先頭に付与する
    if not any(msg.get("role") == "system" for msg in history):
        history = [{"role": "system", "content": BASE_SYSTEM_PROMPT}] + history

    url, tail_text = extract_url_and_rest(req.message)

    summary: Optional[str] = None
    summary_text: Optional[str] = None

    if url:
        try:
            summary = fetch_url_and_summarize(url, max_chars=1200)
            summary_text = f"URL: {url}\n\n{summary}"
        except Exception as e:
            logger.warning("failed to fetch url %s: %s", url, e)
            if not tail_text:
                return ChatResponse(
                    reply=(
                        "指定されたURLにアクセスできませんでした。\n"
                        f"URL: {url}\n"
                        f"error: {e}"
                    ),
                    session_id=session_id,
                )
            summary_text = f"URL: {url}\n\n[Error] Failed to fetch this URL: {e}"

    # 1) URL だけ or ほぼ URL だけ → LLM を使わずサマリだけ返す
    if url and not tail_text:
        if session_id != "garak-chat-session":
            messages = history + [
                {"role": "user", "content": req.message},
                {"role": "assistant", "content": summary or ""},
            ]
            save_history(db, user_id, session_id, messages)

        return ChatResponse(reply=summary or "", session_id=session_id)

    # 2) URL + 質問 or URLなし → 従来通り LLM に投げる
    if url and tail_text:
        page_system = {
            "role": "system",
            "content": (
                "The user sent a URL and a question.\n"
                "Use the following page summary to answer the user's question.\n\n"
                "=== Page Summary ===\n"
                + (summary_text or "")
            ),
        }
        messages = history + [page_system] + [
            {"role": "user", "content": tail_text}
        ]
    else:
        messages = history + [
            {"role": "user", "content": req.message}
        ]

    # デバッグ用: LLM に渡す履歴を短くして記録する
    if logger.isEnabledFor(logging.INFO):
        preview = []
        for m in messages:
            content = m.get("content") or ""
            preview.append(
                {
                    "role": m.get("role"),
                    "content": content[:200] + ("..." if len(content) > 200 else ""),
                }
            )
        logger.info("LLM input user=%s session=%s messages=%s", user_id, session_id, preview)

    answer = call_llm_backend(messages)

    if session_id != "garak-chat-session":
        new_history = messages + [{"role": "assistant", "content": answer}]
        save_history(db, user_id, session_id, new_history)

    return ChatResponse(reply=answer, session_id=session_id)


@router.get("/history/search", response_model=List[HistoryItem])
def search_history(
    q: Optional[str] = Query(
        None,
        description="keyword to search; omitted to fetch latest",
    ),
    session_id: Optional[str] = Query(None, description="filter by session_id"),
    limit: int = Query(50, ge=1, le=500, description="max results"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ログインユーザ(current_user) の会話履歴をキーワード検索。"""
    from src.models import Conversation  # 遅延インポートで循環を避ける

    keyword = q.strip() if q else None

    query = db.query(Conversation).filter(
        Conversation.user_id == current_user.username,

    )

    # キーワード指定時は「キーワードにヒットしたセッションの全メッセージ」を返す
    # （ユーザ発話にだけ含まれるキーワードでも、返信もセットで取得するため）
    if keyword:
        session_filter = db.query(Conversation.session_id).filter(
            Conversation.user_id == current_user.username,
            Conversation.content.like(f"%{keyword}%"),
        )
        if session_id:
            session_filter = session_filter.filter(Conversation.session_id == session_id)

        query = query.filter(Conversation.session_id.in_(session_filter))
    elif session_id:
        query = query.filter(Conversation.session_id == session_id)

    rows = (
        query
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .limit(limit)
        .all()
    )

    return rows
