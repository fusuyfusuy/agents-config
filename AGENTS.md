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
