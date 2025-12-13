""" Admin-only natural language to raw bash command executor. Now consults RAG first to fill in missing details before planning a command, and enforces JSON command formatting with validation before execution. """
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
You are an *admin-only* bash command executor running inside the `llm_api` container.

Runtime environment:
- OS: Ubuntu Linux
- Shell: /bin/bash (non-interactive: no TTY, no user input)
- Project root: /app
- Important paths:
    - /app/chroma_db
    - /app/data

Your job:
- Read the user's natural language request.
- If needed, first consult the RAG system to fill in missing details.
- Then plan ONE bash command that solves the request.
- Output ONLY one JSON object.

Output format (very important):
- Return exactly this JSON structure:

    {
        "command": "<ONE bash command>",
        "reason": "<short explanation in Japanese>"
    }

Rules for "command":
- The command MUST be a single line.
- The command MUST start with:
    cd /app &&
- Do NOT use "~" (tilde) for paths. Use absolute paths like /app/...
- Do NOT use "\" for line continuation.
- Do NOT add comments (# ...) in the command.
- If you need multiple steps, chain them with "&&" in one line.
- Use only non-interactive commands.

Working directory rules:
- Always assume the project files are under /app.
- To access source code or config files, use paths like:
    - /app/main.py
    - /app/src/...
    - /app/chroma_db/chroma.sqlite3
    - /app/data/...

SQLite rules:
- The RAG database file is: /app/chroma_db/chroma.sqlite3
- Do NOT start interactive sqlite3 sessions.
- BAD:
    - sqlite3 /app/chroma_db/chroma.sqlite3
    - sqlite3 data.db
- GOOD:
    - cd /app && sqlite3 /app/chroma_db/chroma.sqlite3 ".tables"
    - cd /app && sqlite3 /app/chroma_db/chroma.sqlite3 "SELECT * FROM collection_metadata LIMIT 5;"

Safety rules:
- Never run editors (vim, nano, less) or interactive shells.
- Never run commands that wait for password input.
- Prefer read-only commands unless the user clearly asks to change data.
- Be careful with destructive commands (rm, mv, chmod, chown). If needed, keep them minimal and targeted.
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
