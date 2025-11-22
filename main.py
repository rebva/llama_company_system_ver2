import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, Header, HTTPException, status, Query
from pydantic import BaseModel
# 追加
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from jose import JWTError, jwt

import hashlib
import hmac

import requests


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
    connect_args={"check_same_thread": False},  # SQLite のおまじない
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()



# =========================
# DBモデル
# =========================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="user")  # role管理



class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)       # ここでは username を入れる
    session_id = Column(String, index=True)
    role = Column(String)                      # "user" or "assistant"
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))

#admin用API
class UserInfo(BaseModel):
    id: int
    username: str
    role: str

    class Config:
        from_attributes  = True

app = FastAPI()

# =========================
# FastAPI 本体
# =========================



#起動時のdefoult user = admin
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # すでに存在するかチェック
        existing = get_user_by_username(db, "admin")
        if existing is None:
            # ★ ここで admin ユーザとして作成
            create_user(db, "admin", "password123", role="admin")
    finally:
        db.close()



# =========================
# DB セッション取得
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
    # 実運用なら bcrypt / argon2 を使うべき。
    # ここではデモ用に「SECRET_KEY をソルト代わり」に SHA-256 を使う。
    data = (SECRET_KEY + password).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    data = (SECRET_KEY + plain_password).encode("utf-8")
    calc = hashlib.sha256(data).hexdigest()
    # タイミング攻撃対策用(compare_digest)
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
    
#　ユーザ作成モジュール用pydanicモデル
class RegisterRequest(BaseModel):
    username: str
    password: str


class RegisterResponse(BaseModel):
    username: str




# =========================
# チャットAPI用モデル
# =========================

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str

#chat history ref to db
class HistoryItem(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    created_at: datetime

    class Config:
        orm_mode = True


# =========================
# 認証依存関係 (JWT)
# =========================

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    Authorization: Bearer <token> を受け取る。
    /docs の「Authorize」ボタンからトークンだけ入れればOKになる。
    """
    token = credentials.credentials  # "Bearer " の後の部分だけ

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user = get_user_by_username(db, token_data.username)
    if user is None:
        raise credentials_exception
    return user



#role 管理
def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    role='admin' のユーザだけを許可する dependency。
    それ以外は 403 Forbidden を返す。
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",  # 権限が足りない
        )
    return current_user

#adminエンドポイントapp.getリクエストはdefの下

#dbの下にadmin
@app.get("/admin/users", response_model=list[UserInfo])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),  # ★ admin だけ
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
        "role": user.role,  # ★ role も入れる
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
    新しいユーザを登録するAPI。
    - すでに同じusernameがあれば 400 を返す。
    """
    # すでに存在するかチェック
    existing = get_user_by_username(db, req.username)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # ユーザ作成（パスワードは get_password_hash() でハッシュ化される）
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
    # シンプルに「そのセッションの履歴を一度削除してから全部入れ直す」
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
# /chat エンドポイント (JWT必須)
# =========================

@app.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current_user.username  # 会話テーブルには username を保存する
    session_id = req.session_id or "default"

    # 1) 履歴取得
    history = load_history(db, user_id, session_id)

    # 2) Ollama に投げる messages を作る
    messages = history + [
        {"role": "user", "content": req.message}
    ]

    payload = {
        "model": "llama3",
        "messages": messages,
        "stream": False,  # 1つのJSONだけ返すモード
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

    # 5) レスポンス
    return ChatResponse(reply=answer, session_id=session_id)

# ref to chat history from sqlite.db
# =========================
# /history/search エンドポイント
# =========================

@app.get("/history/search", response_model=list[HistoryItem])
def search_history(
    q: str = Query(..., min_length=1, description="keyword to search"),  # 検索キーワード
    session_id: Optional[str] = Query(None, description="filter by session_id"),  # 省略可
    limit: int = Query(50, ge=1, le=500, description="max results"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    ログインユーザ(current_user) の会話履歴をキーワード検索する。
    - デフォルト: 全セッションから検索
    - session_id を指定すると、そのセッションだけから検索
    """
    query = db.query(Conversation).filter(
        Conversation.user_id == current_user.username,
        Conversation.content.like(f"%{q}%"),
    )

    if session_id:
        query = query.filter(Conversation.session_id == session_id)

    # 新しい順で limit 件
    rows = (
        query
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .limit(limit)
        .all()
    )

    return rows