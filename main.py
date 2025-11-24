import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from jose import JWTError, jwt

import hashlib
import hmac
import requests

# ★ RAG チェーンを読み込み（src 配下は既存のまま利用）
from src.rag_chain import get_qa_chain  # RetrievalQA チェーン構築関数

# =========================
# 設定 (config)
# =========================

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama_rebva:11434")
DB_URL = os.environ.get("DB_URL", "sqlite:///./data/chat.db")

SECRET_KEY = os.environ.get("JWT_SECRET", "CHANGE_THIS_SECRET_KEY")
ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

security = HTTPBearer()

# SQLite engine
engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False},  # SQLite 用おまじない
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# =========================
# DB モデル
# =========================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="user")  # "admin" / "user" など


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)       # username を保存
    session_id = Column(String, index=True)
    role = Column(String)                      # "user" or "assistant"
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))


# 管理画面用 User 情報
class UserInfo(BaseModel):
    id: int
    username: str
    role: str

    class Config:
        from_attributes = True  # ORM モデルから変換

# =========================
# FastAPI 本体
# =========================

app = FastAPI()

# RAG チェーンをグローバルに一度だけ初期化
rag_qa = None  # LangChain RetrievalQA インスタンスを後からセット


# =========================
# アプリ起動時の初期化
# =========================

@app.on_event("startup")
def on_startup():
    """
    - DB のテーブル作成
    - デフォルト admin ユーザ作成
    - RAG チェーン (RetrievalQA) の初期化
    """
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # admin ユーザがいなければ作る
        existing = get_user_by_username(db, "admin")
        if existing is None:
            create_user(db, "admin", "password123", role="admin")
    finally:
        db.close()

    # ★ 起動時に一度だけ RAG チェーンを構築
    global rag_qa
    rag_qa = get_qa_chain()


# =========================
# DB セッション
# =========================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# パスワード関連（簡易版: SHA-256）
# =========================

def get_password_hash(password: str) -> str:
    """
    実運用なら bcrypt/argon2 を推奨。
    ここではデモ用に SECRET_KEY をソルト代わりに SHA-256。
    """
    data = (SECRET_KEY + password).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    data = (SECRET_KEY + plain_password).encode("utf-8")
    calc = hashlib.sha256(data).hexdigest()
    # timing attack 対策として compare_digest を使用
    return hmac.compare_digest(calc, hashed_password)


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def create_user(db: Session, username: str, password: str, role: str = "user") -> User:
    hashed_pw = get_password_hash(password)
    user = User(username=username, hashed_password=hashed_pw, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# =========================
# JWT 関連
# =========================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


# ユーザ作成用 Pydantic モデル
class RegisterRequest(BaseModel):
    username: str
    password: str


class RegisterResponse(BaseModel):
    username: str


# =========================
# チャット API 用モデル
# =========================

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


# 履歴参照用
class HistoryItem(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    created_at: datetime

    class Config:
        orm_mode = True


# =========================
# RAG チャット API 用モデル
# =========================

class RagChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


class RagSource(BaseModel):
    source: str
    snippet: str


class RagChatResponse(BaseModel):
    answer: str
    session_id: str
    sources: List[RagSource]


# =========================
# 認証依存関係 (JWT)
# =========================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Authorization: Bearer <token> を受け取ってユーザを特定。
    """
    token = credentials.credentials

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user = get_user_by_username(db, token_data.username)
    if user is None:
        raise credentials_exception
    return user


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    role='admin' のユーザだけを許可する dependency。
    それ以外は 403 Forbidden。
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


# =========================
# 管理系エンドポイント
# =========================

@app.get("/admin/users", response_model=List[UserInfo])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),  # admin のみ
):
    users = db.query(User).order_by(User.id).all()
    return users


# =========================
# /login エンドポイント
# =========================

@app.post("/login", response_model=Token)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, req.username, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": user.username,
        "role": user.role,
    }
    access_token = create_access_token(
        data=payload,
        expires_delta=access_token_expires,
    )
    return Token(access_token=access_token, token_type="bearer")


# =========================
# /register エンドポイント
# =========================

@app.post("/register", response_model=RegisterResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """
    新しいユーザを登録する API。
    """
    existing = get_user_by_username(db, req.username)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    create_user(db, req.username, req.password)
    return RegisterResponse(username=req.username)


# =========================
# 履歴の読み書き
# =========================

def load_history(db: Session, user_id: str, session_id: str) -> list[dict]:
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
    # シンプルにそのセッションの履歴を削除してから再挿入
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
# /chat エンドポイント (Ollama 直叩き, JWT 必須)
# =========================

@app.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user.username
    session_id = req.session_id or "default"

    # 1) 履歴取得
    history = load_history(db, user_id, session_id)

    # 2) Ollama に送る messages を作成
    messages = history + [{"role": "user", "content": req.message}]

    payload = {
        "model": "llama3",
        "messages": messages,
        "stream": False,  # 1つの JSON を返す
    }

    # 3) Ollama API 呼び出し
    resp = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    answer = data["message"]["content"]

    # 4) 履歴保存
    new_history = messages + [{"role": "assistant", "content": answer}]
    save_history(db, user_id, session_id, new_history)

    return ChatResponse(reply=answer, session_id=session_id)


# =========================
# /rag/chat エンドポイント (RAG + LangChain, JWT 必須)
# =========================

@app.post("/rag/chat", response_model=RagChatResponse)
def rag_chat(
    req: RagChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    LangChain RetrievalQA (RAG) を使った QA エンドポイント。
    """
    if rag_qa is None:
        # 起動時に初期化できていない場合
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG chain is not ready.",
        )

    user_id = current_user.username
    session_id = req.session_id or "1"

    # ★ LangChain 0.30 の RetrievalQA は "query" キーのみ受け付ける
    #   余計なキー (user_id, role など) を渡すとエラーになるため注意
    result = rag_qa.invoke({"query": req.question})

    answer: str = result.get("result", "") or ""
    source_docs = result.get("source_documents", []) or []

    # 会話履歴を保存（必要最低限）
    history_messages = [
        {"role": "user", "content": req.question},
        {"role": "assistant", "content": answer},
    ]
    save_history(db, user_id, session_id, history_messages)

    # ソース情報を整形
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


# =========================
# /history/search エンドポイント
# =========================

@app.get("/history/search", response_model=List[HistoryItem])
def search_history(
    q: str = Query(..., min_length=1, description="keyword to search"),
    session_id: Optional[str] = Query(None, description="filter by session_id"),
    limit: int = Query(50, ge=1, le=500, description="max results"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    ログインユーザ(current_user) の会話履歴をキーワード検索。
    """
    query = db.query(Conversation).filter(
        Conversation.user_id == current_user.username,
        Conversation.content.like(f"%{q}%"),
    )

    if session_id:
        query = query.filter(Conversation.session_id == session_id)

    rows = (
        query
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .limit(limit)
        .all()
    )

    return rows
