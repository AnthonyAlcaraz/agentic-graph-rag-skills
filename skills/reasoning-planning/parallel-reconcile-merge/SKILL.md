---
name: parallel-reconcile-merge
description: |
  Controlled-parallelism window for a tree pipeline (Ch5 Tree Pipeline +
  "The architecture of controlled parallelism" + state reducers, Examples
  5-7/5-8/5-16). Dispatches independent branches that read different data and
  write to separate channels, isolates errors per-branch so one branch's
  failure neither cascades nor corrupts shared state, then reconciles the
  survivors with a reducer-style deterministic merge and decides completion as
  all-or-nothing or partial-coverage. Surfaces the union of every branch's red
  flags — a failed branch never silently drops a flag. Use when a planning node
  has verified true independence between branches (fraud / provider / pricing
  verification; parallel hypothesis tests). NOT for branches that share mutable
  state or make joint decisions (that is uncoordinated parallelism, the failure
  mode), NOT for strictly sequential dependent steps, NOT as a thread pool
  (this is the isolation+merge contract; the concurrency mechanism is a
  production swap).
osmani-pattern: Pipeline
ghosh-layer: Orchestration
chapter-source: "Agentic GraphRAG (O'Reilly) Ch5 — Reasoning & Planning — Tree Pipeline (Example 5-7) + State management reducers (Example 5-8) + The Multi-Agent Debate / controlled parallelism (Example 5-16)"
references:
  - "Ch5 Example 5-7 — explore_reasoning_paths: parallel hypothesis verification via Send API"
  - "Ch5 Example 5-8 — state reducers (add_messages, operator.add): deterministic merge regardless of execution order"
  - "Ch5 Example 5-16 / 'The architecture of controlled parallelism' — independence verification, error isolation, ontologically-validated merge"
---

# Parallel Reconcile-Merge

## Overview

Parallelism itself is not the enemy — uncoordinated parallelism is. The
chapter's safe pattern embeds a parallel window inside a sequential control
flow: planning verifies the branches are truly independent, the branches run
simultaneously reading different data sources and writing to separate channels,
and only the merge node combines them.

This skill implements the execution + reconciliation half:

- **Per-branch error isolation** (tree-pipeline error aggregation): each branch
  runs in isolation; an exception is caught and recorded in that branch's own
  result. "One branch's failure shouldn't cascade to others or corrupt shared
  state." Branches receive a copy of context and never write shared state —
  only the merge node combines them.
- **Reducer-style deterministic merge** (Example 5-8): merge successful branch
  values with a reducer (`add`, `extend`, `union`, `max`, `min`) so the result
  is "deterministic merging regardless of execution order."
