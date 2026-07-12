---
name: letta-failure-modes
description: |
  Reviewer skill: diagnose an agent's memory architecture against the 8
  Letta Leaderboard failure modes (Ch4). Takes a memory snapshot (or a
  description of the architecture) and reports which failure modes are
  present, with concrete evidence and recommended fixes. Use BEFORE
  shipping any memory implementation to production and BEFORE root-causing
  why a deployed agent "forgets" or "drifts." NOT a benchmark (does not
  produce a single accuracy number), NOT a substitute for production
  observability (this is a static diagnostic, not a runtime monitor).
osmani-pattern: Reviewer
ghosh-layer: Workflow
chapter-source: "Agentic Graph RAG (O'Reilly) Ch4 — Memory — The Problem section (Letta Leaderboard 8 failure modes) + composes with hierarchical-memory + bi-temporal-edge"
references:
  - "Letta Leaderboard for agentic memory (Ch4 anchor — 8 failure modes named)"
---

# Letta 8-Failure-Modes Diagnostic

## Overview

The Letta Leaderboard for benchmarking agentic memory names eight distinct
failure modes that tend to co-occur (Ch4):

1. **No-retrieval-when-available** — model fails to recognize when relevant
   info is already in memory; issues unnecessary searches.
2. **Hierarchy-collapse** — trivia in prime memory; critical facts archived
   or dropped.
3. **In-conversation-misses** — agent misses key pieces of info even when
   present in the immediate context.
4. **Volume-degradation** — retrieval accuracy degrades as data volume
   grows; performance drops at scale.
5. **Silent-overwrite** — new info overwrites old facts instead of being
   layered; system cannot explain how or why things changed.
6. **Cross-reference-failure** — related info isolated in separate silos;
   no pattern recognition.
7. **Temporal-blur** — event timelines blur; agent loses temporal coherence.
8. **Threshold-collapse** — works at hundreds of facts, quietly collapses
   at thousands.

This skill takes a snapshot of an agent's memory state (or a structural
description) and reports which of these 8 are present, with evidence and
recommended fixes. It runs static analysis — no agent inference loop required.

## When to Use

- Pre-launch review of a new memory implementation
- Root-cause analysis when an agent in production is "forgetting" or
  "drifting"
- Periodic audit (weekly / monthly) on long-running agents
- Code review of a colleague's memory layer

Phrases: "audit my memory architecture", "why is my agent forgetting",
"is my memory production-ready", "Letta Leaderboard", "memory diagnostic".

## When NOT to Use

- **Single failure mode you've already identified.** If you know it's
  silent-overwrite, just go fix it; this skill's value is the cross-cutting
  audit, not the depth on one mode.
- **Runtime monitor.** This is a static diagnostic. Production needs
  metrics + alerts, not periodic full-audit invocation.
- **Benchmark/eval.** This does not produce a comparable accuracy number.
  For Letta Leaderboard scoring, run the actual benchmark suite.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Memory snapshot dict OR architecture description JSON | `lib.diagnose(snapshot)` | `DiagnosticReport` with 8 entries (one per failure mode) | report covers all 8 modes; each entry has status ∈ {ok, warning, present}; severity score 0-3 |
| 2 | Report | `lib.format_text(report)` | Human-readable diagnostic | every "present" mode includes evidence + fix recommendation |
| 3 | Report | `lib.format_json(report)` | machine-readable JSON | round-trip serializable |
| 4 | Report | `lib.total_score(report)` | int 0-24 (sum of severities) | 0 = production-ready; ≥10 = ship at risk; ≥18 = do not ship |
| 5 | Scenario name | `cli.py scenario broken-vs-clean` | showcase that EXERCISES all 8 modes: an anti-pattern snapshot triggers all 8 (`present`) and a clean composed snapshot triggers 0 | broken reports 8 `present`, clean reports 0 |

## Diagnostic Heuristics (per failure mode)

| Mode | Static signal | Threshold |
|------|---------------|-----------|
| No-retrieval-when-available | recall layer is empty or query log not preserved | recall.size == 0 with mature memory |
| Hierarchy-collapse | >50% short-lived facts in core OR durable facts > 50% in archival vs core | (composes with hierarchical-memory.diagnostics) |
| In-conversation-misses | extract_fn not wired up — interactions logged but no facts promoted | recall.size > 5 AND core.size == 0 |
| Volume-degradation | retrieval method is linear-scan with no index | flagged via architecture description tag |
| Silent-overwrite | edges have no `valid_until` mechanism / no `invalidation_reason` | flagged if bi-temporal-edge primitive is absent |
| Cross-reference-failure | average node degree < 1 OR graph is a forest with many disconnected components | components > nodes/10 |
| Temporal-blur | timestamps not preserved on edges / facts | facts without `created_at` |
| Threshold-collapse | core_limit OR retrieval pipeline declared O(n) on architecture form | size-test scenario fails at 10x scale |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "My agent works fine on the demo — I'll skip the audit." | Demo workloads are small. The Ch4 anchor: "Systems that work acceptably with hundreds of facts quietly collapse when exposed to thousands." Threshold-collapse is the failure mode that hides best in demos. |
| "I'll fix the failures as users complain." | The first 7 failure modes are silent — the agent "feels" wrong without producing a single error log. You will not know which mode to fix unless you scan for them. |
| "I'll skip diagnostics for short-lived agents." | Short-lived agents that suffer in-conversation-misses still produce wrong answers. The discipline is cheap (one call); the failure cost is incident-response time. |
| "I already use a hierarchical memory — that covers most of these." | Letta-style hierarchy covers 1, 2, 3, and partially 8. The other 4 (silent-overwrite, cross-reference-failure, temporal-blur, volume-degradation) are orthogonal and need separate primitives (bi-temporal-edge, graphiti-incremental-update, indexed retrieval). The hierarchy alone is necessary, not sufficient. |
| "The diagnostic scoring is arbitrary." | The 0-24 score is a forcing function. The Ch4 chapter quote — "The quality of memory management directly determines agent performance on long-running tasks" — converts to a single number that goes up when memory degrades. Track the number. |

## Red Flags

- **All 8 modes flagged `ok`.** Either the diagnostic is broken (likely)
  or the architecture is exceptional (suspicious — verify by running a
  size-stress scenario).
- **`silent-overwrite` flagged with no `bi-temporal-edge`.** The fix is
  mechanical: integrate `bi-temporal-edge` for the affected relationships.
- **`hierarchy-collapse` and `volume-degradation` both flagged.** The
  memory architecture is unrescuable without a redesign; recommend
  switching to a structured 3-tier hierarchy (composes with
  `hierarchical-memory`).
- **`temporal-blur` flagged on a regulated-domain agent.** Compliance
  blocker — fix before shipping.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report:
   - all 8 failure modes detectable from a synthesized broken memory
   - no false-positives on a known-clean memory built from the other
     three Ch4 skills (bi-temporal-edge + hierarchical-memory +
     graphiti-incremental-update)
   - round-trip report serialize / deserialize
2. **Run the showcase scenario.** `python cli.py scenario broken-vs-clean`
   reports 8 vs 0 failure modes respectively.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints SKILL.md.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, AnthonyAlcaraz / forthcoming),
Chapter 4 — The Problem section (Letta Leaderboard 8 failure modes).
Composes with sibling Ch4 skills: bi-temporal-edge / hierarchical-memory /
graphiti-incremental-update.
