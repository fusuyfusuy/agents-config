# Agent Processes

Concrete recipes supporting the Subagent Management Protocol in [`AGENTS.md`](AGENTS.md). Read that first for the rules — this doc is the how-to.

---

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

## Installed Skills & Config

| File | Purpose |
| :--- | :--- |
| `AGENTS.md` | Core operating principles and subagent management protocol. |
| `claude/skills/agent-error-kb/SKILL.md` | `agent-kb` lookup/record reference. |
| `claude/skills/agent-processes/SKILL.md` | Condensed, triggerable form of this doc. |
| `status/status.py`, `status/statusline.sh` | Statusline: quota, branch, context usage. |
