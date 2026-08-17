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

`dump` and `map` both accept `--budget <chars|default|large|immense>` (or the `AGENT_CTX_BUDGET` env var). `large` is 60 000 chars, `immense` is 200 000.

A bigger budget costs **tokens, not time** — generation is flat regardless — and it saturates: past the point where every ranked file is already detailed, extra budget buys nothing. On a small-to-mid repo `large` and `immense` are often byte-identical to each other. Reach for a bigger budget when you need broad coverage of an unfamiliar large repo; stay on `default` for routine work, since an oversized dump crowds the context it is meant to save.

When the budget binds, degradation is by priority and nothing vanishes silently:

- **Memory** keeps invariants and gotchas ahead of status/epics; an oversized top-priority section is truncated rather than dropped.
- **Decisions** always list **every ADR title**, expanding bodies newest-first — so you always know which decisions exist and can read any body from the file.
- **Map** collapses lower-ranked files by directory and reports the counts.

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
