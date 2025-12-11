"""
Admin-only natural language to raw bash command executor.
Now consults RAG first to fill in missing details before planning a command,
and enforces JSON command formatting with validation before execution.
"""
from __future__ import annotations

import logging
import json
import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.auth import get_current_user
from src.config import ENABLE_SHELL_EXEC
from src.database import get_db
from src.models import AdminShellCommand, RagSource
from src.utils import llm_backend
from src.utils.llm_json import strip_think_blocks
from src.utils.rag_context import fetch_rag_context
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
    rag_context: str | None = None
    rag_sources: List[RagSource] = Field(default_factory=list)


SYSTEM_PROMPT_ADMIN = """
You are a command composer for a Linux bash shell inside a Docker container.

- The working directory is /app.
- Convert the user's natural language request into ONE bash command line.
- You may receive context from a knowledge base; prefer those facts over guesses.
- Output MUST be exactly one JSON object in this format:
  {"command": "<one-line bash to run>"}
- Do NOT output explanations, comments, markdown, code fences, or <think> tags.
- Do NOT wrap the JSON in backticks.
- If you need multiple steps, chain them with && in a single line inside the command.
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
    Normalize and validate JSON output to a single command string.
    - strip <think> blocks
    - extract JSON object containing "command"
    - reject empty or banned patterns
    """
    cleaned = strip_think_blocks(text)

    # LLM sometimes returns multiple {"command": "..."} objects concatenated.
    # Grab the first valid one to stay robust while keeping a single-command policy.
    cmd = None
    json_text = None
    cmd_pattern = re.compile(r'\{[^{}]*["\']command["\']\s*:\s*["\'](.+?)["\'][^{}]*\}')
    for m in cmd_pattern.finditer(cleaned):
        json_text = m.group(0)
        cmd = m.group(1)
        break

    if cmd is None:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or start >= end:
            raise ValueError(f"Could not find JSON object in LLM output: {cleaned!r}")
        json_text = cleaned[start : end + 1]
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from LLM: {e}") from e
        cmd = data.get("command")
        if not cmd or not isinstance(cmd, str):
            raise ValueError(f"Missing or invalid 'command' field: {json_text!r}")

    cmd = cmd.strip()

    if "<think>" in cmd or "</think>" in cmd:
        raise ValueError(f"Refusing suspicious command content: {cmd!r}")

    banned = ["rm -rf /", ":(){:|:&};:"]
    if any(b in cmd for b in banned):
        raise ValueError(f"Refusing banned command: {cmd!r}")

    return cmd


@router.post("/exec", response_model=AdminShellAgentResponse)
async def admin_shell_agent_exec(
    payload: AdminShellAgentRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Admin-only agent:
    - Takes natural language instruction
    - LLM generates a bash command line
    - Optionally executes it inside the container
    """
    ensure_shell_enabled()
    ensure_admin(user)

    rag_context, rag_sources = fetch_rag_context(payload.instruction)
    context_prompt = (
        f"Context from RAG (use to resolve paths, names, options):\n{rag_context}"
        if rag_context
        else (
            "No RAG context available. Avoid guessing critical values; prefer "
            "safe inspection commands or clearly state missing prerequisites."
        )
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_ADMIN},
        {"role": "system", "content": context_prompt},
        {"role": "user", "content": payload.instruction},
    ]

    llm_text = llm_backend.call_llm_backend(messages)
    try:
        command = _extract_single_command(llm_text)
    except ValueError as e:
        # LLM が JSON を返さなかった場合は 502 で返してスタックトレースを防ぐ
        preview = llm_text[:500] + ("..." if len(llm_text) > 500 else "")
        logger.warning("admin_shell invalid LLM output: %s", preview)
        raise HTTPException(
            status_code=502,
            detail="LLM output did not contain a valid JSON command. Please retry.",
        ) from e

    if not command:
        logger.error("LLM returned empty command. Raw output: %s", llm_text)
        raise HTTPException(
            status_code=500,
            detail="LLM returned an empty command.",
        )

    if payload.dry_run:
        response = AdminShellAgentResponse(
            instruction=payload.instruction,
            command=command,
            stdout="",
            stderr="DRY RUN: command not executed.",
            exit_code=0,
            dry_run=True,
            rag_context=rag_context,
            rag_sources=rag_sources,
        )
        db.add(
            AdminShellCommand(
                user_id=user.username,
                instruction=payload.instruction,
                command=command,
                stdout="",
                stderr="DRY RUN: command not executed.",
                exit_code=0,
            )
        )
        db.commit()
        return response

    result = run_shell_command(command, timeout=30)

    response = AdminShellAgentResponse(
        instruction=payload.instruction,
        command=command,
        stdout=result["stdout"],
        stderr=result["stderr"],
        exit_code=result["exit_code"],
        dry_run=False,
        rag_context=rag_context,
        rag_sources=rag_sources,
    )

    db.add(
        AdminShellCommand(
            user_id=user.username,
            instruction=payload.instruction,
            command=command,
            stdout=result["stdout"][:2000],
            stderr=result["stderr"][:2000],
            exit_code=result["exit_code"],
        )
    )
    db.commit()

    return response
