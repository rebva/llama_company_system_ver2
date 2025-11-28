# LLM API (マルチユーザー対応) をやさしく説明する README

FastAPI で動く「社内向け LLM / RAG API サーバ」です。ユーザー認証・履歴保存・RAG（検索拡張生成）がそろっていて、Docker でもローカル Python でもすぐ動かせます。初心者が全体像をつかみやすいように、仕組みと使い方を順番にまとめます。

---

## 1. これが何をしてくれるか
- マルチユーザー：JWT でログインし、ユーザーごとに履歴を分ける
- Chat API：LLM に質問。会話は SQLite に保存され、後でキーワード検索できる
- RAG API：自分のドキュメントを Chroma に埋め込んで検索し、参照元を返す
- 管理機能：管理者だけがユーザー一覧を確認できる
- コンテナ対応：`docker compose up` で API を起動（外部 vLLM/Ollama に接続）

---

## 2. ざっくりアーキテクチャ
- FastAPI (`main.py`) がエントリーポイント。起動時に DB 初期化とデフォルト admin ユーザー作成。
- 認証：`src/auth.py` で JWT 発行/検証。`/login` で発行、`/register` でユーザー追加。
- データベース：`src/database.py` で SQLite を利用。会話は `conversations` テーブルに保存。
- LLM：`src/utils/llm_backend.py` が OpenAI 互換の vLLM/Ollama エンドポイントへ投げる。
- RAG：`src/rag_chain.py` で LangChain RetrievalQA を構築。Chroma (ベクトル検索) + BM25 (全文検索) のハイブリッド。
- ルーター：`src/routers/` にエンドポイントを分離（auth / chat / rag / admin）。

---

## 3. API の動き
- `/register`：ユーザー新規登録。
- `/login`：JWT を発行（レスポンス `access_token` を以後の Authorization に使う）。
- `/chat`：  
  - URL だけ送る → ページを取得して要約だけ返す（LLM 不使用）。  
  - URL + 質問 or URL なし → 過去の履歴を付けて LLM へ投げる。  
  - 履歴はユーザー/セッションごとに SQLite に保存。
- `/history/search`：自分の履歴をキーワード検索（セッション ID で絞り込み可）。
- `/rag/chat`：埋め込んだ自前データを検索し、回答と参照元スニペットを返す。
- `/admin/users`：管理者だけがユーザー一覧を確認。

---

## 4. ディレクトリの見どころ
- `main.py`：FastAPI 起動とルーター登録。
- `src/routers/`：各エンドポイントの実装。`chat_router.py` や `rag_router.py` を見れば挙動がわかる。
- `src/auth.py`：認証・認可（JWT、パスワードハッシュ、admin チェック）。
- `src/models.py`：SQLAlchemy モデルと Pydantic スキーマがまとまっている。
- `src/utils/`：LLM 呼び出し、履歴保存、URL 取得などの補助。
- `src/rag_chain.py`：LangChain の RetrievalQA を組み立てる場所。Chroma DB を読み込み。
- `src/prepare_data.py`：RAG 用のベクトルデータを事前生成するスクリプト。
- `docker-compose.yaml` / `Dockerfile`：API を 8080 ポートで公開するコンテナ設定。

---

## 5. 事前に知っておくこと
- Python 3.10 以上推奨。
- LLM バックエンドは OpenAI 互換の HTTP エンドポイントに投げます（例：vLLM、Ollama の OpenAI モード）。
- 初回起動で `admin / password123` の管理ユーザーが自動作成されます。実運用ではすぐ変更してください。
- パスワードハッシュはデモ用（SHA-256 + SECRET）。本番は bcrypt/argon2 への置き換え推奨。

---

## 6. 環境変数（主なもの）
`.env` を置くか、コンテナ環境変数で指定します。デフォルト値は `src/config.py` 参照。

| 変数 | 役割 | 例 |
| --- | --- | --- |
| `VLLM_BASE_URL` | OpenAI 互換エンドポイント | `http://vllm:8010/v1` |
| `OLLAMA_MODEL` | 利用するモデル名 | `Qwen/Qwen2-0.5B-Instruct` |
| `DB_URL` | DB パス | `sqlite:///./data/chat.db` |
| `JWT_SECRET` | JWT 署名キー | `CHANGE_THIS_SECRET_KEY` |
| `JWT_ALGORITHM` | JWT アルゴリズム | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | トークン有効期限 | `43200` (30日) |
| `HUGGINGFACEHUB_API_TOKEN` | 埋め込みモデル用 | `<your_token>` |

---

## 7. 動かし方（2パターン）

### A. Docker Compose で簡単起動
```bash
docker compose up --build
```
- API: http://localhost:8080
- vLLM などの LLM バックエンドは別途立ち上げておくこと（compose の `VLLM_BASE_URL` を合わせる）。

### B. ローカル Python で起動
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export VLLM_BASE_URL=http://localhost:8010/v1  # 自分の環境に合わせる
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
- API: http://localhost:8000

---

## 8. RAG データを用意する手順
1. `rag_data/` に PDF / Word / Excel / PPT / テキストなどを置く。
2. 埋め込みを生成して ChromaDB を作成:
   ```bash
   python -m src.prepare_data
   ```
3. `chroma_db/` に永続化される。LangChain は起動時にここを読む。
4. 任意で BM25 検索も使いたい場合は `chroma_db/bm25_documents.json` を置くとハイブリッド検索が有効になる。

---

## 9. すぐ試せる API サンプル
`BASE` は `http://localhost:8080`（ローカル起動なら 8000）。

### 1) ユーザー登録
```bash
curl -X POST "$BASE/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"user1","password":"pass1"}'
```

### 2) ログインしてトークン取得
```bash
TOKEN=$(curl -s -X POST "$BASE/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"user1","password":"pass1"}' | jq -r '.access_token')
echo $TOKEN
```

### 3) チャット
```bash
curl -X POST "$BASE/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"こんにちは","session_id":"demo"}'
```

### 4) RAG チャット
```bash
curl -X POST "$BASE/rag/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"社内規程のポイントは？","session_id":"rag1"}'
```

### 5) 履歴検索
```bash
curl -G "$BASE/history/search" \
  -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "q=こんにちは" \
  --data-urlencode "session_id=demo"
```

### 6) 管理者でユーザー一覧
```bash
ADMIN_TOKEN=... # admin でログインして取得
curl "$BASE/admin/users" -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## 10. 実運用で気をつけること
- JWT シークレットは必ず強固な値に変える。
- パスワードハッシュを bcrypt/argon2 に置き換える（デフォルトはデモ向け）。
- HTTPS とリバースプロキシ (Nginx など) を挟む。
- RAG に入れる文書は信頼できるものだけにし、権限管理を考慮する。
- 管理者の初期パスワード `password123` はすぐ変更する。

---

これで全体像と初期セットアップを押さえられます。コードを追うときは `main.py` → `src/routers/` → `src/utils/` の順に見ると理解しやすいです。
