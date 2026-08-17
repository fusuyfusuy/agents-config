# agents-config

My personal config for running AI coding agents (Claude Code, Antigravity / Gemini CLI) across machines: shared operating principles, a lightweight project-memory CLI, tmux status integration, and editor/CLI settings — all kept in one repo and symlinked into place.

Published for reference, not as a product. It's opinionated, it changes whenever it suits me, and parts of it (paths, hostnames, trusted workspaces) are specific to my machine. Read before you symlink — don't run it blind.

## Layout

| Path | What it is |
| :--- | :--- |
| `AGENTS.md` | Core rules doc — symlinked to `~/.claude/CLAUDE.md` and `~/.gemini/AGENTS.md`. Operating principles, subagent management protocol, project memory protocol, and "Ponytail" lazy-dev mode. |
| `PROCESSES.md` | How-to recipes backing `AGENTS.md`: git worktree isolation, the error knowledge base. |
| `bin/agent-ctx` | Zero-daemon, stdlib-only CLI for per-project memory, an AST-derived symbol map, and an activity log, stored in each target repo's `.agents/` directory. |
| `bin/agent-kb/` | Zero-daemon CLI + SQLite-backed error knowledge base (`agent-kb`) — error-signature fingerprinting and fuzzy lookup for previously-resolved runtime errors. Has its own `pyproject.toml`/`uv.lock`; `setup.sh` builds its venv. |
| `claude/` | Claude Code `settings.json`, statusline command, and skills (`agent-context`, `agent-processes`, `agent-error-kb`). |
| `status/` | Statusline scripts for Antigravity / Gemini CLI (quota, branch, context usage). |
| `tmux/plugins/tmux-agent-quotas/` | tmux plugin showing live Antigravity + Claude Code quota remaining in the status bar. |
| `antigravity-cli/`, `config/` | Antigravity / Gemini CLI settings, keybindings, MCP server config. |
| `setup.sh` | Symlink installer — see below. |

## Install

```bash
./setup.sh
```

Symlinks everything into place under `$HOME` (`~/.claude`, `~/.gemini`, `~/.antigravity`, `~/.local/bin`, `~/.tmux/plugins`). If a target already exists and isn't one of these symlinks, it's backed up (`.bak.<timestamp>`) rather than overwritten. Safe to re-run.

## Philosophy

`AGENTS.md` is the actual source of truth; the short version:

- No backward-compatibility shims — remove obsolete paths instead of layering fallbacks.
- Grow in layers: smallest thing that works end to end, then build on top of it.
- **Ponytail mode**: before writing code, climb a ladder — does this need building at all, does it already exist in the codebase, does the stdlib/platform/an existing dependency cover it, can it be one line — and only then write the minimum that works. Lazy means efficient, not careless.
- Subagents get delegated broad exploration and multi-file work, but must report back a summary, never raw output.

## `agent-ctx`

Run inside any project (not just this repo) to give an agent fast, cheap context before it starts grepping around:

```bash
agent-ctx init   # scaffold .agents/{memory,decisions,repo_map}.md + activity.jsonl
agent-ctx dump   # print memory + decisions + a freshly-generated symbol map + recent activity
agent-ctx log --action "..." --summary "..." --files "a.py,b.py"
```

Zero dependencies, zero background service — everything lives in flat files under the target repo's `.agents/`.

## `agent-kb`

Error-signature knowledge base backing the `agent-error-kb` skill — lookup verified fixes for errors you've hit before instead of re-debugging from scratch:

```bash
agent-kb lookup "<error_log_or_stacktrace>"
agent-kb record --error "..." --cause "..." --fix "..." --tags "a,b"
agent-kb patterns
```

SHA-256 exact-fingerprint matching plus token/n-gram fuzzy similarity over a local SQLite DB (`~/.agent-kb/kb.db`). Trimmed down from its original form before moving in here — the original also had an MCP server mode, but it didn't actually work against the current `mcp` SDK and had never been exercised, so it was dropped rather than carried over broken.

## Notes if you're browsing or forking this

- `antigravity-cli/settings.json` and `config/config.json` contain my machine's trusted-workspace paths and hostname — irrelevant noise if you're not me, don't copy them verbatim.
- No license is attached. Treat this as read-only reference rather than something to redistribute.
