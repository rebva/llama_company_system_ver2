"""
Natural-language to safe shell actions via LLM.
The LLM only decides an allowlisted action; the server builds and runs the command.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.auth import get_current_user
from src.config import ENABLE_SHELL_EXEC
from src.utils import llm_backend
from src.utils.llm_json import extract_last_json_object
from src.utils.shell_exec import (
    build_safe_command,
    run_shell_command,
    SafeAction,
)

logger = logging.getLogger("llm_api")
router = APIRouter(prefix="/agent/shell", tags=["agent-shell"])


class ShellAgentRequest(BaseModel):
    instruction: str = Field(..., description="Natural language instruction from user")


class ShellAgentResponse(BaseModel):
    instruction: str
    decided_action: SafeAction
    path: str | None = None
    lines: int = 100
    command: str
    stdout: str
    stderr: str
    exit_code: int


SYSTEM_PROMPT = """
You are a command planner for a safe shell helper.

You NEVER run commands yourself. You only decide ONE action for the backend and must output exactly one JSON object.
Allowed actions (case sensitive) are:
- "list_dir": list directory contents
- "show_file": show full file content
- "tail_file": show last N lines of a file
- "disk_usage": show disk usage (df -h)

Return ONLY a JSON object with this schema:
{
  "action": "list_dir" | "show_file" | "tail_file" | "disk_usage",
  "path": "<path or null>",
  "lines": 100
}

Rules:
- If the user wants to see files in a folder -> use "list_dir" with that folder path.
- If the user wants to see disk usage -> use "disk_usage" and path = null.
- If the user wants to see content of a file -> use "show_file" and set path.
- If the user wants to see recent logs -> use "tail_file", set path, choose a reasonable lines (e.g. 200).
- Never add explanations. Output pure JSON only.
- Do NOT wrap JSON in backticks.
- Do NOT output <think> tags; think silently if needed.
""".strip()


def ensure_shell_enabled() -> None:
    if not ENABLE_SHELL_EXEC:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Shell execution is disabled by server configuration.",
        )


@router.post("/exec", response_model=ShellAgentResponse)
async def agent_shell_exec(
    payload: ShellAgentRequest,
    user=Depends(get_current_user),
):
    """
    Natural language -> LLM -> safe shell command (user-safe actions only).
    """
    ensure_shell_enabled()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": payload.instruction},
    ]

    # LLM decides the plan as JSON string
    llm_text = llm_backend.call_llm_backend(messages)

    try:
        plan = extract_last_json_object(llm_text)
    except ValueError as e:
        logger.error("LLM returned invalid JSON: %s", llm_text)
        raise HTTPException(
            status_code=500,
            detail=f"LLM returned invalid JSON: {e}",
        )

    action = plan.get("action")
    path = plan.get("path")
    lines_raw = plan.get("lines", 100)
    try:
        lines = int(lines_raw)
    except (TypeError, ValueError):
        lines = 100

    if action not in ("list_dir", "show_file", "tail_file", "disk_usage"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported action from LLM: {action}",
        )

    command = build_safe_command(action=action, path=path, lines=lines)
    result = run_shell_command(command, timeout=10)

    return ShellAgentResponse(
        instruction=payload.instruction,
        decided_action=action,
        path=path,
        lines=lines,
        command=command,
        stdout=result["stdout"],
        stderr=result["stderr"],
        exit_code=result["exit_code"],
    )
