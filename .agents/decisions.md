# Architecture Decisions (ADRs)

## Record Format
### [YYYY-MM-DD] ADR-Title
- **Context**: Why was this decision necessary?
- **Decision**: What was chosen?
- **Consequences**: What trade-offs or constraints follow?

### [2026-08-17] agent-ctx dump regenerates the symbol map live, never from cache
- **Context**: `dump` read the cached `.agents/repo_map.md` from disk. That file only updates when someone remembers to run `agent-ctx map`, so it silently drifted out of sync with the repo (missing an entire directory added in the very commit that last refreshed it) with no timestamp or signal telling an agent the data was stale. The `agent-context` skill tells agents to trust `dump`'s output over grepping, so stale data there is actively worse than no tool.
- **Decision**: `cmd_dump` now calls `generate_repo_map(root)` directly instead of reading `repo_map.md` from disk. The on-disk `repo_map.md` file (written by `init`/`map`) is kept only for humans/other tools browsing the repo directly.
- **Consequences**: `dump` is now immune to map staleness by construction, at the cost of a full repo walk on every `dump` call instead of a file read. Acceptable since `generate_repo_map` is a plain `os.walk` with no external calls. `.agents/activity.jsonl` was also un-ignored (previously caught by the repo's blanket `*.jsonl` gitignore rule) so the activity log — the one part of `.agents/` that was actually being populated — is now shared via git instead of staying local-only.
