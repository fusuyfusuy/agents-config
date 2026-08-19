# tmux-agent-quotas

A lightweight, non-blocking tmux plugin that displays real-time remaining subscription quotas for **Antigravity (`agy`)**, **Claude Code (`claude`)** and today's **pi spend ($)** in your tmux status bar.

---

## Features

- **Non-blocking Status Updates**: Tmux status rendering never waits for network or IPC calls (sub-millisecond `cat` from atomic cache).
- **Triple Support**:
  - **Antigravity (`agy`)**: Probes active Language Server or cached `/usage` model quotas. Surfaces the **active gating constraint** (the currently active session model's quota, or the lowest remaining quota bucket across models) with live reset timers.
  - **Claude Code**: Tracks 5-hour rolling sprint usage and 7-day weekly quota, automatically surfacing whichever constraint is tighter.
  - **Pi (`pi`)**: Today's total spend across all pi sessions, summed from per-message costs persisted in `~/.pi/agent/sessions/**.jsonl` (as computed by pi's own usage totals); resets at local midnight.
- **Adaptive Color Indicators**:
  - High quota remaining (> 50%): `#[fg=green]`
  - Medium quota remaining (20% - 50%): `#[fg=yellow]`
  - Low quota remaining (< 20%): `#[fg=red]`

---

## Installation

### With TPM (Tmux Plugin Manager)

Add the plugin to your `~/.tmux.conf`:

```tmux
set -g @plugin 'tmux-plugins/tpm'
# Local symlinked plugin path:
run-shell ~/.tmux/plugins/tmux-agent-quotas/tmux-agent-quotas.tmux
```

### Manual Installation (without TPM)

Clone or link the plugin directory, and add to your `~/.tmux.conf`:

```tmux
# Use #{agy_quota}, #{claude_quota}, #{pi_spend}, or #{agent_quotas}
set -g status-right "#{agent_quotas} | %H:%M"

# Run plugin
run-shell ~/.tmux/plugins/tmux-agent-quotas/tmux-agent-quotas.tmux
```

---

## Status Placeholders

| Placeholder | Output Example | Description |
| :--- | :--- | :--- |
| `#{agy_quota}` | `AGY 12% 2d22h` | Antigravity active gating quota (active model / lowest remaining) |
| `#{claude_quota}` | `CC 38% 28h34m` | Claude Code active gating (5h or 7d whichever is tighter) |
| `#{pi_spend}` | `PI $1.87` | Pi today's total spend across all sessions |
| `#{agent_quotas}` | `AGY 12% 2d22h │ CC 38% 28h34m │ PI $1.87` | Combined active gating status segment + pi spend |
