# tmux-agent-quotas

A lightweight, non-blocking tmux plugin that displays real-time remaining subscription quotas for **Antigravity (`agy`)** and **Claude Code (`claude`)** in your tmux status bar.

---

## Features

- **Non-blocking Status Updates**: Tmux status rendering never waits for network or IPC calls (sub-millisecond `cat` from atomic cache).
- **Dual Support**:
  - **Antigravity (`agy`)**: Probes active Language Server or cached `/usage` model quotas (Gemini 2.5 Pro, Claude 3.7 Sonnet, etc.) with refresh timers.
  - **Claude Code**: Captures 5-hour rolling usage and 7-day quota percentages + reset timestamps.
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
# Use #{agy_quota}, #{claude_quota}, or #{agent_quotas}
set -g status-right "#{agent_quotas} | %H:%M"

# Run plugin
run-shell ~/.tmux/plugins/tmux-agent-quotas/tmux-agent-quotas.tmux
```

---

## Status Placeholders

| Placeholder | Output Example | Description |
| :--- | :--- | :--- |
| `#{agy_quota}` | `AGY 90% (2h 15m)` | Antigravity primary model quota & reset time |
| `#{claude_quota}` | `CC 5h 85%→18:00 7d 40%` | Claude Code 5h & 7d remaining quotas |
| `#{agent_quotas}` | `AGY 90% (2h) │ CC 5h 85% 7d 40%` | Combined status segment |
