"""
Admin-only natural language to raw bash command executor.
The LLM emits a single bash line; server optionally executes it inside the container.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.auth import get_current_user
from src.config import ENABLE_SHELL_EXEC
from src.utils import llm_backend
from src.utils.llm_json import strip_think_blocks
from src.utils.shell_exec import run_shell_command

logger = logging.getLogger("llm_api")
router = APIRouter(prefix="/agent/admin_shell", tags=["agent-admin-shell"])


class AdminShellAgentRequest(BaseModel):
    instruction: str = Field(..., description="Natural language instruction")
    dry_run: bool = Field(
        False, description="If true, do not execute; only return the planned command."
    )


class AdminShellAgentResponse(BaseModel):
    instruction: str
    command: str
    stdout: str
    stderr: str
    exit_code: int
    dry_run: bool


SYSTEM_PROMPT_ADMIN = """
You are a command composer for a Linux bash shell inside a Docker container.

- The working directory is /app.
- Convert the user's natural language request into ONE bash command line.
- Output MUST be exactly one line of bash code.
- Do NOT output explanations, comments, markdown, JSON or <think> tags.
- Do NOT wrap the command in backticks or fences.
- If you need multiple steps, chain them with && in a single line.
""".strip()


def ensure_shell_enabled() -> None:
    if not ENABLE_SHELL_EXEC:
        raise HTTPException(
            status_code=403,
            detail="Shell execution is disabled by server configuration.",
        )


def ensure_admin(user) -> None:
    if getattr(user, "role", "") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin shell agent is restricted to admin users.",
        )


def _extract_single_command(text: str) -> str:
    """
    Normalize LLM output to a single command line.
    - strip <think> blocks
    - drop fences/backticks if present
    - take the first non-empty line
    """
    cleaned = strip_think_blocks(text)
    if "```" in cleaned:
        parts = cleaned.split("```")
        cleaned = parts[-2] if len(parts) >= 2 else cleaned
    for line in cleaned.splitlines():
        cmd = line.strip()
        if cmd:
            return cmd
    return ""


@router.post("/exec", response_model=AdminShellAgentResponse)
async def admin_shell_agent_exec(
    payload: AdminShellAgentRequest,
    user=Depends(get_current_user),
):
    """
    Admin-only agent:
    - Takes natural language instruction
    - LLM generates a bash command line
    - Optionally executes it inside the container
    """
    ensure_shell_enabled()
    ensure_admin(user)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_ADMIN},
        {"role": "user", "content": payload.instruction},
    ]

    llm_text = llm_backend.call_llm_backend(messages)
    command = _extract_single_command(llm_text)

    if not command:
        logger.error("LLM returned empty command. Raw output: %s", llm_text)
        raise HTTPException(
            status_code=500,
            detail="LLM returned an empty command.",
        )

    if payload.dry_run:
        return AdminShellAgentResponse(
            instruction=payload.instruction,
            command=command,
            stdout="",
            stderr="DRY RUN: command not executed.",
            exit_code=0,
            dry_run=True,
        )

    result = run_shell_command(command, timeout=30)

    return AdminShellAgentResponse(
        instruction=payload.instruction,
        command=command,
        stdout=result["stdout"],
        stderr=result["stderr"],
        exit_code=result["exit_code"],
        dry_run=False,
    )
