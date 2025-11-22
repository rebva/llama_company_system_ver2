````markdown
# 🔐 Multi-User LLM API System  
FastAPI + JWT + RBAC + SQLite + Ollama Chat API

このプロジェクトは **ローカル LLM（Ollama）をマルチユーザー化**し、  
**JWT 認証・RBAC（ロールベースアクセス制御）・会話履歴管理・検索 API** を備えた  
**セキュアな LLM API サーバー** の実装です。

認証・認可・履歴管理がそろっているため、  
「社内向け LLM」「チーム内チャット AI」「業務支援ボット」などにそのまま使えます。

---

## 🚀 Features（機能）

### 🔑 1. ユーザー認証（JWT）
- `/register` でユーザー作成  
- `/login` で JWT アクセストークン発行  
- FastAPI 依存関係で `get_current_user` により JWT 検証  
- Token Payload:
  ```json
  {
    "sub": "username",
    "role": "admin or user",
    "exp": "expire timestamp"
  }
````

### 🛡 2. RBAC（Role-Based Access Control）

* 管理者だけアクセスできる API `/admin/users`
* 通常ユーザーはアクセス不可 → **403 Forbidden**

### 💬 3. 会話履歴の永続化（SQLite）

* SQLite `data/chat.db` に永続保存
* 会話は `session_id` ごとに区別して保存
* 再起動しても履歴が残る

### 🔎 4. 会話検索 API（キーワード検索）

* `/history/search?keyword=hello`
* 自分の会話のみ検索可能（ユーザー隔離）

### 📂 5. セッション管理 API

* `/sessions` — すべての会話セッション一覧
* `/history/by-session?session_id=<id>` — セッション単位で過去ログ閲覧

### 🤖 6. Ollama Chat 連携

* `/chat` で Ollama コンテナへ LLM クエリ
* 会話履歴をコンテキストとして送信
* Llama3 などユーザー環境のモデルに対応

---

---

## 🏗 System Architecture（システム構成）

```
+-------------------------------------------+
|                 Client                    |
|        (curl / app / frontend)            |
+------------------------+------------------+
                         |
                         v
+--------------------------------------------------------+
|                     FastAPI Server                     |
|                                                        |
|  - /register  → User create                            |
|  - /login     → JWT issue                              |
|  - /chat      → Chat with LLM                          |
|  - /sessions  → Session list                           |
|  - /history   → History & search                       |
|                                                        |
|  Auth: JWT + RBAC                                      |
|  DB: SQLite (chat.db)                                  |
+------------------------+-------------------------------+
                         |
                         v
+--------------------------------------------------------+
|                       Ollama                           |
|       (local LLM model e.g., llama3 / mistral)         |
+--------------------------------------------------------+
```

---

## 📦 Directory Structure

```
.
├── Dockerfile
├── docker-compose.yaml
├── main.py              # FastAPI server
├── requirements.txt
└── data/
    └── chat.db          # SQLite database (auto-generated)
```

---

## 🔧 Installation

### 1. Clone repository

```bash
git clone https://github.com/yourname/llmapi.git
cd llmapi
```

### 2. Start with docker compose

```bash
docker compose build
docker compose up -d
```

### 3. Check containers

```bash
docker compose ps
```

例：

```
llm_api       running 0.0.0.0:8080->8080/tcp
ollama        running 11434/tcp
```

---

## 🧪 API Usage Examples

ここでは **curl** を使った動作確認例をまとめます。

---

### 🔐 Register User

```bash
curl -X POST http://localhost:8080/register \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "password": "pass1"}'
```

---

### 🔑 Login (Get JWT Token)

```bash
TOKEN=$(curl -s -X POST http://localhost:8080/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user1","password":"pass1"}' | jq -r '.access_token')
```

---

### 🤖 Chat with LLM

```bash
curl -X POST http://localhost:8080/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello LLM","session_id":"test1"}'
```

---

### 📂 List Sessions

```bash
curl -X GET http://localhost:8080/sessions \
  -H "Authorization: Bearer $TOKEN"
```

---

### 📝 Get History by Session

```bash
curl -X GET \
  "http://localhost:8080/history/by-session?session_id=test1" \
  -H "Authorization: Bearer $TOKEN"
```

---

### 🔎 Search Keyword in History

```bash
curl -X GET \
  "http://localhost:8080/history/search?keyword=Hello" \
  -H "Authorization: Bearer $TOKEN"
```

---

### 👑 Admin Only API

```bash
curl -X GET http://localhost:8080/admin/users \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

---

## ⚙ Settings (Environment Variables)

環境変数で柔軟に変更できます：

| 変数名                           | デフォルト値                     | 説明        |
| ----------------------------- | -------------------------- | --------- |
| `JWT_SECRET`                  | CHANGE_THIS_SECRET_KEY     | JWT署名キー   |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 60                         | Token有効期限 |
| `DB_URL`                      | sqlite:///./data/chat.db   | DBファイル    |
| `OLLAMA_HOST`                 | http://ollama_admin:11434 | Ollamaサーバ |

---

## 🔐 Security Notes

* パスワードは SHA-256（+ SECRET_KEY）でハッシュ
  → 運用では bcrypt / argon2 に変更推奨
* API はすべて JWT 必須
* RBAC により admin だけ管理操作可能
* LLM にはフィルタ済みの履歴のみ渡す
* SQLite → PostgreSQL への置き換え可能

---

## 📝 Roadmap（拡張案）

* [ ] Audit Log（監査ログ）
* [ ] Rate Limit（1分あたりのリクエスト制限）
* [ ] RAG（PDF/文書の取り込み）
* [ ] Admin Dashboard（Web UI）
* [ ] PostgreSQL への移行
* [ ] API Key 認証追加

---

## 📝 License

MIT License

---

## 🧑‍💻 Author

admin
Security / LLM Infra / FastAPI Developer

```

---

# 🔥 次のステップを自動生成できます

- README の英語版  
- ER 図（DB 設計）  
- システム構成図（Mermaid）  
- API ドキュメント（OpenAPI 仕様書）  
- GitHub Actions（CI/CD）  

どれを追加する？
```
