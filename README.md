ここでは **/sql/chat =「安全な履歴アシスタント」** として設計します。

---

## 1. /sql/chat の役割とユースケース

### 1.1 役割

> **「あなた専用の“履歴秘書”チャット」**
> 通常の会話もしつつ、
> 必要なら DB から自分のログを引っ張ってきて分析や要約をしてくれる。

### 1.2 想定ユースケース

例：

* 「先週の自分の質問を全部要約して」
* 「最近、どんなトピックをよく聞いているかリストにして」
* 「このセッションの会話を短くまとめて」
* 「security という単語が出ているメッセージだけ教えて」

→ これらはすべて
**「自然文の質問 → LLM → 必要なら DB ツールを呼ぶ → 結果を読んで答える」**
という流れで処理します。

---

## 2. /sql/chat の API 仕様 (設計案)

### 2.1 パスとメソッド

* `POST /sql/chat`
* 認証必須 (既存の `get_current_user` を利用)

### 2.2 リクエストボディ (JSON)

最小構成：

```jsonc
{
  "message": "先週の会話を要約して",
  "session_id": "optional-session-id",      // 省略可
  "max_history": 100                        // 省略可（LLMに渡す履歴の上限）
}
```

* `message` (必須): ユーザーの自然文の質問
* `session_id` (任意): 特定セッションだけを対象にしたい時
* `max_history` (任意): LLM に渡すログ数の上限（DoS 対策にもなる）

### 2.3 レスポンス (JSON)

```jsonc
{
  "reply": "ユーザー向けの最終回答テキスト",
  "used_tools": [
    {
      "name": "fetch_user_conversations",
      "args": {
        "session_id": "abc123",
        "limit": 50
      }
    }
  ],
  "meta": {
    "model": "llm-jp/llm-jp-3.1-1.8b-instruct4",
    "took_ms": 1234
  }
}
```

* `reply`: 画面に出すテキスト
* `used_tools`: どの DB ツールをどんな引数で呼んだか（デバッグ・監査用）
* `meta`: お好みで

---

## 3. アーキテクチャ（/sql/chat だけ）

```text
Client (UI)
  ↓ POST /sql/chat
[FastAPI Router (/sql/chat)]
  ↓
[SQL Chat Orchestrator (調停役)]  ← 新規
  ├─ LLM 呼び出し (tools付き)
  └─ DB ツール呼び出し (read-only)
        ↓
      SQLite chat.db
```

### 3.1 Orchestrator(オーケストレータ: 全体制御役) の責務

* JWT から `user_id` を取得
* LLM に

  * system メッセージ
  * user メッセージ
  * （必要なら）過去の通常チャット履歴
    を渡して呼び出す
* レスポンスに `tool_calls` があれば：

  * `tool_name` を見て対応する Python 関数を呼ぶ
  * 戻り値を `role=tool` メッセージとして LLM に再入力
* 最終的に `role=assistant` の自然文返信が来たら、それを `/sql/chat` のレスポンスとする

---

## 4. DB ツール設計（/sql/chat 用：READ ONLY）

### 4.1 テーブル前提（仮定）

`conversations` テーブル（既にある想定）：

* `id`
* `user_id`
* `session_id`
* `role` ("user" / "assistant" / "system")
* `content`
* `created_at`

※ 正確なスキーマは実装段階で合わせれば OK。ここは設計レベル。

### 4.2 /sql/chat の「公開ツール」

**ステージ 1 では READ ONLY に限定**します。

1. `fetch_user_conversations`

   * 目的: 指定条件で会話ログを取得
   * 引数:

     * `session_id` (任意)
     * `from_datetime` (任意, ISO 8601 文字列)
     * `to_datetime` (任意)
     * `limit` (デフォルト 50, 最大 200 など)
   * 制約:

     * `user_id` は JWT からサーバ側でセット（LLM には触らせない）

2. `search_user_conversations`

   * 目的: `content LIKE '%keyword%'` 的なテキスト検索
   * 引数:

     * `keyword` (必須)
     * `limit` など
   * 制約:

     * もちろん `user_id` でフィルタ

