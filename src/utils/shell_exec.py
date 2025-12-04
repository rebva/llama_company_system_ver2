"""
Container-scoped shell execution utilities with a small allowlist
for read-only user operations.
"""
from __future__ import annotations

import logging
import shlex
import subprocess
from typing import Literal, Optional

logger = logging.getLogger("llm_api")


class ShellExecutionError(Exception):
    """Shell command execution failed."""


def run_shell_command(
    command: str,
    timeout: int = 10,
    workdir: Optional[str] = None,
) -> dict:
    """
    Run a shell command via /bin/bash -lc '...'.

    Returns:
        dict: { "stdout": str, "stderr": str, "exit_code": int }
    """
    logger.info("[shell_exec] run: %s", command)

    completed = subprocess.run(
        ["/bin/bash", "-lc", command],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    return {
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exit_code": completed.returncode,
    }


SafeAction = Literal["list_dir", "show_file", "tail_file", "disk_usage"]


def build_safe_command(
    action: SafeAction,
    path: Optional[str] = None,
    lines: int = 100,
) -> str:
    """
    Build a read-only command for normal user.
    Only allow safe commands (ls, cat, tail, df).
    """
    safe_path = path or "."
    safe_path_quoted = shlex.quote(safe_path)

    if action == "list_dir":
        return f"ls -lha {safe_path_quoted}"

    if action == "show_file":
        return f"cat {safe_path_quoted}"

    if action == "tail_file":
        n = max(1, min(lines, 1000))  # clip to avoid abusive requests
        return f"tail -n {n} {safe_path_quoted}"

    if action == "disk_usage":
        return "df -h"

    raise ValueError(f"Unsupported safe action: {action}")
