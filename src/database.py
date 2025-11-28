"""
DB 接続とセッション管理をまとめたモジュール。
FastAPI からは get_db 依存性を介してセッションを取得する。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import DB_URL

# SQLite でも他 DB でも動くように engine を一元管理
engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
)

# セッションファクトリ
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    FastAPI の Depends で呼び出し、使い終わったら自動で close する。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
