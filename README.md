# Claude Code Security Guard

A PreToolUse hook that prevents Claude Code from accessing your credentials.

## The Problem

Claude Code automatically reads `.env` files. Any API keys, tokens, or secrets in the LLM context are a security risk - prompt injection, accidental logging, or the agent creatively building curl commands with your credentials.

For background:
- [Claude Code loads .env secrets without permission](https://www.knostic.ai/blog/claude-loads-secrets-without-permission) (Knostic)
- [Claude Code ignores ignore rules meant to block secrets](https://www.theregister.com/2026/01/28/claude_code_ai_secrets_files/) (The Register)

## The Solution

A 150-line Python script that runs **before every tool execution** and blocks credential access:

| Tool | What's blocked |
|------|---------------|
| **Bash** | `source .env`, `cat .env`, `grep .env`, credential variables in curl, auth header expansion |
| **Read** | Any `.env` file (allows `.env.example`, `.env.template`) |
| **Grep** | Searching inside `.env` files |

The agent still gets API access - through **wrapper scripts** that source `.env` internally. The LLM sees structured output, never the keys.

```
┌─────────────┐     ┌──────────────────┐     ┌─────────┐
│ Claude Code  │────▶│ security_guard.py │────▶│  Tool   │
│  (LLM)      │     │  (PreToolUse)     │     │ Execute │
└─────────────┘     └──────────────────┘     └─────────┘
       │                    │
       │              BLOCKED if .env
       │                    │
       ▼                    ▼
┌─────────────┐     ┌──────────────────┐
│ wrapper.sh  │────▶│  .env (sourced   │
│ (Bash call) │     │   internally)    │
└─────────────┘     └──────────────────┘
       │
       ▼
  Structured output
  (LLM sees this, not the keys)
```

## Setup (2 minutes)

### 1. Copy the hook

```bash
cp security_guard.py /path/to/your/project/.claude/hooks/
```

### 2. Add to your project's `.claude/settings.json`

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 $CLAUDE_PROJECT_DIR/.claude/hooks/security_guard.py",
            "timeout": 5000
          }
        ]
      }
    ]
  }
}
```

### 3. Done

The hook runs automatically before every tool call. No restart needed.

## How Wrapper Scripts Work

Instead of letting the agent read `.env` directly, create wrapper scripts:

```bash
#!/usr/bin/env bash
# scripts/my-api.sh - credential-isolated wrapper

source "$(dirname "$0")/../.env"  # credentials stay in this process

case "${1:-}" in
  fetch)
    curl -s -H "Authorization: Bearer $API_KEY" \
      "https://api.example.com/data"
    ;;
esac
```

The agent calls `./scripts/my-api.sh fetch` and gets JSON back. It never sees `$API_KEY`.

See `example-wrapper.sh` for a complete template.

## What Happens When Something Is Blocked

The agent sees:
```
SECURITY BLOCKED: .env sourcing
Use credential-isolated wrapper scripts for API access.
If you need to modify .env, ask the user to do it manually.
```

All blocks are logged to `~/.claude-security/security-guard.log`:
```
[2026-02-22T08:30:00+0100] BLOCKED | session=abc123 | tool=Bash | reason=.env sourcing | detail=source .env && curl...
```

## Defense in Depth

This hook is one layer. Combine with:

- **`.claude/settings.json` permissions** - restrict which tools are auto-allowed
- **Wrapper scripts** - the agent gets data without seeing credentials
- **Audit log** - review what was blocked and when

Even if a prompt injection tells the agent to "read the .env file", the hook blocks it. It runs outside the LLM context - the agent can't bypass it.

## Customization

**Add your own patterns** to `BASH_BLOCK_PATTERNS`:

```python
BASH_BLOCK_PATTERNS = [
    # ... existing patterns ...
    (r"\bmy-custom-secret\b", "custom secret access"),
]
```

**Change the log directory**:

```python
LOG_DIR = Path.home() / ".my-project" / "security-logs"
```

**Disable logging**:

```python
LOG_DIR = None
```

## Requirements

- Python 3.10+ (for `str | None` type hints, or change to `Optional[str]` for 3.9)
- Claude Code with hooks support

## License

MIT