> **注意**:
> 書き込み系 (DELETE / UPDATE) は、ここではまだ設計に入れない。
> 「安全に動く READ ONLY エージェント」をまず完成させる。

---

## 5. LLM 側のツール定義 (論理設計)

OpenAI 互換の `tools` / `functions` のイメージ：

```jsonc
[
  {
    "type": "function",
    "function": {
      "name": "fetch_user_conversations",
      "description": "Get chat history messages of the current user.",
      "parameters": {
        "type": "object",
        "properties": {
          "session_id": { "type": "string" },
          "from_datetime": { "type": "string" },
          "to_datetime": { "type": "string" },
          "limit": {
            "type": "integer",
            "default": 50,
            "description": "Max number of messages to fetch."
          }
        }
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "search_user_conversations",
      "description": "Search chat messages of the current user by keyword.",
      "parameters": {
        "type": "object",
        "properties": {
          "keyword": { "type": "string" },
          "limit": {
            "type": "integer",
            "default": 50
          }
        },
        "required": ["keyword"]
      }
    }
  }
]
```

※ 実装時は Python の dict で同じ構造を作る形。

---

## 6. /sql/chat 専用の system プロンプト設計

ここが「通常チャット」との一番の違いです。

### 6.1 役割定義（案）

```text
You are a helpful assistant that can also inspect the CURRENT USER's
chat history using tools.

Important safety rules:
- You can access ONLY the current user's conversations.
- You MUST NOT assume or guess another user's ID or data.
- You MUST NOT output SQL queries or database internals directly to the user.
- Use tools only when they are really helpful.
- For normal questions, just answer as a normal assistant.

Typical usages:
- Summarize the user's recent conversations.
- Find messages that contain a specific keyword.
- Analyze patterns in the user's questions.

If the user asks you to do something outside your tools (ex: delete the whole database),
politely refuse and explain the limitation.
```

英語は少し長いですが、**ルールを LLM に明示することが重要**です。

---

## 7. セキュリティ設計上のポイント (/sql/chat)

設計段階で意識しておくべきポイントだけ列挙しておきます：

1. **user_id は LLM に触らせない**

   * ルーター or オーケストレータが JWT から取り出し、DB ツールに渡す
   * ツール引数には `user_id` を含めない

2. **SQL はすべて Python コード側で固定**

   * LLM に SQL を一切書かせない
   * `fetch_user_conversations` も ORM / 固定クエリで実装

3. **READ ONLY から始める**

   * UPDATE / DELETE は次フェーズで設計
   * 今回は「事故って DB 消えた」が絶対に起こらないようにする

4. **ツール呼び出し回数の上限**

   * 無限ループを防ぐため、1 リクエストあたり 2〜3 回まで

5. **監査ログ (audit log)**

   * 後で Garak やテストで使いたくなるので、

     * `user_id`
     * `tool_name`
     * `args`
   * を DB に記録するテーブルを用意する案も良い

---

## 8. 実装フェーズへのブレークダウン

次にやるべき「実装タスク」を簡単にリストにしておきます：

1. **Router の追加**

   * `src/routers/sql_safe_router.py` などを作成
   * `POST /sql/chat` を定義
   * `main.py` に `app.include_router` を追加

2. **DB ツールモジュール**

   * `src/sql_tools_readonly.py` のような名前で

     * `fetch_user_conversations`
     * `search_user_conversations`
   * を実装（中身は SQLAlchemy の SELECT のみ）

3. **LLM ツール付き呼び出しラッパ**

   * `call_llm_with_sql_tools(messages: list[dict])` みたいな関数を追加
   * `tools` に上記 2 つを設定して vLLM に投げる

4. **オーケストレータ**

   * `/sql/chat` のハンドラ内で

     * `messages` 構築
     * `tool_calls` のループ処理（最大 3 回程度）
     * `tool` ロールメッセージを LLM に戻す

---
