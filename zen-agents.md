# AGENTS.md

## The Zen of Systems

> *Perfection is achieved not when there is nothing more to add, but when there is nothing left to take away. Model data explicitly, keep transformations flat and deterministic, and cooperate with hardware realities rather than forcing artificial abstractions.*

---

## 1. Core Invariants & Architecture

* **Data First, Logic Second:** Define complete data models, types, and schemas before writing execution logic.
* **Flat Over Nested:** Eliminate deep branching (`if/else` ladders, nested callbacks). Favor early returns, guard clauses, and flat lookup tables (LUTs).
* **Subtract Obsolete Code:** Never build backward-compatibility shims, deprecated wrappers, or fallback paths. Remove dead code cleanly.
* **Zero Speculative Engineering:** Implement strictly what meets active requirements. No premature abstractions, unused helper layers, or "future-proofing."
* **Mechanical Sympathy:** Minimize unneeded heap allocations (e.g., redundant deep copies, object spreading inside loops). Keep hot execution paths contiguous.
* **Explicit Error Domains:** Never swallow errors or use silent fallback defaults. Model failure states explicitly via Discriminated Unions or typed Results.

---

## 2. Language Standards

### TypeScript

* **Data Shapes:** Use `type` and `interface` for pure data shapes. Restrict `class` to framework lifecycle bindings (e.g., NestJS controllers).
* **Strict Typing:**
* `any` is forbidden. Use `unknown` with explicit type narrowing or type guards.
* Model operational results and multi-state flows with **Discriminated Unions**.
* Use `as const` for fixed lookup tables, state maps, and enums.


* **Allocation Awareness:** Avoid cascading object spreads (`{ ...state, ...delta }`) inside high-frequency loops; use local mutation buffers or structured batching.
* **Async Safety:** Handle all Promise rejections explicitly; avoid unhandled fire-and-forget executions.

```typescript
// ✅ Good: Discriminated Union + Table Lookup
type AuthState = 
  | { readonly status: 'unauthenticated' }
  | { readonly status: 'authenticated'; readonly token: string; readonly userId: string }
  | { readonly status: 'error'; readonly code: number; readonly message: string };

const HTTP_STATUS_CODES = {
  OK: 200,
  UNAUTHORIZED: 401,
  NOT_FOUND: 404,
} as const;

```

### Python

* **Data Shapes:**
* Internal models/DTOs: `@dataclass(slots=True, kw_only=True)`.
* External I/O & API boundaries: Pydantic (`BaseModel`).


* **Typing & Signatures:** Full type annotations required (`T | None`, `list[str]`, `Sequence[T]`).
* **Composition Over Inheritance:** Write top-level, stateless, pure functions. Use `typing.Protocol` for structural subtyping; reject multi-tier class inheritance.
* **Control Flow:** Prefer dictionary dispatch or `match/case` over long `if/elif/else` ladders.
* **Resource Hygiene:** Always use context managers (`with`) for files, connections, and locks. Use generators (`yield`) for streaming datasets to keep memory overhead $O(1)$.

```python
# ✅ Good: Slotted dataclass + Protocol composition
from dataclasses import dataclass
from typing import Protocol

@dataclass(slots=True, kw_only=True)
class SensorReading:
    device_id: str
    temperature: float
    humidity: float

class TelemetrySink(Protocol):
    def flush(self, readings: list[SensorReading]) -> None: ...

```

---

## 3. Workflow & Verification Gates

### Execution Sequence

```
[1. Spec & Types] ──► [2. Flat Implementation] ──► [3. Automated Verification]

```

1. **Spec & Types:** Define or update schemas, types, and interfaces first.
2. **Implementation:** Write the most direct, flat implementation that fulfills the spec.
3. **Deterministic Verification Gate:** You MUST execute local verification before claiming completion:
* Typechecks pass cleanly (`tsc --noEmit`, `pyright`, or `mypy`).
* Affected test suites run and pass.
* Local builds succeed without missing environment variables.



### Context & Task Hygiene

* **Subagent Delegation:** Delegate only isolated exploration or self-contained multi-file tasks. Never spawn subagents for single-file edits.
* **Atomic Conventional Commits:** Use `feat:`, `fix:`, `refactor:`, `docs:` with concise rationale.
* **Architectural Memory (`DECISIONS.md`):** Record non-obvious architecture choices, new dependencies, or discarded alternatives using the ADR protocol.

---

## 4. Architectural Decision Records (`DECISIONS.md`)

*Record entries strictly for technology additions/removals, storage engine selections, state synchronization strategies, or security boundaries. Keep entries under 25 lines.*

```markdown
## [ADR-001] YYYY-MM-DD: Short Title

- **Status:** Accepted | Superseded by [ADR-XXX] | Deprecated
- **Context & Problem:** 1-2 sentences on the constraint or bottleneck.
- **Decision:** The concrete architecture, library, or data pattern chosen.
- **Alternatives Discarded:**
  - *Option A:* Why it was rejected (e.g., memory overhead, high latency).
  - *Option B:* Why it was rejected (e.g., lack of strict typing, maintenance risk).
- **Key Trade-offs / Consequences:**
  - *Positive:* Direct benefit (e.g., O(1) lookup time, zero heap allocations).
  - *Negative / Debt:* Compromise accepted (e.g., single-writer concurrency limit).

```

---

## 5. Negative Constraints (Strictly Forbidden)

* **DO NOT** install new third-party dependencies without explicit instruction.
* **DO NOT** refactor unrelated files or make cosmetic edits outside the requested scope.
* **DO NOT** introduce Gang-of-Four design patterns (Factories, Adapters, Strategies) where a single pure function or table lookup is sufficient.
* **DO NOT** declare a task complete without running and reporting clean verification commands.
