---
name: ocgo-routing
description: >
  Route each task across the OpenCode Go tiers against the pooled
  $12/5h · $30/wk · $60/mo budget: GLM-5.3 designs (deep, rare), DeepSeek
  V4 Flash is the default/mid/verifier, MiMo-V2.5 bulk-fills, GPT-5.6 Luna
  high/xhigh is failover (never base), Kimi K3 backs up the design tier.
  Enforces the design→fill→verify contract with a machine gate on every
  MiMo fill and per-window budget checks via `ocgo`. Use when the user says
  "which model", "route this", "tier this", "design in GLM then fill",
  "model strategy", or before multi-file builds or bulk generation.
---

# OpenCode Go Routing (ocgo-routing)

Route every LLM task onto the right OpenCode Go tier, then enforce the
design → fill → verify contract so cross-model work doesn't rot into
silently-incompatible code. Numbers below are the verified snapshot
(2026-08-20; refresh path in the appendix). **Live tier values are in
[`tiers.json`](tiers.json)** — edit that file to swap any position on the
go; the table here stays as a readable snapshot.

## The tiers

> Snapshot 2026-08-20 — live source: `tiers.json` (this table is not the
> source of truth after the first edit to that file).

| Role | Model | Intel | Code | Agentic | $/1M in / out | Ctx | Allowance | Req/mo |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Design / deep** | `glm-5.3` | 59.5 | 74.8 | 59.1 | 1.40 / 4.40 | 1M | $15/mo | 1,080 |
| **Default / mid / verify** | `deepseek-v4-flash` | 51.8 | 69.1 | 48.4 | 0.22 / 0.66 | 1M | $30/mo | 37,800 |
| **Bulk fill** | `mimo-v2.5` | 38.0 | 56.8 | 24.4 | 0.14 / 0.28 | 256k | $60/mo | 150,400 |
| **Failover / 2nd opinion** | `gpt-5.6-luna` **high/xhigh only** | 47/50 | — | — | 0.20 / 1.20 | 1M | $15/mo | 10,250 |

Aux (also in `tiers.json`): design backup `kimi-k3` (59.7 / 76.2 / 54.3,
$15/mo, 490/mo), ultra-cheap churn `hy3` (42.2, $60/mo, 21,500/mo) for
<256k no-reasoning work, fill escalator `mimo-v2.5-pro` (16,300/mo).

> Allowance map: **$15/mo** — glm-5.3, gpt-5.6-luna, kimi-k3, grok-4.5,
> deepseek-v4-pro, qwen3.8-max. **$30/mo** — deepseek-v4-flash. **$60/mo** —
> mimo-v2.5, hy3, minimax-*, kimi-k2.x, qwen3.7/3.6-plus. All windows scale
> from the pooled account caps ($12/5h · $30/wk · $60/mo) by usage/60.
> Map lives in `tiers.json:allowance_map`.

## Route (4 steps)

1. **Classify** the task on two axes:
   - reasoning demand: mechanical → deep
   - volume: one-shot → bulk
   The decisive axis is **agentic demand** (will it loop/tool?): bulk
   tier 24.4 < default 48.4 < design 59.1. Any task that needs multi-step
   adherence or tool use is NOT the bulk tier's.
2. **Pick the tier** from `tiers.json` (snapshot table above for quick
   glance). Fill-type rule:
   - UI / component / website codegen → bulk tier (snapshot: MiMo is
     *better than default* on Arena code ELO 1279 / rank 23 vs 1269 / 34).
   - Backend logic, refactors, anything with interfaces → default tier.
   - Whole-feature design, architecture, "deep analysis" → design tier.
     Coarse-grained only: design tier gets ~1,080 req/mo and ~220/5h;
     per-file design kills the budget.
3. **Budget-gate before any batch**: run `ocgo -w r` (and `-w w` weekly).
   Peak volume is what gates — the busiest real 5h window was 2,541 reqs.
   If the window is nearly spent, downgrade the tier instead of bursting:
   design→default, default→bulk. Never run a design pass and a bulk run at
   full blast inside the same window — they share the pool.
4. **Escalate by meaning, not by habit**: harder task → design tier (or its
   backup); wrong-output failover / second opinion / vendor diversity →
   failover tier high or xhigh. Failover base (snapshot intel 27) is a
   downgrade below bulk — never an escalation.

## The design → fill → verify contract

Iterative design (back-and-forth to agree) does NOT run on the design tier —
`glm-5.3` is `220/5h, 1,080/mo` and dies on loops. Draft on the cheap tier,
lock on the deep tier:

- **Draft loop** (`tiers.default` / `deepseek-v4-flash`, 48.4 agentic, `7.5k/5h`):
  back-and-forth with the human until the shape is agreed. Cheap enough to chat.
- **Lock** (`tiers.design` / `glm-5.3`, 59.1 agentic): **one** final pass that
  emits **executable pseudocode only**: function signatures, data shapes, return
  contracts, explicit edge cases. Prose forbidden — bulk's 24.4 agentic drifts on
  prose and follows contracts. If you need a second lock, you already paid for it;
  re-draft on default.
- **Filler** (bulk tier, or default tier for backend fills) transcribes one
  file per contract, verbatim — no interpretation of its own.