- **Completion policy**: `all_or_nothing` (every branch must succeed) vs
  `partial_coverage` (a quorum suffices — "sometimes three successful branches
  out of four provide sufficient coverage").
- **Flag union**: any red flag from any branch is surfaced; a failed sibling
  never silently drops another branch's flag.

In the DevOps latency investigation (account `123456789012`), the planner spawns
parallel hypothesis tests — database connection-pool metrics and payment-service
memory profiles — reading different data sources. The pool branch raises a
`pool_exhausted` flag; the memory branch comes back normal. Reconcile surfaces
the flag, merges both findings, and (under all-or-nothing for a confirmation
phase) reports completion only if both branches succeeded. The analogous claims
case runs fraud / provider-credentials / medical-necessity branches the same
way: any flag from any branch affects the final decision.

## When to Use

- A planning node has verified branch independence (different data sources, no
  shared decision, no shared mutable state)
- Parallel hypothesis tests, multi-aspect verification (fraud / pricing /
  credentials), parallel research tracks
- You need deterministic merge + a quorum/all-or-nothing completion policy +
  flag aggregation

Phrases: "merge parallel branches", "reconcile branch results", "controlled
parallelism", "error isolation across branches", "all-or-nothing vs partial
coverage", "state reducer merge".

## When NOT to Use

- Branches share mutable state or make a joint decision (uncoordinated
  parallelism — the documented failure mode; serialize or re-decompose first)
- Strictly sequential dependent steps (use a sequential pipeline)
- You actually need concurrency tuning — this is the isolation+merge contract;
  swap in threads/asyncio/Send API for the dispatch mechanism in production

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | branch_fns (name -> fn), context | `lib.execute_branches(...)` | list of `BranchResult` | a raising branch yields ok=False and does NOT abort siblings |
| 2 | branch values + reducer name | `lib.reduce_field(values, REDUCERS[name])` | merged value | merge is order-independent for commutative reducers |
| 3 | results + mode + min_success + reducer | `lib.reconcile(...)` | `MergeOutcome` | all_or_nothing fails if any branch failed; partial_coverage completes at quorum; flags are unioned |
| 4 | branch_fns + context (+policy) | `lib.run_parallel_window(...)` | end-to-end `MergeOutcome` | succeeded/failed partition matches branch outcomes |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Just let the branches share state — it's simpler." | Shared mutable state across parallel branches is exactly the uncoordinated-parallelism failure Cognition documents. The chapter's branches "read from different knowledge graph regions and write their findings to separate channels that only the orchestrator combines." |
| "If one branch fails, fail the whole thing." | Only under all-or-nothing. The chapter notes "three successful branches out of four provide sufficient coverage" for many tasks — partial-coverage is a first-class mode. Pick the mode per task; do not hard-fail by default. |
| "A crashed branch — just drop it and its flags." | Error isolation records the failure; flag union still surfaces every flag from every branch. A dropped flag (e.g. a fraud signal) is a silent correctness hole. Failure isolation is not the same as discarding signal. |
| "Combine the branch scores any way — order won't matter." | Only commutative reducers are order-safe. The reducer pattern (Example 5-8) exists precisely so merge is "deterministic regardless of execution order"; ad-hoc combination reintroduces race-order dependence. |

## Red Flags

- **Branches mutate `context` and expect siblings to see it.** They get copies
  by design; a branch relying on another branch's write is not independent and
  should not be in this window.
- **`all_or_nothing` chosen for an exploratory fan-out.** One flaky branch
  fails the whole window when partial coverage would have sufficed — wrong mode
  for the task.
- **Flags empty but a branch reported a problem in its value.** The branch is
  not surfacing red flags through the flags channel; the merge cannot union
  what it cannot see.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report:
   - a raising branch is isolated (ok=False) and siblings still run
   - all_or_nothing completes only when every branch succeeds
   - partial_coverage completes at the quorum and fails below it
   - flags are unioned across branches (including from non-failing siblings)
   - reducer merge is order-independent for a commutative reducer
   - succeeded/failed partition matches branch outcomes
2. **Verify CLI help.** Exits 0 and prints the SKILL.md description.

## Security Posture

- **Prompt injection.** Branch results are untrusted - branches typically run
  LLM reasoning over untrusted sources. The merge treats values and flags as
  data (reducers, unions), never executing them; one compromised branch can
  bias the merged value but cannot rewrite siblings' channels, because
  branches get context copies and only the merge node combines.
- **Data exfiltration.** No network calls, no file writes in the window
  itself. The merge concentrates findings from every branch into one outcome -
  apply per-branch data-access policy upstream, since the merged report sees
  everything any branch saw.
- **Privilege escalation.** No shell invocation, no eval. The guarded property
  is signal integrity: flag union guarantees a failed or malicious sibling
  cannot suppress another branch's fraud/red flag, and completion policy - not
  any single branch - decides whether the window counts as done.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien) Ch5 — Reasoning &
Planning: "Tree Pipeline: Parallel Exploration" (Example 5-7), "State
management across pipelines" reducer pattern (Example 5-8), and "The
Multi-Agent Debate" / "The architecture of controlled parallelism" (Example
5-16) — independence verification, per-branch error isolation, and the
ontologically-validated merge.
