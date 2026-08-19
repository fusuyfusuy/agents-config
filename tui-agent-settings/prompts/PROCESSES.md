# Agent Processes

Concrete recipes supporting the Subagent Management Protocol in [`AGENTS.md`](AGENTS.md). Read that first for the rules — this doc is the how-to.

---

## Change Protocol (Explore → Plan → Approve → Execute)

Rule in [`AGENTS.md`](AGENTS.md). Only non-trivial work (multi-file or non-trivial logic) goes through the gate; one-liners execute directly.

- Present a one-paragraph plan before editing: **files**, **approach**, **verification**.
- Wait for explicit approval; re-present if the approved scope changes.
- Execute the smallest change, run the check, report the result.

Example plan:

> Touch `collect_agent_usage.py` (add `parse_x` mirroring `parse_y`) and `test_collect_agent_usage.py` (one fixture). Verify: `python3 test_collect_agent_usage.py`.

## Workspace Isolation (Git Worktrees)

For parallel or isolated work, use a dedicated worktree instead of the primary working directory:

```bash
git worktree add -b agent/task-<id> ../worktrees/task-<id> origin/main
cd ../worktrees/task-<id>

# verify locally (typecheck/lint/test), then hand off a patch:
git diff origin/main...HEAD > /tmp/task-<id>.patch

git worktree remove ../worktrees/task-<id>
```

---

## Error Knowledge Base (`agent-kb`)

Before debugging a runtime/tool/git/environment error from scratch, check for a known fix:

```bash
agent-kb lookup "<error_log_or_stacktrace>"
```

Once resolved — and not already in the KB, or resolved differently — record it so future sessions reuse it:

```bash
agent-kb record \
  --error "<exact_error_message>" \
  --cause "<root_cause_explanation>" \
  --fix "<verified_command_or_fix>" \
  --tags "<comma_separated_tags>"
```

---

## Project Context & Memory (`agent-ctx`)

Before exploratory code grepping across repos, load the project snapshot or symbol map:

```bash
agent-ctx dump       # Snapshot: memory, ADRs, repo map, recent activity
agent-ctx map        # Refresh AST symbol map in .agents/repo_map.md
```

After completing non-trivial tasks or architectural changes, log activity and update memory:

```bash
agent-ctx log \
  --action "<action_name>" \
  --summary "<short_rationale_and_summary>" \
  --files "<comma_separated_files>"
```

---

## Installed Skills & Config

| File / Component | Purpose |
| :--- | :--- |
| `prompts/AGENTS.md` | Core operating principles, subagent protocol, and Ponytail lazy-dev mode. |
| `skills/agent-error-kb/SKILL.md` | `agent-kb` lookup/record reference. |
| `skills/agent-context/SKILL.md` | `agent-ctx` project memory, mapping & activity tracking. |
| `skills/agent-processes/SKILL.md` | Condensed, triggerable form of this doc. |
| `skills/agent-context/agent-ctx` | Zero-daemon CLI for project memory and symbol mapping. |
| `skills/agent-error-kb/agent-kb/` | Zero-daemon CLI + SQLite-backed error knowledge base (`agent-kb`). |
| `tmux/plugins/tmux-agent-quotas/` | Live Antigravity + Claude Code quota tracking in tmux status bar. |
| `tmux/plugins/tmux-agent-alert/` | Tmux alert dispatcher (Mosh bell, status flash, instant focus jump). |
| `antigravity-cli/status.py`, `antigravity-cli/statusline.sh` | Statusline: quota, branch, context usage, and state alerts. |

(All paths above are relative to `tui-agent-settings/`.)


