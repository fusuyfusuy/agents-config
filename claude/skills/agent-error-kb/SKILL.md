---
name: agent-error-kb
description: Zero-service, zero-daemon error knowledge base for runtime errors, git locks, database locks, permission errors, rate limits, and tool execution failures. Use this whenever you hit an unhandled exception, subprocess failure, or environment blocker during a task — look up whether it's a known pattern with a verified fix before debugging from scratch, and record the fix once resolved so future sessions reuse it.
---

# Agent Error Knowledge Base (agent-kb)

`agent-kb` gives instant error-signature matching against verified, previously-recorded fixes stored in a local shared SQLite database (`~/.agent-kb/kb.db`). No background service — every command is a direct one-shot CLI call.

## When to use

Reach for this the moment you hit any of these (or similar) during a task, before spending time debugging from scratch:

- Git repository locks: `fatal: Unable to create '.git/index.lock': File exists`
- SQLite database locks: `sqlite3.OperationalError: database is locked`
- Permission/EACCES errors: `EACCES: permission denied, mkdir '/usr/local/lib/node_modules'`, `/var/run/docker.sock`
- Subprocess timeouts: `subprocess.TimeoutExpired: Command 'git log' timed out`
- Virtual environment / import failures: `ModuleNotFoundError: No module named 'fastapi'`
- API quota / rate limit errors: `openai.RateLimitError: 429 - Rate limit reached`
- OOM crashes: `SIGKILL - Out of Memory (OOM)`
- JSON tool-output parsing errors: `JSONDecodeError: Expecting value: line 1 column 1`
- Sandbox path traversal blocks: `ValueError: Path outside workspace sandbox root`

## Lookup

```bash
agent-kb lookup "<error_log_or_stacktrace>"
agent-kb lookup "sqlite3.OperationalError: database is locked" --format json
```

If a match comes back, verify it actually applies to the current situation before applying it blindly — the KB stores prior fixes, not guarantees.

## Record a new fix

Once you've resolved an error that wasn't already in the KB (or resolved it differently than the recorded fix), record it so future sessions — yours or the user's other agents — don't re-derive it:

```bash
agent-kb record \
  --error "fatal: Unable to create '.git/index.lock': File exists" \
  --cause "Stale lockfile left behind by a crashed subprocess" \
  --fix "pgrep -f 'git ' || rm -f .git/index.lock" \
  --tags "git,lockfile,concurrency"
```

## Other commands

```bash
agent-kb patterns          # list top recurring error pattern tags
agent-kb seed               # pre-populate with 12 real-world AI agent error records (only if the DB is empty)
```

## Notes

- Binary: `~/.local/bin/agent-kb` (already on PATH). It's a thin wrapper around `~/projects/agent-error-kb/backend/cli.py` run through that project's own `.venv`.
- Shared across tools: this same KB is also used by the Antigravity/Gemini CLI setup on this machine (`agents-config` repo) — fixes recorded here are visible there too, and vice versa.
- An MCP server mode also exists (`agent-kb mcp`, stdio JSON-RPC) if you want it wired in as an MCP tool instead of shelling out — not configured by default here.
