"""
/sql/chat: 履歴を安全に扱うツール付きチャットエンドポイント。
"""
from __future__ import annotations

import json
import textwrap
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.auth import get_current_user
from src.utils.llm_backend import call_llm_simple
from src.sql_tools_readonly import (
    fetch_user_conversations,
    search_user_conversations,
)

router = APIRouter(prefix="/sql", tags=["sql-chat"])


class SqlChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    max_history: int = Field(50, ge=1, le=500, description="Number of messages to send to LLM (reserved for future use)")


class SqlChatResponse(BaseModel):
    reply: str
    used_tools: List[Dict[str, Any]] = Field(default_factory=list)


def _build_sql_tools_system_prompt() -> str:
    """
    LLM に「正しい JSON で tool_call を返す」ことを徹底させるプロンプト。
    """
    return textwrap.dedent(
        """
        You are a helpful assistant for the current user.

        You can inspect ONLY the current user's chat history using these tools:

        1) fetch_user_conversations
           Arguments (JSON object):
           {
             "session_id": string | null,
             "from_datetime": string | null,
             "to_datetime": string | null,
             "limit": integer | null
           }

        2) search_user_conversations
           Arguments (JSON object, required: keyword):
           {
             "keyword": string,
             "session_id": string | null,
             "limit": integer | null
           }

        VERY IMPORTANT:
        - When you call a tool, you MUST pass arguments as a VALID JSON OBJECT STRING.
          Example: {"keyword": "error", "limit": 20}
        - Do NOT pass plain text like "error" or "keyword=error".
        - If you can answer without a tool, respond with:
          {"mode": "answer", "answer": "..."}
        - If you need a tool, respond with:
          {"mode": "tool_call", "name": "<tool name>", "args": { ... }}
        - Never include user id; the server handles authentication.
        - Respond in JSON only (no extra text).
        """
    ).strip()


