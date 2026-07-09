---
name: graduated-validation-protocol
description: |
  The Ch7 safety envelope for a self-evolving agent: the RPO spine
  (Recursion, Provenance, Optimization) plus the Graduated Validation
  Protocol that gates what reaches production. Assigns every candidate
  change a risk tier and applies the matching scrutiny: Tier 1 canary
  (1% traffic, statistically significant target lift with no core-KPI
  regression, automatic rollback), Tier 2 staging gauntlet (multi-objective
  utility U = w_accuracy*accuracy + w_cost*(1-cost) + w_safety*safety_score,
  passes only net-positive with no safety regression), Tier 3 airlock
  (sandboxed risk/reward report escalated for human approve/reject/modify).
  Also the entropy-collapse guard (Kepler dual-store): a daily
  garbage-collection traversal that reclaims agent-generated Learnings once
  promoted, contradicted, or idle past a 30-day TTL. Use to gate a
  continuous self-evolution loop before candidate changes reach users. NOT
  for a one-off manual deploy (a single approval gate is enough), NOT for
  the diagnosis / attribution / intervention steps that produce the
  candidate (this validates the candidate, it does not generate it).
osmani-pattern: Reviewer
ghosh-layer: Workflow
chapter-source: "Agentic Graph RAG (O'Reilly) Ch7 — Self-Evolution and Evaluation — The RPO Spine and Graduated Validation Protocol + Persistent Self-Learning Without Entropy Collapse + Example 7-1"
references:
  - "RPO spine: Recursion / Provenance / Optimization (source control for thought)"
  - "Kepler dual-store garbage collection (OpenAI, 2026)"
  - "Consumes candidates from the execution-graph + semantic-backpropagation + intervention skills"
---

# Graduated Validation Protocol

## Overview

The evolutionary loop generates candidate improvements continuously. Not
all of them should reach production. Any system that modifies itself in
production needs a safety envelope. Ch7 provides it through the RPO spine
and the Graduated Validation Protocol (GVP).

The RPO spine is three interlocking properties:

- **Recursion** — the improvement mechanisms are themselves part of the
  codebase the agent can analyze and improve. The self-improvement system
  applies to itself.
- **Provenance** — every change is cryptographically signed and committed
  to an immutable ledger. This is source control for thought: complete
  auditability and instant rollback for every model, prompt, or
  architectural change. `lib.provenance_signature` is the dev-time stand-in.
- **Optimization** — the GVP itself. Rather than a single approval gate that
  must be either permissive or strict, it routes each candidate to a risk
  tier and applies matching scrutiny.

The three tiers:

| Tier | Risk class | Gate | Outcome |
|------|-----------|------|---------|
| 1 canary release | low: minor prompt updates, hyperparameter adjustments | ~1% live traffic; statistically significant target-metric lift with no core-KPI degradation | pass or automatic rollback |
| 2 staging gauntlet | moderate: SEAL/TPT fine-tune results, refined tool integration | benchmark + regression (catastrophic forgetting) + safety/alignment (bias drift) + performance (latency/cost) suites; net-positive multi-objective utility, no safety regressions | pass or archive |
| 3 airlock protocol | high: modifies safety protocols, integrates a brand-new tool, or failed staging with large potential | sandboxed isolated environment; automated risk/reward report | escalated for human approve / reject / modify |

The second half is the entropy-collapse guard. In production the agent
evolves continuously, hundreds of small improvements per week, each passing
validation individually. The compounding problem is the accumulated weight
of all changes: contradictory learnings, stale fixes for resolved issues,
redundant nodes that slow retrieval. The Kepler architecture (OpenAI, 2026)
solves this with a dual-store pattern: Knowledge is human-authored and
version-controlled; Learnings are agent-generated and ephemeral. A daily
garbage-collection traversal walks the Learnings subgraph and removes a node
if any of three conditions holds: the issue was resolved and promoted to
Knowledge, a newer higher-confidence learning contradicts it, or it has not
been retrieved in 30 days.

## When to Use

- Gating a continuous self-evolution loop: candidate changes must be
  validated before they reach live traffic (Ch7 Example 7-1, the
  `graduated_validation(candidate).passed` branch)
- Routing a mixed stream of candidates (prompt tweaks, fine-tunes, new-tool
  integrations) to the right level of scrutiny automatically
- Enforcing "no safety regression" as a hard constraint on a fine-tune
  before it ships (Tier 2)
- Running the daily Learnings garbage-collection pass to prevent entropy
  collapse in a long-running agent
