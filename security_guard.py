#!/usr/bin/env python3
"""
Security Guard Hook for Claude Code (PreToolUse)

Blocks tool calls that would expose credentials (.env files, API keys, tokens)
to the LLM context. Runs synchronously before every tool execution.

Why: Claude Code reads .env files automatically. Any secrets in the LLM context
can leak through prompt injection, logs, or creative tool use. This hook ensures
the agent never sees your credentials directly.

How: Use API wrapper scripts that source .env internally and return only
structured output. The LLM gets the data it needs without ever seeing the keys.

Exit codes:
  0 = Allow (tool executes normally)
  2 = Block (reason printed to stdout, shown to the LLM)

Install: See README.md for setup instructions.
License: MIT
"""

import json
import os
import re
import sys
import time
from pathlib import Path

# --- Configuration ---

# Where to log blocked attempts (set to None to disable logging)
LOG_DIR = Path.home() / ".claude-security"
LOG_FILE = LOG_DIR / "security-guard.log"

# --- Logging ---

def log_blocked(tool_name: str, reason: str, detail: str) -> None:
    """Log blocked tool calls for audit."""
    if LOG_DIR is None:
        return
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        session_id = os.environ.get("CLAUDE_SESSION_ID", "unknown")
        with open(LOG_FILE, "a") as f:
            f.write(
                f"[{timestamp}] BLOCKED | session={session_id} "
                f"| tool={tool_name} | reason={reason} "
                f"| detail={detail[:200]}\n"
            )
    except OSError:
        pass  # Logging must never block execution


# --- Bash Command Checks ---

BASH_BLOCK_PATTERNS = [
    # Direct .env file access
    (r"(?:source|\.)\s+.*\.env\b", ".env sourcing"),
    (r"\bcat\b.*\.env\b", ".env read via cat"),
    (r"\bgrep\b.*\.env\b", ".env read via grep"),
    (r"\bhead\b.*\.env\b", ".env read via head"),
    (r"\btail\b.*\.env\b", ".env read via tail"),
    (r"\bless\b.*\.env\b", ".env read via less"),
    (r"\bmore\b.*\.env\b", ".env read via more"),
    (r"\bawk\b.*\.env\b", ".env read via awk"),
    (r"\bsed\b.*\.env\b", ".env read via sed"),
    # Credential variables in curl commands
    (r"\bcurl\b.*(?:_SECRET|_TOKEN|_KEY)\s*=", "credential in curl argument"),
    (r"\bcurl\b.*(?:client_secret|refresh_token|api_key)\s*=", "credential in curl argument"),
    # Auth headers with variable expansion
    (r"\bcurl\b.*-H\s*[\"']?Authorization.*\$", "auth header with variable expansion"),
    # Echo/export of credential variables
    (r"\becho\b.*\$\{?(?:.*(?:SECRET|TOKEN|API_KEY))", "credential echo"),
    (r"\bexport\b.*(?:SECRET|TOKEN|API_KEY)\s*=", "credential export"),
    # Piping .env content
    (r"\.env\b.*\|", ".env piped to command"),
]


def check_bash_command(command: str) -> str | None:
    """Check if a Bash command would expose credentials. Returns reason or None."""
    for pattern, reason in BASH_BLOCK_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return reason
    return None


# --- Read Tool Check ---

def check_read_tool(tool_input: dict) -> str | None:
    """Block Read tool access to .env files."""
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return None
    basename = os.path.basename(file_path)
    if basename == ".env" or (
        basename.startswith(".env.")
        and not basename.endswith((".example", ".template", ".sample"))
    ):
        return f".env file read blocked ({basename})"
    return None


# --- Grep Tool Check ---

def check_grep_tool(tool_input: dict) -> str | None:
    """Block Grep tool searches in .env files."""
    path = tool_input.get("path", "")
    if not path:
        return None
    basename = os.path.basename(path)
    if basename == ".env" or (
        basename.startswith(".env.")
        and not basename.endswith((".example", ".template", ".sample"))
    ):
        return f".env file grep blocked ({basename})"
    return None


# --- Main ---

def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)  # Can't parse -> allow (must not cause false blocks)

    tool_name = payload.get("tool_name") or payload.get("toolName", "")
    tool_input = payload.get("tool_input") or payload.get("toolInput", {})

    reason = None
    detail = ""

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if command:
            reason = check_bash_command(command)
            if reason:
                detail = command
    elif tool_name == "Read":
        reason = check_read_tool(tool_input)
        if reason:
            detail = tool_input.get("file_path", "")
    elif tool_name == "Grep":
        reason = check_grep_tool(tool_input)
        if reason:
            detail = tool_input.get("path", "")

    if reason:
        log_blocked(tool_name, reason, detail)
        print(f"SECURITY BLOCKED: {reason}")
        print("Use credential-isolated wrapper scripts for API access.")
        print("If you need to modify .env, ask the user to do it manually.")
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
