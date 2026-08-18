# agents-config

A unified configuration and tooling suite for running AI coding agents (Claude Code, Antigravity / Gemini CLI) across machines: shared operating principles, zero-daemon project memory & AST mapping, error knowledge sharing, live tmux status integration, and Mosh-optimized alert dispatching.

---

## Layout

| Path | Description |
| :--- | :--- |
| [`AGENTS.md`](AGENTS.md) | Core operating rules: subagent management protocol, project memory protocol, and "Ponytail" lazy-dev mode. Symlinked to `~/.gemini/AGENTS.md` and `~/.claude/CLAUDE.md`. |
| [`PROCESSES.md`](PROCESSES.md) | Concrete how-to recipes backing `AGENTS.md` (worktree isolation, error KB workflow, memory lifecycle). |
| [`bin/agent-ctx`](bin/agent-ctx) | Zero-daemon, stdlib-only CLI for AST-derived ranked symbol maps, project memory, and activity logging. |
| [`bin/agent-kb/`](bin/agent-kb/) | Zero-daemon SQLite-backed error knowledge base CLI (`agent-kb`) with exact fingerprinting and token similarity search. |
| [`tmux/plugins/tmux-agent-quotas/`](tmux/plugins/tmux-agent-quotas/) | Tmux plugin displaying live Antigravity and Claude Code subscription quotas in the status bar. |
| [`tmux/plugins/tmux-agent-alert/`](tmux/plugins/tmux-agent-alert/) | Tmux plugin & hooks alerting via Mosh terminal bell, status flash, statusline badge, and `<prefix> A` focus jump when agents wait for input. |
| [`status/`](status/) | Statusline scripts and live quota monitors for Antigravity / Gemini CLI. |
| [`claude/`](claude/) | Claude Code settings (`settings.json`), statusline script, and agent skills (`agent-context`, `agent-processes`, `agent-error-kb`). |
| [`antigravity-cli/`, `config/`](antigravity-cli/) | Antigravity / Gemini CLI settings, keybindings, and MCP server configuration. |
| [`setup.sh`](setup.sh) | Symlink installer script. |

---

## Installation

Run the setup script to symlink all configurations, skills, binaries, and plugins into `$HOME`:

```bash
./setup.sh
```

- Symlinks files under `~/.claude`, `~/.gemini`, `~/.antigravity`, `~/.local/bin`, and `~/.tmux/plugins`.
- If an existing target file is not already symlinked, it is backed up to `<target>.bak.<timestamp>`.
- Builds the Python venv for `agent-kb` via `uv` or `python3 -m venv`.
- Safe to re-run at any time.

---

## Philosophy & Operating Principles

All agents running under this configuration adhere to [`AGENTS.md`](AGENTS.md):

1. **No backward-compatibility shims**: Remove obsolete paths cleanly instead of layering migrations or fallbacks.
2. **Grow in layers**: Build the smallest version that works end-to-end first, then add capabilities incrementally.
3. **Ponytail (Lazy Senior Dev) ladder**:
   - Does this need to be built at all? (YAGNI)
   - Does a helper or pattern already exist in the codebase?
   - Does the standard library or platform feature already cover it?
   - Can this be one line?
   - Only then: write the minimum code that works.
4. **Subagent Protocol**: Keep the main context lean. Delegate multi-file exploration to subagents and require concise, structured summaries back.

---

## Tooling Guides

### 1. `agent-ctx` — Project Context & Symbol Map CLI

[`bin/agent-ctx`](bin/agent-ctx) provides fast, zero-daemon orientation for agents entering any repository:

```bash
# Scaffold .agents/ directory (memory.md, decisions.md, repo_map.md, activity.jsonl)
agent-ctx init

# One-shot context dump: working state, memory, ADRs, ranked symbol map, and activity
agent-ctx dump

# Generate or refresh AST repository symbol map
agent-ctx map

# Log a completed task or decision
agent-ctx log --action "add-auth" --summary "Added OAuth2 middleware" --files "auth.py,server.py"

# Inspect recent session activity
agent-ctx history --limit 5

# Run self-tests
agent-ctx --test
```

