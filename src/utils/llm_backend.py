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


def call_llm_backend(
    messages: List[dict],
    model_name: Optional[str] = None,
    max_tokens: int = 1024,
) -> str:
    """
    Ollama/vLLM の /v1/chat/completions を叩いてレスポンスを取得。
    """
    model = model_name or LLM_MODEL
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
    }

    resp = requests.post(
        f"{VLLM_BASE_URL}/chat/completions",
        json=payload,
        timeout=60,
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
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise HTTPException(
            status_code=500,
            detail=f"LLM response format error: {e}",
        )


# シンプルなチャット呼び出し（tools なし、レスポンス全体を返す）
def call_llm_simple(
    messages: List[Dict[str, Any]],
    model_name: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> Dict[str, Any]:
    model = model_name or LLM_MODEL
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    resp = requests.post(
        f"{VLLM_BASE_URL}/chat/completions",
        json=payload,
        timeout=120,
    )

    if not resp.ok:
        logger.error("vLLM error: status=%s body=%s", resp.status_code, resp.text)
        logger.error(
            "Payload sent to vLLM (simple): %s",
            json.dumps(payload, ensure_ascii=False)[:2000],
        )
        raise HTTPException(
            status_code=502,
            detail=f"LLM backend error {resp.status_code}",
        )

    data = resp.json()
    try:
        _ = data["choices"][0]["message"]
    except (KeyError, IndexError) as e:
        raise HTTPException(
            status_code=500,
            detail=f"LLM response format error: {e}",
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
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
    }

    resp = requests.post(
        f"{VLLM_BASE_URL}/chat/completions",
        json=payload,
        timeout=120,
    )

    if not resp.ok:
        logger.error("vLLM error: status=%s body=%s", resp.status_code, resp.text)
        logger.error(
            "Payload sent to vLLM (sql tools): %s",
            json.dumps(payload, ensure_ascii=False)[:2000],
        )
        raise HTTPException(
            status_code=502,
            detail=f"LLM backend error {resp.status_code}",
        )

    data = resp.json()
    try:
        # shape validation only; router側で中身を扱う
        _ = data["choices"][0]["message"]
    except (KeyError, IndexError) as e:
        raise HTTPException(
            status_code=500,
            detail=f"LLM response format error: {e}",
        )
    return data
