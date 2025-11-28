"""
FastAPI エントリーポイント。
- main.py は「旅館の女将」役として各 router を案内するだけに絞る。
"""
import logging

from fastapi import FastAPI

from src.auth import create_user, get_user_by_username
from src.database import engine, SessionLocal
from src.models import Base
from src.routers import admin_router, auth_router, chat_router, rag_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("llm_api")

app = FastAPI()

# ルータを登録（エンドポイントの実体は src/routers 配下）
app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(chat_router.router)
app.include_router(rag_router.router)


@app.on_event("startup")
def on_startup():
    """
    アプリ起動時の初期化。
    - DB テーブル作成
    - デフォルト admin ユーザ作成
    - RAG チェーン初期化
    """
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing = get_user_by_username(db, "admin")
        if existing is None:
            create_user(db, "admin", "password123", role="admin")
            logger.info("default admin user created")
    finally:
        db.close()

    rag_router.init_rag_chain()
