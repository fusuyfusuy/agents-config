---
name: agent-processes
description: Recipes for git worktree isolation and the agent-kb error knowledge base. Use when orchestrating multi-step or multi-agent coding work, setting up workspace isolation, or hitting a runtime/tool/git error before debugging it from scratch.
---

# Agent Processes

Recipes supporting the Subagent Management Protocol in `AGENTS.md` (read that first for the rules). Full detail: [`PROCESSES.md`](file:///home/devhax/projects/fusuyfusuy/agents-config/tui-agent-settings/prompts/PROCESSES.md).

## When to use

- Orchestrating multi-step or multi-agent coding tasks.
- Setting up workspace isolation to avoid concurrent write collisions.
- Hitting a runtime/tool/git error before debugging it from scratch.

## Workspace Isolation

```bash
git worktree add -b agent/task-<id> ../worktrees/task-<id> origin/main
cd ../worktrees/task-<id>
# verify locally, then:
git diff origin/main...HEAD > /tmp/task-<id>.patch
git worktree remove ../worktrees/task-<id>
```

## Error Knowledge Base (`agent-kb`)

```bash
agent-kb lookup "<error_log_or_stacktrace>"
agent-kb record --error "<msg>" --cause "<root_cause>" --fix "<fix>" --tags "<tags>"
```
