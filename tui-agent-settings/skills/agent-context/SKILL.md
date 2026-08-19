---
name: agent-context
description: Zero-daemon project memory, structural symbol mapping, and activity tracking CLI (`agent-ctx`). Use at the start of any session to inspect repo structure and architecture invariants without costly exploratory searches, and use at completion to record architecture decisions and log tasks.
---

# Agent Context & Memory (agent-ctx)

`agent-ctx` provides zero-daemon project memory, AST repository mapping, and session activity tracking stored directly within `.agents/` inside the target workspace.

## 1. Fast Warmup / Startup

Run this first, before any broad grepping or directory crawling:

```bash
agent-ctx dump
```

One call returns five things: **working state** (branch, uncommitted files, recent commits), **project memory**, **architecture decisions**, a **ranked symbol map**, and **recent activity**.

The map is regenerated live on every call, so it never serves stale cached data. Read it as an *orientation* layer, not an index:

- Files are ranked by import in-degree, recent commit churn, and entry-point detection — the top of the map is what matters in this repo, not what sorts first alphabetically.
- `← cli, db, kb_engine` on a file means those modules import it. That is the one thing `Grep` cannot give you in a single call.
- Symbols carry signatures and `:line` numbers, so you can `Read` with an offset instead of searching.
- Output is capped by a character budget. When lower-ranked files are collapsed, the map **says so explicitly** and gives the counts — if it doesn't say it was truncated, you are seeing everything.

Still use `Glob`/`Grep` for exact locations, call sites, and anything below the top-level symbols. The map tells you *where to look*; it does not replace searching.

To write a fresh copy of the map to `.agents/repo_map.md` (for humans or other tools browsing the repo), or print it without writing:

```bash
agent-ctx map
agent-ctx map --stdout
```

### Budget

**`agent-ctx map` is complete by default** — it writes `.agents/repo_map.md` or stdout for browsing, which costs disk, not context. Measured on real repos a full map runs **~40 tokens per file**, so it stays cheap into the hundreds of files. Pass `--budget <chars|large|immense>` to cap it on a very large repo.

**`agent-ctx dump` stays budgeted** (24 000 chars by default), because that output is spent directly on context. Override per call with `--budget <chars|default|large|immense|unlimited>` or the `AGENT_CTX_BUDGET` env var.

Raising a budget costs **tokens, not time** — generation is flat regardless — and it saturates: past the point where every ranked file is already detailed, extra budget buys nothing. Reach for a bigger `dump` budget when orienting in an unfamiliar large repo; stay on `default` for routine work, since an oversized dump crowds the context it is meant to save.

When a budget binds, degradation is by priority and nothing vanishes silently:

- **Memory** keeps invariants and gotchas ahead of status/epics; an oversized top-priority section is truncated rather than dropped.
- **Decisions** always list **every ADR title**, expanding bodies newest-first. An ADR marked `**Superseded by**: ...` is kept for history but never expanded, so the file can grow without the snapshot growing with it.
- **Map** collapses lower-ranked files by directory and reports the counts. Files with no parsed symbols are always summarized this way rather than listed individually, even at an unlimited budget — they are grouped, not dropped.
- **Recent Activity** (the last `agent-ctx log` entries) is capped separately so a verbose logger can't starve the map's share: long summaries and file lists are elided per-entry, and entries are dropped oldest-first if they still don't fit, with a `_N of M entries shown_` note.

### Focused Maps for a Task

Give the map a task lens instead of a global ranking: files matching any focus substring render in full detail **together with their direct import-graph neighbors** (importers and imports); everything else collapses to a directory summary.

```bash
agent-ctx map --stdout --focus "auth.py,server"
agent-ctx dump --focus "src/engine"
AGENT_CTX_FOCUS="auth,api" agent-ctx dump
```

Use it on large repos when you already know the area of a task — it is the cheap, task-conditioned substitute for a global dump. Budget rules still apply; truncation is still announced.

**New agents (fresh sessions, subagents) get focus automatically** when `AGENT_CTX_FOCUS` is exported in the shell they launch from: the standard warmup `agent-ctx dump` then produces a focused map without any extra flag. For a one-off child, pass `--focus` explicitly in the subagent's task text instead.

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
