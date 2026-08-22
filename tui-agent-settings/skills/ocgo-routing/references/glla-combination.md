# ocgo-routing × glla — combination analysis

**Status:** integrated into `../SKILL.md` § GLLA integration (2026-08-20). Skill remains DRAFT — NOT wired (no setup.sh re-run, no symlink into `~/.pi/agent/skills/`). This document is retained as the full seam analysis behind that section.

## Context

`ocgo-routing/SKILL.md` encodes the OpenCode Go tier strategy: route each task onto
the pooled-budget tiers (`glm-5.3` design/deep, `deepseek-v4-flash` default/mid/verify,
`mimo-v2.5` bulk fill, `gpt-5.6-luna` high/xhigh failover only, `kimi-k3` design backup,
`hy3` ultra-cheap churn) and enforce the design → fill → verify contract (executable
pseudocode only, machine gate before accept, filler escalation `mimo-v2.5 → mimo-v2.5-pro
→ flash`, `ocgo -w r` budget gate). Numbers snapshot 2026-08-20; refresh path in the
SKILL.md appendix (llm-search-knowledge repo).

Open question that produced this doc: can the pi goal/list/loop/audit machinery
("glla") be combined with this routing process?

## What glla actually is

`pi-goal-list-loop-audit` (installed, v0.35.3) — mission control for autonomous pi:
`/goal`, `/list`, `/loop`, `/glla`, `/review`. Core thesis is **anti-bamboozle**: the
agent that does the work must not be the one that verifies it.

- Goal intake: interview-drafted contract → Confirm dialog → durable state in
  `.pi-glla/`; nothing activates sight-unseen.
- Implementation: `agent_end`-driven continuation loop, 5-minute hard backoff cap.
- Completion: `complete_goal` queues a **detached, extension-less auditor process**
  (fresh pi RPC, no extensions/skills/context, `read`/`grep`/`find`/`ls`/`bash` in
  intentional power mode, cannot see the implementing conversation) that re-verifies
  against the contract; `regression_shield` requires raw command output per
  verification-contract item, orchestrator-enforced.
- Model machinery (not expected, relevant): `model-selector.ts` — per-scope fallback
  chains (session / subagent / drafter) with a forbidden-gate and ledger;
  `drafter-model.ts` (drafting-only model lease, restores session model after);
  `model-picker.ts` / `multi-model-picker.ts`; subagent model strategy
  (`goal-loop-subagents.ts`: `inherit-parent` default vs `agent-default`, manages
  Explore/Designer agent files behind a frontmatter marker + drift test);
  `main-model-recovery.ts` + `quota-retry.ts`; `reviewer.ts` (reviewer role).
- Telemetry: `.pi-glla/active.jsonl` records `model_switch` events + per-session
  `lastModelRef` (observed real switches: `opencode-go/gpt-5.6-luna → hy3 →
  opencode-go/qwen3.7-plus` in llm-search-knowledge).

## The layer model

| Plane | Owns | System |
| --- | --- | --- |
| Control | what to do, when to stop, who verifies | glla (`/goal`, `/list`, `/loop`, auditor) |
| Execution | which model tier runs each work item | ocgo-routing (the tier table + contract) |
| Budget state | live pooled-window numbers | `ocgo` CLI (`~/.local/bin/ocgo`, `-w r\|w\|m`) |

Orthogonal by construction — no overlap, no conflict. glla orchestrates; routing
dispatches; ocgo reports reality.

## The seams (combination points)

1. **Escalation semantics = fallback chains.** `model-selector.ts` takes per-scope
   priority-ordered model refs with a forbidden-gate. The routing escalation rules
   translate 1:1 into chain definitions:
   - session: `[opencode-go/deepseek-v4-flash → opencode-go/gpt-5.6-luna-high →
     opencode-go/glm-5.3]`
   - drafter: `[opencode-go/glm-5.3 → opencode-go/kimi-k3]`
   - subagent (per role): Designer→GLM, Explore→cheap-fast, implementer→flash
   - "Luna base never" (intel 27 < MiMo 38) is literally a forbidden-gate entry.
