"""
LLM バックエンド呼び出しのラッパー。
"""
import json
import logging
from typing import Optional, List

import requests
from fastapi import HTTPException

from src.config import OLLAMA_HOST, OLLAMA_MODEL

logger = logging.getLogger("llm_api")


def call_llm_backend(
    messages: List[dict],
    model_name: Optional[str] = None,
    max_tokens: int = 256,
) -> str:
    """
    Ollama/vLLM の /v1/chat/completions を叩いてレスポンスを取得。
    """
    model = model_name or OLLAMA_MODEL
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
    }

    resp = requests.post(
        f"{OLLAMA_HOST}/v1/chat/completions",
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
