"""
SQLAlchemy モデルと Pydantic スキーマをここに集約。
DB 構造と入出力の型が一箇所で確認できるようにする。
"""
from datetime import datetime, timezone
from typing import Optional, List, Literal

from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base

# SQLAlchemy Base（テーブル定義の土台）
Base = declarative_base()


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


# ===== Pydantic スキーマ =====

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class RegisterResponse(BaseModel):
    username: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class UserInfo(BaseModel):
    id: int
    username: str
    role: str

    class Config:
        from_attributes = True  # ORM モデルから変換


class HistoryItem(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


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


class OpenAIChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class OpenAIChatRequest(BaseModel):
    model: Optional[str] = None
    messages: List[OpenAIChatMessage]
    mode: Optional[str] = None  # extra option for our system


class OpenAIChatChoice(BaseModel):
    index: int
    message: OpenAIChatMessage
    finish_reason: Literal["stop", "length"] = "stop"


class OpenAIChatUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class OpenAIChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[OpenAIChatChoice]
    usage: OpenAIChatUsage
