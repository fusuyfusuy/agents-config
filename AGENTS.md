# Global Agent Operating Principles (AGENTS.md)

## 1. Core Engineering & Architecture Directives
- **No Obsolete Layers**: Do not preserve backward compatibility. Remove obsolete paths instead of adding compatibility layers, fallbacks, or migrations.
- **Simplest Implementation**: Choose the simplest implementation that fully meets current requirements. Avoid speculative abstractions, configuration, and indirection.
- **Layered System Growth**: Grow the system in layers. Start from the smallest version that works end-to-end, and add each new capability on top of a product that already works. Never trade a working product for unfinished complexity.
- **Long-Term Architectural Quality**: Make architectural decisions for the long term. Do not accept a stopgap that only works for now and is meant to be replaced later.
- **Modular Components**: Keep components modular and concerns clearly separated.

## 2. Dependencies & Framework Rules
- **Prefer Established Libraries**: Prefer established, well-maintained libraries when they reduce overall complexity or improve reliability. Do not reimplement common functionality without a clear reason.
- **Inspect Dependencies First**: Lean on the dependencies already in the project before writing your own implementation or adding packages. Do not assume a library lacks a capability without checking its documentation and types.
- **Target Compatibility**: When using library-provided features, ensure that libraries are available in the target system/architecture/app.

## 3. Workflow & Spec-Driven Development (SDD)
- **Subagent Delegation**: Use subagents for all tasks to keep the main context window clear.
- **Spec-Driven Execution (SDD)**: For non-trivial features, outline requirements and a clear execution plan (`plan.md` / `tasks.md`) before modifying implementation files.
- **Empirical Verification**: Never declare a task resolved without running exact build, test, or typecheck verification commands.
- **Pre-Push Local Build Verification**: Before pushing code changes to remote repositories or triggering CI/CD build pipelines, agents MUST run exact build and typecheck commands locally (e.g. `bun run build`, `bun check`). Avoid `$env/static/public` for dynamic runtime variables; prefer `$env/dynamic/public` with default fallback values so container builds succeed when environment variables are omitted at image build-time.


## 4. Change Tracking & Log Management
- **Task-Level Commits**: Write clean, descriptive Conventional Git Commits (`feat`, `fix`, `docs`, `refactor`) summarizing changes and rationale.
- **High-Level Architectural Logs**: Record major architectural decisions and pivots in `CHANGELOG.md` or `DECISIONS.md` (or `.agents/logs/session.log` for uncommitted local scratchpads) to maintain high-signal project logs.

# Engineering Principles Details
# Agent Instructions & Project Invariants

## Core Directive
> Model explicit data structures first, keep transformations flat and deterministic, and write mechanically sympathetic code that rejects unnecessary abstraction in favor of measurable simplicity and correctness.

---

## 1. General Engineering Invariants
- **Data Layout First:** Define complete data models, types, and schemas before writing control flow or business logic.
- **Flat Over Nested:** Eliminate deep nesting (`if/else` ladders, nested callbacks). Favor early returns, guard clauses, and flat table-driven lookups (LUTs).
- **Mechanical Sympathy:** Minimize unneeded allocations (e.g., redundant deep copies, excessive object spreads in loops). Keep hot execution paths contiguous and linear.
- **Explicit Error Boundaries:** Never swallow exceptions or introduce silent fallback defaults. Model failures explicitly via Result types, Discriminated Unions, or typed exceptions.
- **Zero Speculative Code:** Write only the minimal code needed for the immediate task. Never create premature abstractions, unused helper layers, or "future-proofing" hooks.

---

## 2. TypeScript Standards
- **Data Modeling:** Use `type` and `interface` for pure data shapes. Avoid `class` unless interfacing with an external framework lifecycle.
- **Strict Typing:** 
  - Never use `any`. Use `unknown` with explicit type narrowing or type guards.
  - Model domain states and operation results using **Discriminated Unions**.
  - Use `as const` for fixed lookup tables, state maps, and enums.
- **Allocation Awareness:** Avoid cascading object spreads (`{ ...state, ...delta }`) inside high-frequency loops; use local mutation buffers or structured batching when handling large arrays.
- **Async Hygiene:** Handle all Promise rejections explicitly. Use `Promise.all` for independent parallel I/O; avoid unhandled fire-and-forget execution.

---

## 3. Python Standards
- **Data Modeling:**
  - Use `@dataclass(slots=True, kw_only=True)` for internal data transfer objects and domain models.
  - Use Pydantic (`BaseModel`) strictly at external I/O boundaries (HTTP schemas, environment configuration).
- **Typing & Signatures:** Annotate all function signatures and return types using modern Python syntax (`T | None`, `list[str]`).
- **Composition Over Inheritance:** Keep functions top-level, stateless, and pure where possible. Use `typing.Protocol` for structural interfaces; reject multi-level class inheritance.
- **Lookup Tables:** Prefer dictionary dispatch or `match/case` over long `if/elif/else` branches.
- **Memory & Resource Safety:** Always manage resources with context managers (`with`). Use generators (`yield`) for streaming datasets to keep memory overhead $O(1)$.

---

## 4. Execution & Verification Workflow
When generating or modifying code, follow this exact sequence:

1. **Schema & Types:** Define or update the target types/schemas first.
2. **Implementation:** Write the most direct, flat implementation that fulfills the spec.
3. **Verification Checklist:**
   - [ ] Are type checks passing cleanly (`tsc --noEmit`, `pyright`, or `mypy`)?
   - [ ] Are edge cases (null/None, empty collections, network timeouts) explicitly handled?
   - [ ] Are tests included or updated to cover the new behavior and edge cases?

## 5. Negative Constraints (Strictly Forbidden)
- **DO NOT** install new third-party dependencies without explicit instruction.
- **DO NOT** refactor unrelated files or rewrite existing code outside the requested scope.
- **DO NOT** introduce Gang-of-Four design patterns (Factories, Adapters, Strategies) where a single pure function or table lookup is sufficient.
