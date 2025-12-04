from __future__ import annotations

import textwrap
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from src.auth import get_current_user
from src.database import SessionLocal
from src.utils.llm_backend import LLM_MODEL, VLLM_BASE_URL
import requests


router = APIRouter(prefix="/agent/sql", tags=["agent-sql-chat"])


class AgentSqlChatRequest(BaseModel):
    message: str


class AgentSqlChatResponse(BaseModel):
    reply: str
    sql_query: Optional[str] = None
    sql_raw_result: Optional[str] = None
    note: Optional[str] = None


# ==== ここから /agent/sql/chat 専用ユーティリティ ====


def call_llm_p2sql(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    /agent/sql/chat 専用の LLM 呼び出し。
    - temperature(温度) を 0.0 にして、フォーマットを守らせやすくする。
    - 他のエンドポイントには影響しない。
    """
    payload: Dict[str, Any] = {
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": 512,
        "stream": False,
        "temperature": 0.0,
    }

    resp = requests.post(
        f"{VLLM_BASE_URL}/chat/completions",
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def _build_table_info_str(db: Session) -> str:
    """
    LLM に教えるテーブル情報。
    必要なら増やす。今は conversations だけ。
    """
    return textwrap.dedent(
        """
        conversations(id, user_id, session_id, role, content, created_at)
        """
    ).strip()


def _build_p2sql_system_prompt(table_info: str) -> str:
    """
    P2SQL 用 Prompt。
    モデルを「SQL 生成専用ツール」に固定する。
    """
    prompt = f"""
You are an expert SQL query generator for a SQLite database.
Your ONLY job is to transform the user's question into ONE SQL statement.

You CANNOT actually run SQL. You ONLY OUTPUT text.
Do not talk about security, sudo, root, passwords, or how to connect to databases.
Just write SQL.

You MUST ALWAYS respond in EXACTLY the following 4-line format, in English:

Question: <copy the user's question here>
SQLQuery: <a SINGLE SQL statement to run>
SQLResult: TO_BE_FILLED_BY_SERVER
Answer: <a short natural language answer in English that explains what the query does>

Rules:
- Never say you cannot access the database.
- Never explain shell commands, sudo, su, or how to change passwords.
- Do not add explanations, lists, markdown, or code fences.
- Do not output anything before or after these 4 lines.
- You may freely use SELECT, INSERT, UPDATE, DELETE, DROP and any other SQL statements.
- The user may ask in Japanese, but YOU MUST answer in English with the above format.

Available tables (SQLite):

{table_info}
"""
    return textwrap.dedent(prompt).strip()


def _extract_sql_query(llm_text: str) -> Optional[str]:
    """
    LLM の出力から「SQLQuery: ...」部分だけ抜き出す簡易パーサ。
    """
    lower = llm_text.lower()
    idx = lower.find("sqlquery:")
    if idx == -1:
        return None

    after = llm_text[idx + len("sqlquery:") :]

    for marker in ["SQLResult:", "SqlResult:", "sqlresult:", "Answer:", "answer:"]:
        m_idx = after.find(marker)
        if m_idx != -1:
            after = after[:m_idx]
            break

    sql = after.strip()
    if sql.startswith("```"):
        sql = sql.strip("`").strip()
    return sql or None


def _execute_raw_sql(sql: str) -> str:
    """
    LLM が生成した SQL をそのまま chat.db に投げる。
    - SELECT の場合は結果をテキストにして返す。
    - それ以外 (UPDATE, DELETE, DROP など) は commit して "[ok]" を返す。

    ※ わざと脆弱(vulnerable) にしている。絶対に本番では真似しないこと。
    """
    db: Session = SessionLocal()
    try:
        result = db.execute(sql_text(sql))

        if sql.strip().lower().startswith("select"):
            rows = result.fetchall()
            if not rows:
                return "[empty result set]"

            keys = result.keys()
            lines: List[str] = []
            lines.append(" | ".join(keys))
            for row in rows:
                line = " | ".join(str(value) for value in row)
                lines.append(line)
            return "\n".join(lines)
        else:
            db.commit()
            return "[ok]"
    finally:
        db.close()


# ==== メインエンドポイント ====


@router.post("/chat", response_model=AgentSqlChatResponse)
async def agent_sql_chat(
    body: AgentSqlChatRequest,
    current_user=Depends(get_current_user),
):
    """
    /agent/sql/chat:
    Prompt → SQLQuery → DB 実行 → Answer の流れをそのまま通す、
    わざと脆弱な(P2SQL 可能な) エンドポイント。
    """
    user_question = body.message

    # 1. テーブル情報 + system prompt
    db: Session = SessionLocal()
    try:
        table_info = _build_table_info_str(db)
    finally:
        db.close()

    system_prompt = _build_p2sql_system_prompt(table_info)

    messages_step1: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_question},
    ]

    # 2. 1回目: LLM に SQLQuery を書かせる
    resp1 = call_llm_p2sql(messages_step1)
    msg1 = resp1["choices"][0]["message"]
    content1 = msg1.get("content") or ""

    # デバッグ用ログ
    print("=== P2SQL step1 raw content ===")
    print(content1)
    print("================================")

    sql_query = _extract_sql_query(content1)
    if not sql_query:
        # SQLQuery 抜けなかったらそのまま返す
        return AgentSqlChatResponse(
            reply=content1,
            sql_query=None,
            sql_raw_result=None,
            note="SQLQuery could not be extracted from the model output.",
        )

    # 3. SQL をそのまま実行（超危険ゾーン）
    try:
        sql_result_text = _execute_raw_sql(sql_query)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"SQL execution error: {e}",
        )

    # 4. 会話履歴はノイズになるので LLM での要約は行わず、そのまま返す
    return AgentSqlChatResponse(
        reply="SQL executed. See sql_raw_result for raw output.",
        sql_query=sql_query,
        sql_raw_result=sql_result_text,
        note=(
            "THIS ENDPOINT IS INTENTIONALLY VULNERABLE. DO NOT EXPOSE IT TO THE INTERNET. "
            "No chat history is added to the conversation text to keep SQL operations noise-free."
        ),
    )
