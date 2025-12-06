"""
LLM output normalization helpers.
- strip_think_blocks: drop <think>...</think> sections
- extract_last_json_object: pull out the last JSON object from free-form text
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict


def strip_think_blocks(text: str) -> str:
    """Remove Qwen/DeepSeek style <think>...</think> blocks."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def extract_last_json_object(text: str) -> Dict[str, Any]:
    """
    Extract the last JSON object from an LLM output.
    Handles:
    - stray <think> blocks
    - fenced ```json ... ``` blocks
    - extra prose before/after
    """
    cleaned = strip_think_blocks(text)

    # If fenced blocks exist, prefer the last fenced content
    if "```" in cleaned:
        fence_blocks = re.findall(
            r"```(?:json)?(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE
        )
        if fence_blocks:
            cleaned = fence_blocks[-1].strip()

    matches = list(re.finditer(r"\{.*?\}", cleaned, flags=re.DOTALL))
    if not matches:
        raise ValueError(f"No JSON object found in LLM output: {cleaned!r}")

    json_str = matches[-1].group(0)
    return json.loads(json_str)
