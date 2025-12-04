"""
LLM から呼び出す READ ONLY の SQL ツール群。
- 会話履歴の取得・検索のみを提供し、書き込みは行わない。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.database import SessionLocal
from src.models import Conversation

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _clamp_limit(limit: Optional[int]) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(int(limit), MAX_LIMIT))


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    # Allow trailing Z by normalizing to +00:00
    normalized = value.rstrip("Z") + ("+00:00" if value.endswith("Z") else "")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid datetime format: {value}") from exc


def _rows_to_dicts(rows: List[Conversation]) -> List[Dict[str, Any]]:
    return [
        {
            "id": row.id,
            "session_id": row.session_id,
            "role": row.role,
            "content": row.content,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def _run_readonly_query(query_fn):
    db: Session = SessionLocal()
    try:
        return query_fn(db)
    finally:
        db.close()


def fetch_user_conversations(
    *,
    user_id: str,
    session_id: Optional[str] = None,
    from_datetime: Optional[str] = None,
    to_datetime: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> Any:
    """
    指定ユーザーの会話履歴を取得（READ ONLY）。
    """

    def _query(db: Session):
        try:
            start_dt = _parse_datetime(from_datetime)
            end_dt = _parse_datetime(to_datetime)
        except ValueError as exc:
            return {"error": str(exc)}

        q = db.query(Conversation).filter(Conversation.user_id == user_id)

        if session_id:
            q = q.filter(Conversation.session_id == session_id)
        if start_dt:
            q = q.filter(Conversation.created_at >= start_dt)
        if end_dt:
            q = q.filter(Conversation.created_at <= end_dt)

        rows = (
            q.order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .limit(_clamp_limit(limit))
            .all()
        )
        return _rows_to_dicts(rows)

    return _run_readonly_query(_query)


def search_user_conversations(
    *,
    user_id: str,
    keyword: str,
    session_id: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> Any:
    """
    キーワード全文検索（LIKE）で会話履歴を取得。
    """

    def _query(db: Session):
        if not keyword:
            return {"error": "keyword is required"}

        q = db.query(Conversation).filter(
            Conversation.user_id == user_id,
            Conversation.content.like(f"%{keyword}%"),
        )

        if session_id:
            q = q.filter(Conversation.session_id == session_id)

        rows = (
            q.order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .limit(_clamp_limit(limit))
            .all()
        )
        return _rows_to_dicts(rows)

    return _run_readonly_query(_query)
