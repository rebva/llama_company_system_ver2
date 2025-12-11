"""
LLM バックエンド呼び出しのラッパー。
"""
import json
import logging
from typing import Any, Dict, List, Optional

import requests
from fastapi import HTTPException

from src.config import VLLM_BASE_URL, LLM_MODEL

logger = logging.getLogger("llm_api")


def _messages_to_prompt(messages: List[dict]) -> str:
    """
    Chat形式の履歴を、/v1/completions にそのまま渡せる 1 本の prompt に変換する。
    - system ロールは先頭にまとめる
    - user/assistant は [INST] ... [/INST] と回答を順に連結する
    """
    system_chunks: List[str] = []
    turns: List[Dict[str, Optional[str]]] = []

    for msg in messages:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if not content:
            continue

        if role == "system":
            system_chunks.append(content)
            continue

        if role == "user":
            turns.append({"user": content, "assistant": None})
            continue

        if role == "assistant":
            if turns and turns[-1].get("assistant") is None:
                turns[-1]["assistant"] = content
            else:
                turns.append({"user": None, "assistant": content})

    prompt_lines: List[str] = []
    if system_chunks:
        prompt_lines.append("\n\n".join(system_chunks))

    for turn in turns:
        user_content = turn.get("user")
        if user_content:
            prompt_lines.append(f"[INST] {user_content} [/INST]")

        assistant_content = turn.get("assistant")
        if assistant_content:
            prompt_lines.append(assistant_content)

    prompt = "\n".join(prompt_lines).strip()
    return prompt


def _post_completion(
    prompt: str,
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    timeout_sec: int = 120,
) -> Dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    resp = requests.post(
        f"{VLLM_BASE_URL}/completions",
        json=payload,
        timeout=timeout_sec,
    )

    if not resp.ok:
        logger.error("vLLM error: status=%s body=%s", resp.status_code, resp.text)
        logger.error(
            "Payload sent to vLLM: %s",
            json.dumps(payload, ensure_ascii=False)[:2000],
        )
        raise HTTPException(
            status_code=502,
            detail=f"LLM backend error {resp.status_code}",
        )

    data = resp.json()
    choices = data.get("choices") or []
    if not choices or "text" not in choices[0]:
        raise HTTPException(
            status_code=500,
            detail="LLM response format error: missing 'text' in choices[0]",
        )

    # 後方互換のため、chat/completions 風の message を付ける
    text = choices[0].get("text") or ""
    choices[0]["message"] = {"role": "assistant", "content": text}
    data["choices"] = choices
    return data


def call_llm_backend(
    messages: List[dict],
    model_name: Optional[str] = None,
    max_tokens: int = 1024,
) -> str:
    """
    Ollama/vLLM の /v1/completions を叩いてレスポンスを取得。
    """
    model = model_name or LLM_MODEL
    prompt = _messages_to_prompt(messages)
    data = _post_completion(
        prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=0.0,
        timeout_sec=60,
    )

    return data["choices"][0]["text"]


# シンプルなチャット呼び出し（tools なし、レスポンス全体を返す）
def call_llm_simple(
    messages: List[Dict[str, Any]],
    model_name: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> Dict[str, Any]:
    model = model_name or LLM_MODEL
    prompt = _messages_to_prompt(messages)
    data = _post_completion(
        prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return data


# --- /sql/chat 用: LLM に公開する SQL ツール定義と専用呼び出し ---
SQL_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "fetch_user_conversations",
            "description": "Get chat history messages of the current user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Optional session id to filter messages.",
                    },
                    "from_datetime": {
                        "type": "string",
                        "description": "Start datetime in ISO format, e.g. 2025-01-01T00:00:00",
                    },
                    "to_datetime": {
                        "type": "string",
                        "description": "End datetime in ISO format.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of messages to fetch.",
                        "default": 50,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_user_conversations",
            "description": "Search chat messages of the current user by keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Keyword to search in message content.",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Optional session id to filter messages.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of messages to fetch.",
                        "default": 50,
                    },
                },
                "required": ["keyword"],
            },
        },
    },
]


def call_llm_with_sql_tools(
    messages: List[Dict[str, Any]],
    model_name: Optional[str] = None,
    max_tokens: int = 1024,
) -> Dict[str, Any]:
    """
    /sql/chat 用の LLM 呼び出し。
    現状は tools 機能を無効化し、通常の chat/completions として呼び出す。
    """
    model = model_name or LLM_MODEL
    prompt = _messages_to_prompt(messages)
    data = _post_completion(
        prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=0.0,
    )
    return data
