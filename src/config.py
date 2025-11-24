import os  # os を利用して環境変数読み込み
# 共通設定
# LLMモデル名を指定
OLLAMA_MODEL   = "hf.co/elyza/Llama-3-ELYZA-JP-8B-GGUF"
# Windows環境でOllamaのnamed pipeソケットパス
OLLAMA_SOCKET  = r"\\.\pipe\ollama.sock"
# ドキュメント格納フォルダパス
DATA_FOLDER    = "./rag_data"
# ChromaDBの永続ストアパス
CHROMA_DB_PATH = "./chroma_db"
# Hugging Face Hub 用トークン
# 環境変数 HUGGINGFACEHUB_API_TOKEN を優先して利用
HUGGINGFACEHUB_API_TOKEN = os.getenv(
  "HUGGINGFACEHUB_API_TOKEN",
  "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"
)
# モジュール読み込み時に必ず環境変数にも登録
os.environ["HUGGINGFACEHUB_API_TOKEN"] = HUGGINGFACEHUB_API_TOKEN
