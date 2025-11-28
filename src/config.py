"""
集中管理された設定値。
- 既存の RAG 用設定を維持しつつ、API 全体で使う環境変数もここに集約する。
"""
from dotenv import load_dotenv
import os

# .env を読み込んで環境変数を事前にセット
load_dotenv()

# ===== RAG 用設定（既存） =====
# LLMモデル名（環境変数 OLLAMA_MODEL 優先、なければデフォルトで Qwen）
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "Qwen/Qwen2-0.5B-Instruct")
# Windows環境でOllamaのnamed pipeソケットパス
OLLAMA_SOCKET = r"\\.\pipe\ollama.sock"
# ドキュメント格納フォルダパス
DATA_FOLDER = "./rag_data"
# ChromaDBの永続ストアパス
CHROMA_DB_PATH = "./chroma_db"
# Hugging Face Hub 用トークン（環境変数を優先）
HUGGINGFACEHUB_API_TOKEN = os.getenv("HUGGINGFACEHUB_API_TOKEN")
os.environ["HUGGINGFACEHUB_API_TOKEN"] = HUGGINGFACEHUB_API_TOKEN or ""

# ===== API 共通設定（新規追加） =====
# LLM バックエンド（vLLM/Ollama など）エンドポイント
# OpenAI 互換のベース URL（デフォルトで /v1 を含める）
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://vllm:8010/v1")
# データベース URL（デフォルトは SQLite）
DB_URL = os.getenv("DB_URL", "sqlite:///./data/chat.db")
# JWT 設定
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_THIS_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# HTTP リクエスト共通ヘッダ（スクレイピング用）
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