@router.post("/chat", response_model=SqlChatResponse)
async def sql_chat(
    body: SqlChatRequest,
    current_user=Depends(get_current_user),
):
    """
    /sql/chat: 安全な「履歴アシスタント」エンドポイント（JSON プロトコル版）。

    ステップ:
    1) LLM に JSON だけで「回答 or tool_call」を返させる
    2) tool_call の場合だけ DB ツールを実行
    3) DB 結果を渡して LLM に最終回答を書かせる
    """
    user_id: str = current_user.username
    user_message = body.message

    # --- 1. 1回目: ツールを使うかの JSON を LLM に書かせる ---
    system_prompt_step1 = _build_sql_tools_system_prompt()

    messages_step1: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt_step1},
        {"role": "user", "content": user_message},
    ]

    resp1 = call_llm_simple(messages_step1)
    msg1 = resp1["choices"][0]["message"]
    content1 = msg1.get("content") or ""
    tool_calls = msg1.get("tool_calls") or []

    used_tools: List[Dict[str, Any]] = []

    # --- 1-1. OpenAI style tool_calls が返ってきた場合 ---
    if tool_calls:
        tool_results: List[Dict[str, Any]] = []

        for tc in tool_calls:
            name = tc.get("function", {}).get("name")
            args_raw = tc.get("function", {}).get("arguments") or {}

            print("=== /sql/chat tool_call raw ===")
            print("name:", name)
            print("args_raw:", repr(args_raw))
            print("================================")

            # args を JSON として解釈、失敗したら keyword に詰めて検索に寄せる
            if isinstance(args_raw, str):
                try:
                    args = json.loads(args_raw)
                except json.JSONDecodeError:
                    args = {"keyword": args_raw.strip()}
            else:
                args = args_raw

            if not isinstance(args, dict):
                args = {}

            used_tools.append({"name": name, "args": args})

            if name == "fetch_user_conversations":
                db_result = fetch_user_conversations(
                    user_id=user_id,
                    session_id=args.get("session_id"),
                    from_datetime=args.get("from_datetime"),
                    to_datetime=args.get("to_datetime"),
                    limit=args.get("limit", 50),
                )
            elif name == "search_user_conversations":
                db_result = search_user_conversations(
                    user_id=user_id,
                    keyword=args.get("keyword", ""),
                    session_id=args.get("session_id"),
                    limit=args.get("limit", 50),
                )
            else:
                db_result = {"error": f"unknown tool: {name}"}

            tool_results.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id") or name,
                    "name": name,
                    "content": json.dumps(db_result, ensure_ascii=False),
                }
            )

        # Step3: ツール結果を LLM に渡して最終回答を生成
        system_prompt_step2 = (
            "You are a helpful assistant.\n"
            "Use the provided tool results to answer the user's original question.\n"
            "Do not expose raw database internals unless explicitly requested.\n"
        )

        messages_step2: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt_step2},
            {"role": "user", "content": user_message},
        ] + tool_results

        resp2 = call_llm_simple(messages_step2)
        msg2 = resp2["choices"][0]["message"]
        answer2 = msg2.get("content") or ""

        return SqlChatResponse(reply=answer2, used_tools=used_tools)

    # --- 2. JSON 解析。壊れていればそのまま返す ---
    try:
        decision = json.loads(content1)
    except json.JSONDecodeError:
        return SqlChatResponse(reply=content1, used_tools=used_tools)

    mode = decision.get("mode")

    # --- 2-1. 直接回答パス ---
    if mode == "answer":
        answer_text = decision.get("answer", "")
        return SqlChatResponse(reply=answer_text, used_tools=used_tools)

    # --- 2-2. ツール呼び出しパス ---
    if mode == "tool_call":
        name = decision.get("name")
        args_raw = decision.get("args") or {}

        # デバッグログ: LLM が何を返しているか観察する
        print("=== /sql/chat tool_call raw ===")
        print("name:", name)
        print("args_raw:", repr(args_raw))
        print("================================")

        # args が文字列なら JSON にパースを試み、失敗したら検索用に keyword に詰める
        if isinstance(args_raw, str):
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {"keyword": args_raw.strip()}
        else:
            args = args_raw

        # args が壊れている（文字列など）のケースを防御
        if not isinstance(args, dict):
            return SqlChatResponse(
                reply="Invalid tool args from LLM (expected JSON object).",
                used_tools=used_tools,
            )

        if name == "fetch_user_conversations":
            tool_result = fetch_user_conversations(
                user_id=user_id,
                session_id=args.get("session_id"),
                from_datetime=args.get("from_datetime"),
                to_datetime=args.get("to_datetime"),
                limit=args.get("limit", 50),
            )
        elif name == "search_user_conversations":
            tool_result = search_user_conversations(
                user_id=user_id,
                keyword=args.get("keyword", ""),
                session_id=args.get("session_id"),
                limit=args.get("limit", 50),
            )
        else:
            tool_result = {"error": f"unknown tool: {name}"}

        used_tools.append({"name": name, "args": args})

        # --- 3. DB 結果を渡して最終回答を LLM に書かせる ---
        system_prompt_step2 = (
            "You are a helpful assistant.\n"
            "The server executed a database tool for the current user.\n"
            "Use the provided JSON result to answer the user's original question.\n"
            "Do not expose raw database internals unless explicitly requested.\n"
        )

        messages_step2: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt_step2},
            {
                "role": "user",
                "content": (
                    "User question:\n"
                    f"{user_message}\n\n"
                    "Database tool result (JSON):\n"
                    f"{json.dumps(tool_result, ensure_ascii=False)}"
                ),
            },
        ]

        resp2 = call_llm_simple(messages_step2)
        msg2 = resp2["choices"][0]["message"]
        answer2 = msg2.get("content") or ""

        return SqlChatResponse(reply=answer2, used_tools=used_tools)

    # mode 不明: LLM がプロトコルを守らなかった場合は素の内容を返す
    return SqlChatResponse(reply=content1, used_tools=used_tools)
