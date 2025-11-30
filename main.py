"""
FastAPI エントリーポイント。
- main.py は「司令塔」として各 router を呼び出し、起動時の初期化も担当。
"""
import logging
<<<<<<< HEAD
from pathlib import Path

=======
 
>>>>>>> 153f32bf5a54fab46b04cdcf4ee5a3a1965abbd8
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.auth import create_user, get_user_by_username
from src.database import engine, SessionLocal
from src.models import Base
from src.routers import admin_router, auth_router, chat_router, rag_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("llm_api")

BASE_DIR = Path(__file__).resolve().parent
INDEX_PATH = BASE_DIR / "index.html"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI()

# CORS: ローカルの index.html から直接叩けるように全許可
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静的ファイル (存在する場合のみマウント)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ルートで index.html を返す簡易フロント
@app.get("/")
def serve_index():
    if INDEX_PATH.exists():
        return FileResponse(INDEX_PATH)
    return {"message": "LLM API"}

# ルーター登録 (エンドポイント郡は src/routers 配下)
app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(chat_router.router)
app.include_router(rag_router.router)


@app.on_event("startup")
def on_startup():
    """
    アプリ起動時の初期化。
    - DB テーブル作成
    - デフォルト admin ユーザー作成
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