**Key Features:**
- **Ranked Orientation**: Files are scored and ranked by import in-degree (AST-parsed Python and JS/TS path aliases), commit churn, and entry points rather than alphabetical order.
- **Structural Budgeting**: `agent-ctx dump` respects token budgets (`--budget default|large|immense|unlimited`) and degrades gracefully: memory invariants $\rightarrow$ ADR titles $\rightarrow$ ranked map $\rightarrow$ collapsed directory summaries.
- **Zero Daemon**: Pure Python standard library with no external dependencies.

---

### 2. `agent-kb` — Error Knowledge Base CLI

[`bin/agent-kb/`](bin/agent-kb/) provides an error-signature knowledge base stored in a local SQLite database (`~/.agent-kb/kb.db`):

```bash
# Search for verified fixes for an error or stack trace
agent-kb lookup "fatal: Unable to create '.git/index.lock': File exists"

# Record a verified fix once resolved
agent-kb record \
  --error "fatal: Unable to create '.git/index.lock': File exists" \
  --cause "Stale lockfile left behind by crashed subprocess" \
  --fix "pgrep -f 'git ' || rm -f .git/index.lock" \
  --tags "git,lockfile,concurrency"

# List top recurring error patterns
agent-kb patterns
```

**Key Features:**
- **Hybrid Matching**: Combines SHA-256 exact fingerprint matching with token and n-gram fuzzy similarity.
- **Shared Context**: Accessible by both Antigravity CLI and Claude Code across all workspace sessions.

---

### 3. `tmux-agent-quotas` — Subscription Quota Monitor

[`tmux/plugins/tmux-agent-quotas/`](tmux/plugins/tmux-agent-quotas/) monitors live remaining subscription quotas in the tmux status bar.

Add to `~/.tmux.conf`:
```tmux
set -g status-right "#{agent_quotas} #[bold]#[fg=colour255]│ #(date +%H:%M) #[default]"
run-shell ~/.tmux/plugins/tmux-agent-quotas/tmux-agent-quotas.tmux
```

**Interpolations:**
- `#{agy_quota}`: Antigravity primary model quota and reset countdown.
- `#{claude_quota}`: Claude Code 5-hour rolling and 7-day quota percentages.
- `#{agent_quotas}`: Combined formatted quota block with color-coded thresholds.

---

### 4. `tmux-agent-alert` — Mosh & Tmux Alert Dispatcher

[`tmux/plugins/tmux-agent-alert/`](tmux/plugins/tmux-agent-alert/) alerts you when an AI agent or background pane is waiting for user input.

Add to `~/.tmux.conf`:
```tmux
set -g status-right "#{agent_alerts}#{agent_quotas} #[bold]#[fg=colour255]│ #(date +%H:%M) #[default]"
run-shell ~/.tmux/plugins/tmux-agent-alert/tmux-agent-alert.tmux
```

**Key Features:**
- **Mosh Bell Forwarding**: Emits ASCII `\a` (BEL) to attached client TTYs so Mosh triggers local terminal audio/visual bells (Ghostty, iTerm2, Kitty, WezTerm, Alacritty).
- **Statusline Badge**: Shows `#{agent_alerts}` when panes require attention (e.g. `🔔 WAITING [1:agy]`).
- **Instant Focus Jump**: Press `<prefix> A` to switch directly to the waiting window and pane.
- **Auto-Clearing**: Alerts dismiss automatically as soon as you focus the pane.
- **Push Notifications**: Optional [ntfy.sh](https://ntfy.sh) or custom webhook integration.

---

### 5. Statusline Visualizations

- **Antigravity ([`status/statusline.sh`](status/statusline.sh))**: Renders agent state (`READY`, `THINKING`, `WORKING`, `TOOL`), active git branch, model name, fine-grained Unicode context bar, subagent count, task count, and sandbox status.
- **Claude Code ([`claude/statusline-command.sh`](claude/statusline-command.sh))**: Displays workspace path, git branch/dirty state, model, context usage %, and rolling rate limit resets.
