# 🤖 Agent Error Knowledge Base (`agent-error-kb`)

A **Zero-Service, Zero-Daemon, Lightweight Agent Knowledge Sharing Platform** designed for AI agents.

## 🎯 Key Features

- 🧠 **Instant Error Lookup**: Lookup verified solutions for runtime errors, stack traces, and environment blockers using SHA-256 exact fingerprint matching plus token/n-gram fuzzy similarity.
- ⚡ **Zero-Daemon Architecture**: No background HTTP servers or background processes required. Runs directly as a CLI binary (`agent-kb`).
- 💾 **Shared Local Database**: Default database at `~/.agent-kb/kb.db` (auto-creates and auto-seeds if missing, accessible to all agents and users).

---

## 🛠️ Installation & Executable

Installed via this repo's `setup.sh`, which runs `uv sync` here to create `.venv/` and symlinks the resulting `.venv/bin/agent-kb` console script to `~/.local/bin/agent-kb`.

---

## 🚀 CLI Commands

### 🔍 Lookup Error Solutions
```bash
agent-kb lookup "fatal: Unable to create '.git/index.lock': File exists"
```

### ➕ Record New Error Fix
```bash
agent-kb record \
  --error "fatal: Unable to create '.git/index.lock': File exists" \
  --cause "Stale lockfile left behind by crashing subagent" \
  --fix "pgrep -f 'git ' || rm -f .git/index.lock" \
  --tags "git,lockfile,concurrency"
```

### 📊 List Recurring Patterns
```bash
agent-kb patterns
```
