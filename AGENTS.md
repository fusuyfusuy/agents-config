# AGENTS.md — Operating Principles

> Model data first. Keep it flat. Verify before you ship. Don't guess — inspect.

---

## 1. How You Think

- **Schema before logic.** Define types, interfaces, and data models before writing any control flow.
- **Flat over nested.** Early returns, guard clauses, LUTs. Kill `if/else` ladders.
- **Simplest thing that works.** No speculative abstractions, no "future-proofing" hooks, no Gang-of-Four patterns where a function or lookup table will do.
- **Mechanical sympathy.** Minimize allocations on hot paths. No cascading spreads in loops. Keep execution contiguous.
- **Explicit errors.** Never swallow exceptions. Use Result types, discriminated unions, or typed exceptions. No silent fallback defaults.

---

## 2. How You Build

- **Layered growth.** Start from the smallest working end-to-end version. Add capabilities on top of something that already works. Never trade a working product for unfinished complexity.
- **No obsolete layers.** Remove dead paths. Don't add compatibility shims, fallbacks, or migrations for deprecated code.
- **Modular and separated.** One concern per module. Clean boundaries.
- **Long-term decisions only.** No stopgaps. If it's "temporary," it's wrong.

---

## 3. How You Use Dependencies

- **Inspect what's already there.** Check installed packages, their types, and their docs before writing your own or adding new ones.
- **Prefer established libraries** when they reduce complexity. Don't reimplement common functionality without a reason.
- **Verify target compatibility.** Confirm the library version, API surface, and runtime availability in the actual environment — not from memory.

---

## 4. How You Work (Workflow)

- **Spec first (SDD).** For non-trivial features: outline requirements in `plan.md` / `tasks.md` before touching implementation files.
- **Subagent delegation.** Offload research, exploration, and isolated tasks to subagents. Keep the main context window lean.
- **Inspect before you edit.** Always `view_file` on the target lines before modifying. Never edit blind.
- **Targeted reading.** View 100–300 line ranges. Use grep/symbol search for navigation. Never dump entire files into context.

---

## 5. How You Verify

- **Closed loop, no exceptions.** Every edit goes through: `Edit → Typecheck → Lint → Test → Observe → Iterate`.
- **Never declare done without proof.** Run the exact build, typecheck, or test command. Green output or it didn't happen.
- **Pre-push local build.** Run `bun run build`, `tsc --noEmit`, or equivalent locally before pushing or triggering CI.
- **3-strike rule.** If the same fix fails 3 consecutive times: stop. Step back. Re-read the original code. Update `plan.md`. Verify assumptions from first principles. Don't loop on a broken hypothesis.

---

## 6. How You Avoid Hallucination

- **Ground in real types.** Before using any API: inspect the actual installed package signatures (`.d.ts`, `dir()`, `__all__`). Don't interpolate from memory.
- **Probe before you commit.** For unfamiliar libraries or patterns, write a 5-line scratch script and execute it before integrating into the codebase.
- **Don't retreat silently.** If a new approach fails, diagnose *why* by inspecting docs and types — don't silently revert to a legacy pattern. If you must fall back, document the reason.
- **Separate research from implementation.** Research findings are hypotheses until verified by the compiler. Treat them accordingly.

---

## 7. Language Standards

### TypeScript
- `type` and `interface` for data shapes. Avoid `class` unless a framework demands it.
- Never `any`. Use `unknown` + type guards. Discriminated unions for domain states. `as const` for fixed lookups.
- No cascading spreads in loops. Use local mutation buffers for batch operations.
- Handle all Promise rejections explicitly. `Promise.all` for independent parallel I/O.

### Python
- `@dataclass(slots=True, kw_only=True)` for domain models. Pydantic (`BaseModel`) strictly at I/O boundaries.
- Annotate all signatures: `T | None`, `list[str]`. Modern syntax only.
- Top-level pure functions. `typing.Protocol` for interfaces. No deep class hierarchies.
- Dictionary dispatch or `match/case` over `if/elif/else` chains.
- Context managers (`with`) for resources. Generators (`yield`) for streaming data.

---

## 8. How You Track Changes

- **Conventional Commits.** `feat:`, `fix:`, `docs:`, `refactor:` — with rationale, not just description.
- **Decision log.** Record architectural pivots in `DECISIONS.md` or `CHANGELOG.md`. Future-you (and future-agents) will need the *why*.
- **Session scratchpad.** Use `.agents/logs/session.log` for uncommitted local notes during a session.

---

## 9. Hard No's

- **DO NOT** install new dependencies without explicit instruction.
- **DO NOT** refactor unrelated files or rewrite code outside the requested scope.
- **DO NOT** declare a task complete without running verification commands.
- **DO NOT** assume an API exists because it "should." Inspect first.
- **DO NOT** loop on a broken fix. 3 strikes → replan.
