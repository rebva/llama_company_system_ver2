import os
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, Header, HTTPException
from pydantic import BaseModel

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session

import requests

# =========================
# 設定 (config 設定)
# =========================

API_KEY = os.environ.get("API_KEY", "CHANGE_ME")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama_rebva:11434")
DB_URL = os.environ.get("DB_URL", "sqlite:///./data/chat.db")

# SQLite 用のエンジン(engine データベース接続)
engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False},  # SQLite のおまじない
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# =========================
# DBモデル (model = テーブル定義)
# =========================

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    session_id = Column(String, index=True)
    role = Column(String, index=False)      # "user" or "assistant"
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))


# =========================
# FastAPI 本体
# =========================

app = FastAPI()


# 起動時にテーブル作成
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


# DB セッションを取得する依存関係(dependency 依存関係)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# 認証 (very simple API key)
# =========================

async def get_current_user(
    x_api_key: str = Header(..., alias="X-API-Key"),
    x_user_id: str = Header(..., alias="X-User-Id"),
):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"user_id": x_user_id}


# =========================
# リクエスト/レスポンスの型
# =========================

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


# =========================
# 履歴の読み書き
# =========================

def load_history(db: Session, user_id: str, session_id: str) -> list[dict]:
    """指定ユーザ＋セッションの履歴をすべて取得する。"""
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


def save_history(db: Session, user_id: str, session_id: str, messages: list[dict]) -> None:
    """そのセッションの履歴を全部入れ替える（シンプル実装）。"""
    # まず既存の履歴を削除
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


# =========================
# /chat エンドポイント
# =========================

@app.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = user["user_id"]
    session_id = req.session_id or "default"

    # 1) 履歴をDBから取得
    history = load_history(db, user_id, session_id)

    # 2) Ollama に投げるメッセージを作成
    messages = history + [
        {"role": "user", "content": req.message}
    ]

    payload = {
        "model": "llama3",
        "messages": messages,
        "stream": False,   # ★ ストリームOFF（1個のJSONだけ返す）
    }

    resp = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()

    # デバッグ用に中身を見たいときはこれを一時的に付けてもOK
    # print(resp.text)

    data = resp.json()
    answer = data["message"]["content"]


    # 4) 新しい履歴（user + assistant）をDBに保存
    new_history = messages + [{"role": "assistant", "content": answer}]
    save_history(db, user_id, session_id, new_history)

    # 5) クライアントへ返す
    return ChatResponse(reply=answer, session_id=session_id)