- **Gate before accept — non-negotiable, on every fill**: compile, typecheck,
  test, or a `git diff` review. The review pass may run on the churn/default
  tier (a review is ~10× cheaper than a fill's context replay). Two
  consecutive gate failures on the same contract → escalate the filler
  `bulk → fill_escalator → default` (snapshot: `mimo-v2.5 →
  mimo-v2.5-pro → deepseek-v4-flash`). Never hand-tune a misfire; re-spec
  or escalate.
- **Integrator** (default tier) owns merge + cross-file coherence + final
  gate after the fills land.

## Updating a tier (any position, on the go)

Live values live in `tiers.json`. To swap any position, edit one row — no
prose change needed (routing logic refers to roles, not names):

```bash
# swap the design position to kimi-k3
jq '.tiers.design.model = "opencode-go/kimi-k3"' tiers.json > /tmp/t.json && mv /tmp/t.json tiers.json
# swap bulk to any other $60/mo model
jq '.tiers.bulk.model = "opencode-go/qwen3.8-max"' tiers.json > /tmp/t.json && mv /tmp/t.json tiers.json
```

Also update `req_per_month`/`cost_per_1m_*`/`ctx`/`intel` alongside the
model if you have fresh numbers; update `allowance_map` if the allowance
bucket changed. Snapshot table above is docs only after the first swap.

## GLLA integration

Combines with the pi goal/list/loop/audit machinery (`/goal`, `/list`,
`/loop`, detached auditor; see
[`references/glla-combination.md`](references/glla-combination.md) for
full seams). Planes are orthogonal — glla = control (what/when/verify),
routing = execution (which tier), `ocgo` = live budget state.

- **Goal drafting** (`/goal`): capture the servicing tier in the goal text
  and `verificationContract` (e.g. "design in `tiers.json:tiers.design`,
  fills in `tiers.json:tiers.bulk`"). The contract is where the per-goal
  tier choice becomes durable.
- **List** (`/list`): items carry tier tags; `list_activate` spawns with the
  right tier. One tier per list item — routing applies per item.
- **Loop** (`/loop`): per-iteration tier is the atomic task (loop is
  orchestration). Policy: mechanical iterations on churn/bulk, `design`-tier
  checkpoint every N iterations (N set at loop drafting, not mid-loop),
  stop when `ocgo -w r` shows window exhaustion. `quota-retry.ts` reacts
  after a wall; routing makes the downgrade proactive.
- **Subagent roles** → fallback chains (`model-selector.ts` per-scope
  chains with forbidden-gate): Designer → `tiers.design` → `aux.design_backup`,
  Explore → `aux.churn`/cheap, implementer → `tiers.default`. Forbidden
  entry `tiers.failover` base (snapshot: Luna base intel 27) stays blocked.
- **Auditor**: detached, extension-less, runs the session default — not
  pinnable per audit. The skill must not promise per-audit tier control.
  Put the gate criteria (compile/test/typecheck/diff evidence) into
  `verificationContract`; the detached auditor + `regression_shield` then
  enforces "gate before accept" structurally.
- **Telemetry**: `.pi-glla/active.jsonl` already logs `model_switch` +
  `lastModelRef` per session — tier-per-task is retro-auditable via
  `collect_agent_usage` / `toku --detail`.

Caveats: glla evolves fast — skill references commands/concepts, not
internals. Tier is set at spawn (config default or subagent override),
never mid-task — the `"Never: mid-task model switching"` rule and the
`"/goal` captures the tier" rule are the same constraint.

## Never

- Bulk tier into tool loops / agentic work (agentic 24.4).
- Failover base as any escalation (snapshot intel 27 — weaker than bulk).
- Per-file or mid-task design-tier work (budget + latency both die).
- Default-everywhere at peak volume — ~$0.0008/req at our cache mix caps the
  $60/mo pool at ~75k reqs; peak months exceed it. The split exists for this.
- Mid-task model switching (the contract assumes one model per atomic task).
- Accepting a fill that never passed a gate.

## Appendix — evidence

All numbers: `data/opencode_go.csv`, `data/opencode_go_usage_limits.csv`,
`data/results.csv`, `outputs/` in the `llm-search-knowledge` repo, snapshot
2026-08-20. **Live tier data after the snapshot: `tiers.json` in this skill
dir.** Cross-source caveat: Intelligence Index (Artificial Analysis) and
Arena ELO are different scales — never compare across.

Refresh: `python3 scripts/gen_optimal.py` (re-derives the optimal driver from
real agent logs) + re-read `data/opencode_go_usage_limits.csv` +
`outputs/ocgo_optimal.html` + update `tiers.json` (keys: `tiers.*.model`,
`cost_per_1m_*`, `ctx`, `req_per_month`, `intel`/`code`/`agentic`,
`allowance_map`). Live windows: `ocgo` at any time. If the allowance table
changed since the snapshot, trust the fresh data over this file and update
`tiers.json`.

## References

- [`tiers.json`](tiers.json) — live tier registry (swappable per position).
- [`references/glla-combination.md`](references/glla-combination.md) —
  combination analysis; now integrated into "GLLA integration" above.