- Monitoring the Learnings-to-Knowledge promotion rate to tune criteria

Phrases: "should this change ship", "which validation tier", "canary the
prompt update", "staging gauntlet", "airlock protocol", "graduated
validation", "RPO spine", "entropy collapse", "garbage-collect learnings",
"promotion rate".

## When NOT to Use

- **One-off manual deploys.** A single human approval gate is enough; the
  tiered protocol pays off only when candidates arrive continuously.
- **Generating the candidate.** This skill validates a candidate; it does
  not diagnose, attribute, or intervene. Those are the execution-graph,
  semantic-backpropagation, and intervention skills.
- **Hyperparameter optimization of retrieval infrastructure.** That
  background optimization (chunk sizes, hop distances) is Ch8
  production-hardening work; it runs alongside the loop, not inside this gate.
- **As the ledger itself.** `provenance_signature` is a content hash for the
  dev spike; production needs a real signing key and an append-only ledger.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | candidate dict {intervention_type, novel, touches_safety, new_tool} | `lib.assign_tier(candidate)` | one of `TIERS` | Tier 3 flags override; prompt/hyperparameter -> TIER1, fine_tune/tool_integration -> TIER2 |
| 2 | metrics {target_lift, target_pvalue, kpi_deltas} | `lib.canary_gate(metrics, min_lift, kpi_regression_tol)` | `GateResult` (TIER1) | passes iff lift > min_lift AND pvalue < 0.05 AND no KPI below -tol; else auto-rollback reason |
| 3 | scores {accuracy, cost, safety_score}, weights {w_accuracy, w_cost, w_safety} | `lib.staging_utility(scores, weights)` | float U | U = w_accuracy*accuracy + w_cost*(1-cost) + w_safety*safety_score |
| 4 | scores (+ safety_regression), weights, optional baseline | `lib.staging_gate(scores, weights, min_utility, baseline)` | `GateResult` (TIER2) | passes iff utility > baseline (or min_utility) AND safety_regression is False |
| 5 | risk_reward dict, human_decision or None | `lib.airlock_gate(risk_reward, human_decision)` | `GateResult` (TIER3, requires_human=True) | pending on None; passes only on "approve" |
| 6 | candidate carrying gate fields | `lib.graduated_validation(candidate)` | `GateResult` | assigns tier then runs matching gate from candidate fields |
| 7 | candidate dict | `lib.provenance_signature(candidate)` | deterministic SHA-256 hex | RPO Provenance: deterministic, content-sensitive |
| 8 | list[`Learning`], ttl_days=30 | `lib.garbage_collect(learnings, ttl_days)` | (kept, removed) tuple | removes promoted / contradicted / idle-past-TTL; keeps fresh |
| 9 | total_learnings, promoted counts | `lib.promotion_rate(total, promoted)` then `lib.promotion_health(rate)` | float rate, flag string | flags "criteria too strict" when rate < 0.10 |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "One approval gate is simpler than three tiers." | Ch7 is explicit: a single gate "must be either permissive or strict." A permissive gate ships unsafe changes; a strict gate blocks safe ones. The GVP routes each candidate to the appropriate level of scrutiny instead of forcing one policy on all of them. |
| "The fine-tune raised accuracy a lot, ship it." | Tier 2 passes only on net-positive multi-objective utility "with no safety regressions." Safety regression is a hard constraint in Ch7, not a term traded off inside the utility sum. `staging_gate` fails on `safety_regression` even when utility is high. |
| "The canary looks better, that's enough." | Ch7 Tier 1 requires a "statistically significant improvement in the target metric with no degradation in core KPIs." A raw lift without significance (p < 0.05) or with a KPI regression triggers automatic rollback, not a ship. |
| "Human review on the new-tool change slows us down, run it as a fine-tune." | Tier 3 overrides tier assignment: a change that "integrate[s] a brand-new external tool" or "modif[ies] safety protocols" is high-risk by definition and goes to the airlock regardless of its nominal type. `assign_tier` enforces the override. |
| "Learnings are cheap, keep them all." | Ch7 names the failure: "contradictory learnings, stale fixes for resolved issues, and redundant knowledge nodes that slow retrieval." Without the daily GC traversal the Learnings subgraph accumulates entropy and degrades retrieval. Keeping everything is the entropy-collapse path. |
| "Promotion criteria should be strict so only the best patterns are curated." | Ch7 Tip: "If fewer than 10% of learnings get promoted to curated knowledge within 30 days, your promotion criteria are too strict and you are discarding valuable patterns." `promotion_health` flags exactly this. |

