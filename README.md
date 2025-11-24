---

# マルチユーザー対応 LLM & RAG API

**FastAPI + SQLite + LangChain + Chroma + Ollama**

このリポジトリは **FastAPI** をベースにした、
**マルチユーザー対応（Multi-user）LLM / RAG（検索拡張生成）API サーバ** です。

目的は、社内利用できる **安全性の高い LLM システム**をシンプルに構築することです。

---

# 🚀 特徴（Features）

## 🔐 1. 認証・認可（Authentication & Authorization）

* **JWT 認証**（/login）
* **ユーザー登録**（/register）
* **role（user / admin）によるアクセス制御**
* 管理者専用エンドポイント：`/admin/users`

JWT のペイロードには以下が含まれます：

* `sub`: ユーザー名
* `role`: 権限（user / admin）
* `exp`: 有効期限

---

## 💬 2. マルチユーザー Chat API（/chat）

* Ollama の `/api/chat` を利用して LLM に問い合わせ
* 会話履歴は SQLite に保存
* `session_id` によりユーザーごとの複数セッションを保持
* **自分の履歴しか閲覧できない**安全設計

---

## 📚 3. RAG（検索拡張生成）API（/rag/chat）

* LangChain の `RetrievalQA` を使用した RAG パイプライン
* VectorDB は **Chroma**
* Embeddings は **HuggingFaceEmbeddings**（multilingual SBERT）
* Ollama LLM（例：llama3）
* 返却値には：

  * LLM の回答
  * モデルが参照したソース文書（source + snippet）

---

## 📖 4. 履歴検索 API（/history/search）

* キーワード検索により、自分のチャット履歴を検索
* `session_id` 指定でセッション単位の抽出も可能
* 最新順で返却

---

## 👑 5. 管理者向け機能（/admin/users）

* 登録済みユーザーの一覧表示（admin ロールのみアクセス可能）

---

# 🧱 技術スタック（Tech Stack）

| 分類          | 技術                      |
| ----------- | ----------------------- |
| 言語          | Python 3.11             |
| Web フレームワーク | FastAPI                 |
| 認証          | JWT（python-jose）        |
| データベース      | SQLite（SQLAlchemy）      |
| LLM         | Ollama                  |
| Embeddings  | HuggingFaceEmeddings    |
| RAG         | LangChain（RetrievalQA）  |
| VectorDB    | Chroma                  |
| コンテナ        | Docker / docker-compose |

---

# 📁 ディレクトリ構成（例）

```text
.
├── main.py                      # FastAPI エントリーポイント
├── requirements.txt             # 依存パッケージ
├── docker-compose.yaml          # Docker構成
├── .env                         # 環境変数
├── data/
│   └── chat.db                  # SQLite DB
├── chroma_db/                   # ChromaベクトルDB
└── src/
    ├── config.py                # 定数（モデル名 / DBパス）
    ├── rag_chain.py             # RAGチェーン定義
    ├── prepare_data.py          # Chroma作成スクリプト
    ├── loaders.py               # 文書読み込み
    ├── embeddings.py            # Embeddingモデル定義
    └── run_query.py             # RAG 単体テスト
```

---

# 🔧 環境変数（.env）

```env
HUGGINGFACEHUB_API_TOKEN=your_token_here

# Ollama ホスト（docker-compose に合わせる）
OLLAMA_HOST=http://ollama_rebva:11434

# LLM モデル名
OLLAMA_MODEL=llama3

# JWT 設定
JWT_SECRET=CHANGE_THIS_SECRET_KEY
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# SQLite のパス（デフォルト）
DB_URL=sqlite:///./data/chat.db
```

---

# ⚙️ セットアップ（Setup）

## 1. リポジトリのクローン

```bash
git clone https://github.com/yourname/your-repo.git
cd your-repo
```

---

## 2. Python 仮想環境（任意）

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 3. `.env` を作成

```bash
cp .env.example .env
```

自分の環境に合わせて編集してください。

---

## 4. Ollama の起動とモデル準備

```bash
ollama pull llama3
ollama serve
```

接続確認：

```bash
curl http://localhost:11434/api/tags
```

---

## 5. ドキュメントの埋め込み（ChromaDB 構築）

```bash
python -m src.prepare_data
```

---

## 6. FastAPI の起動

### A. 手動（ローカル）

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### B. Docker Compose

```bash
docker compose up --build
```

Swagger UI：

```
http://localhost:8000/docs
```

---

# 🔗 API 一覧と curl サンプル

## ■ 1. ユーザー登録 `/register`

```bash
curl -X POST "http://localhost:8000/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"user1","password":"pass1"}'
```

---

## ■ 2. ログイン `/login`

```bash
TOKEN=$(
  curl -s -X POST "http://localhost:8000/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"user1","password":"pass1"}' | jq -r '.access_token'
)
echo $TOKEN
```

---

## ■ 3. 管理者ユーザー一覧 `/admin/users`

```bash
curl -X GET "http://localhost:8000/admin/users" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## ■ 4. チャット `/chat`

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello","session_id":"session-1"}'
```

---

## ■ 5. RAG チャット `/rag/chat`

```bash
curl -X POST "http://localhost:8000/rag/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"このRAGについて説明して","session_id":"rag1"}'
```

---

## ■ 6. 履歴検索 `/history/search`

```bash
curl -G "http://localhost:8000/history/search" \
  -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "q=Hello" \
  --data-urlencode "session_id=session-1"
```

---

# 🔒 セキュリティ注意点（Security Notes）

* パスワードは SHA-256 + SECRET を使用（本番は bcrypt/argon2 推奨）
* JWT Secret は強力なランダム文字列を使用
* EXPOSE している場合は HTTPS と Reverse Proxy（Nginx）を推奨
* RAG データは「信頼できる文書」のみに限定

---
