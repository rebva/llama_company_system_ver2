"""
FastAPI エントリーポイント。
- main.py は「旅館の女将」役として各 router を案内するだけに絞る。
- main.py は「旅館の女将」役として各 router を案内するだけに絞る。
"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # CORS
from fastapi.responses import HTMLResponse          # HTML を返す
from fastapi.staticfiles import StaticFiles         # static ファイル

from src.auth import create_user, get_user_by_username
from src.database import engine, SessionLocal
from src.models import Base
from src.routers import admin_router, auth_router, chat_router, rag_router
from src.routers import sql_safe_router, agent_sql_router
from src.routers import sql_safe_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("llm_api")

# ==== FastAPI アプリ本体 ====
app = FastAPI()

# ==== CORS 全開放（フロントから直接叩きたいので） ====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://sawachi2:8080"],      # 本番ならドメインを絞るのが推奨
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==== index.html / static のパス設定 ====
BASE_DIR = Path(__file__).resolve().parent
INDEX_PATH = BASE_DIR / "index.html"
STATIC_DIR = BASE_DIR / "static"

# static ディレクトリがあれば /static にマウント
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ==== ルートで UI を返す ====
@app.get("/", response_class=HTMLResponse)
async def root():
    """
    ルートにアクセスされたら index.html をそのまま返す。
    なければ簡易メッセージ。
    """
    if INDEX_PATH.exists():
        return INDEX_PATH.read_text(encoding="utf-8")
    return "<h1>index.html not found</h1>"


# ==== ルータ登録（API エンドポイント） ====
app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(chat_router.router)
app.include_router(rag_router.router)
app.include_router(sql_safe_router.router)
app.include_router(agent_sql_router.router)


@app.on_event("startup")
def on_startup():
    """
    アプリ起動時の初期化。
    - DB テーブル作成
    - デフォルト admin ユーザ作成
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
