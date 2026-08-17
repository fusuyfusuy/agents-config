---
name: agent-context
description: Zero-daemon project memory, structural symbol mapping, and activity tracking CLI (`agent-ctx`). Use at the start of any session to inspect repo structure and architecture invariants without costly exploratory searches, and use at completion to record architecture decisions and log tasks.
---

# Agent Context & Memory (agent-ctx)

`agent-ctx` provides zero-daemon project memory, AST repository mapping, and session activity tracking stored directly within `.agents/` inside the target workspace.

## 1. Fast Warmup / Startup

Before performing multi-file discovery or broad grepping, inspect the project's memory, decisions, and structural symbol map:

```bash
agent-ctx dump
```

To refresh or view only the AST repository symbol map:

```bash
agent-ctx map
agent-ctx map --stdout
```

## 2. Initialize a Project

To set up the `.agents/` directory structure (`memory.md`, `decisions.md`, `repo_map.md`, `activity.jsonl`) in a new or existing repository:

```bash
agent-ctx init
```

## 3. Persistent Memory & Architectural Decisions

- **`.agents/memory.md`**: Update this file when discovering non-obvious domain rules, active epic milestones, or subtle edge-case gotchas.
- **`.agents/decisions.md`**: Record new Architecture Decision Records (ADRs) explaining *Context*, *Decision*, and *Consequences* when introducing new architectural patterns.

## 4. Log Task Activity & Telemetry

When finishing a task or major milestone, log the action with its touched files and summary:

```bash
agent-ctx log \
  --action "refactor-auth" \
  --summary "Migrated token validation to unified middleware and added unit test check" \
  --files "auth.py,middleware.py,test_auth.py"
```

To inspect recent activities across sessions:

```bash
agent-ctx history --limit 5
```
