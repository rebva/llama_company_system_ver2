"""
会話履歴の読み書きユーティリティ。
"""
from datetime import datetime, timezone
from typing import List, Dict

from sqlalchemy.orm import Session

from src.models import Conversation


def load_history(db: Session, user_id: str, session_id: str) -> List[Dict]:
    """指定ユーザー・セッションの履歴を古い順で返す。"""
    rows = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == user_id,
            Conversation.session_id == session_id,
        )
        .order_by(Conversation.created_at.asc(), Conversation.id.asc())
        .all()
    )
    return [{"role": r.role, "content": r.content} for r in rows]


def save_history(db: Session, user_id: str, session_id: str, messages: List[Dict]) -> None:
    """セッション単位で履歴を上書き保存する。"""
    db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.session_id == session_id,
    ).delete()

    now = datetime.now(timezone.utc)

    for msg in messages:
        db.add(
            Conversation(
                user_id=user_id,
                session_id=session_id,
                role=msg["role"],
                content=msg["content"],
                created_at=now,
            )
        )

    db.commit()
