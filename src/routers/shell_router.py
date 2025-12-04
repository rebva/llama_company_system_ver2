"""
Shell execution endpoints.
- /shell/admin/exec: admin-only raw commands (container scoped)
- /shell/user/exec: user-safe, allowlisted read-only actions
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.auth import get_current_user
from src.config import ENABLE_SHELL_EXEC
from src.utils.shell_exec import (
    run_shell_command,
    build_safe_command,
    SafeAction,
)

router = APIRouter(prefix="/shell", tags=["shell"])


class ShellCommandRequest(BaseModel):
    command: str = Field(..., description="Shell command string for admin only")


class ShellCommandResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


class ShellHighLevelRequest(BaseModel):
    action: SafeAction
    path: str | None = None
    lines: int = 100


def ensure_shell_enabled() -> None:
    if not ENABLE_SHELL_EXEC:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Shell execution is disabled by server configuration.",
        )


@router.post("/admin/exec", response_model=ShellCommandResponse)
async def exec_shell_admin(
    payload: ShellCommandRequest,
    user=Depends(get_current_user),
):
    """
    Admin only: run arbitrary shell command inside the llm_api container.
    """
    ensure_shell_enabled()

    if getattr(user, "role", "") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only endpoint.",
        )

    result = run_shell_command(payload.command, timeout=20)
    return ShellCommandResponse(**result)


@router.post("/user/exec", response_model=ShellCommandResponse)
async def exec_shell_user(
    payload: ShellHighLevelRequest,
    user=Depends(get_current_user),
):
    """
    Normal user: run only safe, read-only commands.
    No sudo, no write, only allowlist-based high-level actions.
    """
    ensure_shell_enabled()

    command = build_safe_command(
        action=payload.action,
        path=payload.path,
        lines=payload.lines,
    )
    result = run_shell_command(command, timeout=10)
    return ShellCommandResponse(**result)