2. **The verification gate becomes structural.** The skill's "gate before accept,
   never accept an unverified fill" is enforced by glla's detached auditor +
   regression_shield — a separate process that cannot be talked into a self-serving
   pass. The goal's verificationContract should BE the routing gate criteria
   (compile/test/typecheck/diff evidence).
3. **Loops are the volume multiplier the budget gate exists for.** `/loop` (metric,
   spec, project-audit; hours-long, hundreds of iterations) is exactly the pattern
   where tier economics dominate. Policy to define: per-iteration tier hy3/MiMo for
   mechanical iteration, GLM checkpoint every N iterations, stop iteration when
   `ocgo -w r` shows window exhaustion. `quota-retry.ts` already reacts to quota walls
   reactively — routing makes tier-downgrade proactive.
4. **Subagent model strategy = per-role routing hooks.** glla manages Explore/Designer
   agent files (marker-protected, drift-test-guarded) with `inherit-parent` vs
   `agent-default`. The routing table defines which role runs on which tier; glla
   provides the mechanism.
5. **Routing telemetry already exists.** `active.jsonl` logs every model switch and
   lastModelRef per session — routing decisions are already recorded. Future
   `/glla stats` or `collect_agent_usage` can correlate tier-per-task against audit
   outcomes, closing the loop on whether the table is actually right.

Unifying observation: **the routing rule "never flash-everywhere at peak volume" and
glla's loop budgets are the same constraint in two languages** — a `/loop` with a
`tokens=`/`time=` bound is already a budget gate; the skill formalizes which tier eats
that budget per iteration.

## Frictions / caveats

1. **Auditor model pinning is limited.** The auditor is a fresh extension-less process
   running the session default; per-audit tier control may not be reachable. Mechanical
   audits with a cheap default are fine; deep semantic audits inherit the session
   default. The skill must not promise auditor-tier control it can't deliver.
2. **glla evolves fast** (v0.35.3, addenda every few days). The skill references
   commands (`/goal`, `/list`, `/loop`, `/glla`) and concepts, never internals.
3. **Tier must be set at spawn time** (config default or subagent override) — the
   routing contract forbids mid-task switching. The `/goal` drafting interview is where
   the per-goal tier gets captured into the goal text/contract.
4. **Route per item, not per loop.** A loop iteration is the atomic task; the loop is
   orchestration. "One model per atomic task" applies inside each iteration.
5. **Benchmark data lag.** SWE-bench snapshot stops ~2025-12; 2026 models lean on AA /
   LMArena / OpenRouter benchmarks — the tier table is only as fresh as the last
   `gen_optimal.py` / OpenRouter refresh.

## Proposed v2 direction — done 2026-08-20

Added `SKILL.md` § GLLA integration covering: goal drafting tier tags
(`/goal`), list tier tags (`/list` + `list_activate`), loop iteration policy
(per-iteration tier + checkpoint cadence + window-stop), subagent chain
definitions per role, auditor policy with pinning caveat, telemetry pointer
(`.pi-glla/active.jsonl`). Also extracted `tiers.json` as the live tier
registry (any position swappable on the go) alongside that section.

## Open questions (remaining)

- Should the skill generalize to a rule engine (table + chains + gate) that any
  subscription plan can instantiate? (Decision: stay OC Go-specific — revisit
  later, per session 2026-08-20.)
- Is a tiny backing script (route classifier) justified? (Decision: no — 6-row
  table stays in prose + JSON, revisit at ~10 rows. `tiers.json` is data, not
  code.)
- Can the auditor's model be pinned via settings in a future glla version?
- Wire-up criteria: what has to be true before `setup.sh` runs and the symlink
  fan-out happens? (Skill still DRAFT — criteria: GLLA section + tiers.json
  landed, this iteration completes it.)
