# agents-config

A unified configuration and tooling suite for running AI coding agents (Claude Code, Antigravity / Gemini CLI) across machines: shared operating principles, zero-daemon project memory & AST mapping, error knowledge sharing, live tmux status integration, and Mosh-optimized alert dispatching.

---

## Layout

| Path | Description |
| :--- | :--- |
| [`tui-agent-settings/prompts/AGENTS.md`](tui-agent-settings/prompts/AGENTS.md) | Core operating rules: subagent management protocol, project memory protocol, and "Ponytail" lazy-dev mode. Symlinked to `~/.gemini/AGENTS.md` and `~/.claude/CLAUDE.md`. |
| [`tui-agent-settings/prompts/PROCESSES.md`](tui-agent-settings/prompts/PROCESSES.md) | Concrete how-to recipes backing `AGENTS.md` (worktree isolation, error KB workflow, memory lifecycle). |
| [`tui-agent-settings/skills/`](tui-agent-settings/skills/) | Shared skill definitions (`agent-context`, `agent-error-kb`, `agent-processes`, `code-summary`), each `SKILL.md` co-located with its backing script where it has one (`agent-context/agent-ctx`, `agent-error-kb/agent-kb/`). Fanned out to all three harnesses by `setup.sh`. |
| [`tui-agent-settings/tmux/plugins/tmux-agent-quotas/`](tui-agent-settings/tmux/plugins/tmux-agent-quotas/) | Tmux plugin displaying live Antigravity and Claude Code subscription quotas in the status bar. |
| [`tui-agent-settings/tmux/plugins/tmux-agent-alert/`](tui-agent-settings/tmux/plugins/tmux-agent-alert/) | Tmux plugin & hooks alerting via Mosh terminal bell, status flash, statusline badge, and `<prefix> A` focus jump when agents wait for input. |
| [`tui-agent-settings/claude/`](tui-agent-settings/claude/) | Claude Code settings (`settings.json`) and statusline script. |
| [`tui-agent-settings/antigravity-cli/`](tui-agent-settings/antigravity-cli/) | Antigravity / Gemini CLI settings, keybindings, MCP server configuration, and statusline/quota scripts. |
| [`tui-agent-settings/pi/`](tui-agent-settings/pi/) | pi extensions (`gated-tools.ts`, `compact-tools.ts`), manually synced with `~/.pi/agent/extensions/`. |
| [`setup.sh`](setup.sh) | Interactive installer: detects installed agents (Claude Code, AGY, pi), asks which to configure, then symlinks each agent's config, skills, binaries, and plugins. |

---

## Installation

Run the setup script to symlink all configurations, skills, binaries, and plugins into `$HOME`:

```bash
./setup.sh
```

`setup.sh` detects which agents are installed on the machine (Claude Code, AGY / Antigravity-Gemini, pi) and asks which ones to configure:

```
==> Detected agents:
    [c] Claude Code              : installed
    [a] AGY (Antigravity/Gemini)  : installed
    [p] pi                       : installed

Which agents should I configure here?
  Enter letters to select (e.g. 'cap'), 'all', 'none', or leave blank for all detected:

Optional tmux integration:
  [p] plugins    : symlink tmux-agent-quotas + tmux-agent-alert into ~/.tmux/plugins
  [s] statusline : append the agent status bar + plugin hooks to ~/.tmux.conf
  Enter letters (e.g. 'ps'), 'all', 'none', or leave blank for all:
```

- Enter letters to configure exactly those agents, `all` / blank for every detected agent, or `none` for shared tooling only (CLI binaries, `agent-kb` always install).
- The tmux prompt asks separately about **plugins** (`p`) and **statusline** (`s`). Choosing the statusline auto-installs the plugins it renders against; `none`/blank-for-all behave the same as for agents.
- Non-interactive: with `AGENTS` you override the agent prompt; with `TMUX_SETUP=ps|all|none` you override the tmux prompt. Without a TTY (piped/CI) both defaults install everything detected and never hang on `read`.
- The statusline block is appended to `~/.tmux.conf` behind a marker line, so re-running setup is idempotent and existing config is never rewritten.
- Symlinks files under `~/.claude`, `~/.gemini`, `~/.antigravity`, `~/.pi/agent` (pi global instructions + skills), `~/.local/bin`, and `~/.tmux/plugins`.
- If an existing target file is not already symlinked, it is backed up to `<target>.bak.<timestamp>`.
- Builds the Python venv for `agent-kb` via `uv` or `python3 -m venv`.
- Safe to re-run at any time.

---

## Philosophy & Operating Principles

All agents running under this configuration adhere to [`AGENTS.md`](tui-agent-settings/prompts/AGENTS.md):

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

[`tui-agent-settings/skills/agent-context/agent-ctx`](tui-agent-settings/skills/agent-context/agent-ctx) provides fast, zero-daemon orientation for agents entering any repository:

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

[`tui-agent-settings/skills/agent-error-kb/agent-kb/`](tui-agent-settings/skills/agent-error-kb/agent-kb/) provides an error-signature knowledge base stored in a local SQLite database (`~/.agent-kb/kb.db`):

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

[`tui-agent-settings/tmux/plugins/tmux-agent-quotas/`](tui-agent-settings/tmux/plugins/tmux-agent-quotas/) monitors live remaining subscription quotas in the tmux status bar.

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

[`tui-agent-settings/tmux/plugins/tmux-agent-alert/`](tui-agent-settings/tmux/plugins/tmux-agent-alert/) alerts you when an AI agent or background pane is waiting for user input.

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

### 5. pi (Coding Agent)

`setup.sh` configures [pi](https://pi.dev) — the terminal coding harness used in this repo — by fanning out the same shared resources it installs for Claude Code and AGY:

- `tui-agent-settings/prompts/AGENTS.md` → `~/.pi/agent/AGENTS.md` (pi global instructions)
- `tui-agent-settings/skills/*` → `~/.pi/agent/skills/` (pi discovers `SKILL.md` directories there)

The skills (`agent-context`, `agent-error-kb`, `agent-processes`, `code-summary`) work unchanged across all three harnesses; pi's model/provider settings live in `~/.pi/agent/settings.json`.

### 6. Statusline Visualizations

- **Antigravity ([`tui-agent-settings/antigravity-cli/statusline.sh`](tui-agent-settings/antigravity-cli/statusline.sh))**: Renders agent state (`READY`, `THINKING`, `WORKING`, `TOOL`), active git branch, model name, fine-grained Unicode context bar, subagent count, task count, and sandbox status.
- **Claude Code ([`tui-agent-settings/claude/statusline-command.sh`](tui-agent-settings/claude/statusline-command.sh))**: Displays workspace path, git branch/dirty state, model, context usage %, and rolling rate limit resets.