## Red Flags

- **A fine-tune or new-tool change assigned to Tier 1.** Tier 3 override was
  skipped; `touches_safety` / `new_tool` / `novel` flags are not being read.
- **A staging pass with `safety_regression` True.** The hard safety
  constraint was folded into the utility sum instead of gating on it.
- **A Tier 3 `GateResult` with `requires_human` False.** The airlock is not
  escalating; human review is being bypassed.
- **Learnings count grows unbounded across days.** The daily GC pass is not
  running, or TTL / promotion edges are never set. Entropy collapse follows.
- **Promotion rate stuck below 10% with no flag.** `promotion_health` is not
  wired into monitoring; valuable patterns are being discarded silently.
- **CLI `--help` exits non-zero.** SKILL.md / CLI mismatch; the multi-harness
  invariant is broken.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report
   16/16 passed:
   - `assign_tier` routes prompt -> TIER1, fine_tune -> TIER2,
     touches_safety / new_tool / novel -> TIER3 (override)
   - canary passes on significant lift + no regression, fails on KPI
     regression and on non-significant p-value
   - staging fails when `safety_regression` is True even with high utility,
     passes net-positive over baseline with no regression
   - airlock is pending on None, passes only on "approve", stays
     `requires_human`
   - `garbage_collect` removes idle / promoted / contradicted, keeps a fresh
     high-confidence learning, honors the 30-day TTL boundary
   - `promotion_health` flags below 10%
2. **Run the DevOps scenario.** `python cli.py scenario prompt-canary` routes
   the CausalAttributionNode prompt refinement (stripe-python 3.2.1 -> 3.3.0
   timeout 30s -> 10s cascade) into Tier 1 canary, shows lift with no
   regression, then promotes the resolution to Knowledge and garbage-collects
   the ephemeral Learnings.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints the
   SKILL.md description.

## Security Posture

- **Prompt injection.** Candidate metadata, risk/reward reports, and Learning
  nodes may originate from agent-generated traces. `lib.py` treats every
  candidate field as untrusted data: it reads scalar metrics and boolean
  flags, never evaluates any field as code, and never interpolates a field
  into a shell or query. The airlock risk/reward report is truncated and
  JSON-encoded before display, so an injected instruction string is inert.
- **Data exfiltration.** No network calls anywhere in `lib.py`. Gate results
  and GC output are returned to the caller / printed to stdout; the caller
  owns downstream piping. `provenance_signature` is a local SHA-256 over the
  candidate content, computed in-process.
- **Privilege escalation.** No shell invocation, no `eval`/`exec`, no dynamic
  import, no file writes. The CLI reads only the explicit `--path` JSON files
  and writes nothing to disk. A candidate cannot escalate its own tier: the
  Tier 3 override in `assign_tier` is checked first, so a safety-touching or
  new-tool change cannot masquerade as a Tier 1 canary.

## Composition

- **Composes with** the Anthropic `agent-skills` Reviewer pattern at the
  Osmani layer and the Ghosh Workflow layer: it reviews a candidate change
  and returns a pass/fail verdict for an orchestration loop above it.
- **Consumes** candidates produced by the execution-graph,
  semantic-backpropagation, and intervention skills (Ch7). It is the
  `graduated_validation(candidate).passed` branch of the full evolutionary
  loop (Example 7-1).
- **Composes with** the RPO Provenance ledger: `provenance_signature` signs a
  candidate before the gate result is recorded, giving instant rollback.
- **Pairs with** the Kepler dual-store: the GC traversal runs on the same
  graph the execution-graph skill writes, distinguishing Knowledge from
  Learnings by provenance edges.
- **Hands off to** Ch8 production-hardening for the retrieval-infrastructure
  hyperparameter optimization that runs alongside the loop rather than inside
  this gate.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, AnthonyAlcaraz / forthcoming)
Chapter 7 — Self-Evolution and Evaluation, the sections "The RPO Spine and
Graduated Validation Protocol" and "Persistent Self-Learning Without Entropy
Collapse", plus the full evolutionary loop of Example 7-1. Key references
named in the chapter: the RPO spine (Recursion / Provenance / Optimization,
"source control for thought"); the three-tier Graduated Validation Protocol
(canary release / staging gauntlet / airlock protocol) shown in Figure 7-3;
the multi-objective utility U = w1*accuracy + w2*(1-cost) + w3*safety_score;
and the Kepler dual-store garbage-collection architecture (OpenAI, 2026) with
its 30-day TTL, daily GC pass, and 10% promotion-rate health threshold.
