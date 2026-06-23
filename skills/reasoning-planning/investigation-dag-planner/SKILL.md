---
name: investigation-dag-planner
description: |
  Dynamic-DAG construction for a planning node (Ch5 Example 5-15 + the DevOps
  "Constructing the Investigation DAG" section). Given hypotheses/tasks with
  dependency constraints, compute a topological-level decomposition: each level
  is a phase of tasks that can run concurrently, ordered within-phase by
  priority. The estimated duration of a parallel phase is the MAX over its
  concurrent tests, and execution runs phase-by-phase with early termination
  once a hypothesis is confirmed. Detects dependency cycles as malformed plans.
  Use when a planning node must decide which work is parallel-safe and in what
  order — incident-investigation hypothesis testing, multi-track research,
  multi-party claim processing. NOT for purely linear pipelines (one task per
  level — annotation overhead exceeds benefit), NOT for runtime fault-isolation
  (that is event-driven orchestration), NOT for picking a model or pipeline
  shape (that is architecture selection).
osmani-pattern: Generator
ghosh-layer: Orchestration
chapter-source: "Agentic Graph RAG (O'Reilly) Ch5 — Reasoning & Planning — Dynamic DAG construction (Example 5-15) + Constructing the Investigation DAG (DevOps agent)"
references:
  - "Ch5 Example 5-15 — GraphConstructingPlanningNode: extract dependencies, identify parallel groups, construct optimal DAG, parallelism_factor"
  - "Ch5 'Constructing the Investigation DAG' — phases, parallel-phase duration = max of concurrent tests, early termination on confirmation"
  - "Ch5 'Task graphs at developer scale' — Beads bd ready = topological sort of unblocked tasks"
---

# Investigation DAG Planner

## Overview

Real investigation rarely follows a linear path. When multiple hypotheses
exist, some can be tested in parallel while others have dependencies. Testing
whether the database is overloaded and whether the payment service has memory
pressure use different data sources — they can run simultaneously. But testing
for a network partition between two services only makes sense after ruling out
simpler explanations.

This is the dynamic-DAG-construction pattern (Example 5-15) applied to incident
diagnosis. The planner:

1. Analyzes dependencies between hypotheses/tasks.
2. Identifies groups that can safely run in parallel (a topological level —
   the same computation `bd ready` performs in Beads, and `parallel_groups` in
   Example 5-15).
3. Organizes them into phases. Within each phase, tasks are ordered by priority
   (the historically/structurally most-likely hypothesis first).
4. Estimates each parallel phase's duration as the **max** of its concurrent
   tests, since they run concurrently — not the sum.

Execution then proceeds phase by phase with **early termination**: as soon as a
hypothesis is confirmed with sufficient corroborating evidence, remaining
phases are skipped. A dependency cycle raises `CycleError` — that is a malformed
plan, surfaced rather than silently mis-executed.

In the DevOps latency investigation (account `123456789012`), the checkout
latency spike yields three hypotheses. The DAG groups `db_pool_exhaustion` and
`payment_memory_pressure` into one parallel phase (different data sources);
`network_partition` depends on ruling out the pool hypothesis, so it lands in a
later phase. When the pool hypothesis confirms in the first phase, early
termination skips the network-partition test entirely.

## When to Use

- A planning node must decide which tasks are parallel-safe and order phases
- Incident-investigation hypothesis testing, multi-track research, multi-party
  claim processing (the chapter's multi-vehicle-accident example)
- You want an explicit duration estimate and an auditable phase structure

Phrases: "construct an investigation DAG", "which hypotheses can run in
parallel", "topological phases", "parallel groups", "early termination on
confirmation", "task graph".

## When NOT to Use

- The work is genuinely linear (one task per level) — the DAG annotation
  overhead exceeds the benefit
- You need runtime fault isolation / replay across distributed workers (that is
  event-driven orchestration, a different layer)
- The decision is which model or pipeline shape to use (architecture selection)

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | task rows (id, depends_on, duration_s, priority) | `lib.tasks_from_dicts(rows)` | `{id: Task}` map | unknown-dep / self-dep raises before planning |
| 2 | task map | `lib.topological_phases(tasks)` | list of levels (each a parallel group) | every task appears once; deps land in an earlier level; cycle raises `CycleError` |
| 3 | task map | `lib.build_investigation_dag(tasks)` | `InvestigationDAG` (phases, parallelism_factor, total/critical-path) | parallel-phase duration == max of its tasks; total == sum of phase maxima |
| 4 | dag + task map + `test_fn` | `lib.execute_with_early_termination(...)` | trace with confirmed id + phases_run/skipped | once confirmed, later phases are skipped |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Just test every hypothesis sequentially — simpler." | The chapter's whole point: parallel phases "slash latency" and early termination "can dramatically reduce investigation time." Independent hypotheses tested serially waste the parallel window. |
| "Sum the durations to estimate total time." | Wrong for parallel phases. The chapter is explicit: "the estimated duration for a parallel phase is the maximum duration of its individual tests since they run concurrently." Summing within a phase over-estimates. |
| "Run all phases to be thorough." | Early termination is the optimization: "As soon as a hypothesis is confirmed with sufficient corroborating evidence, there is no need to continue testing alternatives." Thoroughness past confirmation is wasted compute. |
| "A cycle just means re-run until it settles." | A cycle is a malformed plan — there is no valid topological order. Surface it (`CycleError`) so the planner fixes the dependency, do not loop. |

## Red Flags

- **One giant phase with everything in it.** No dependencies were extracted —
  either the task really is embarrassingly parallel, or the dependency
  extraction failed and you are about to test in an unsafe order.
- **Critical path == task count.** Every task depends on the previous one;
  this is a linear pipeline wearing a DAG costume — use a sequential pipeline.
- **`parallelism_factor == 0` on a multi-hypothesis investigation.** The
  planner found no parallel-safe group; check that independent hypotheses were
  not given spurious dependencies.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report:
   - independent tasks land in the same (first) phase
   - a dependent task lands strictly after its dependency
   - parallel-phase duration equals the max of its tasks; total equals sum of maxima
   - a cycle raises `CycleError`
   - early termination skips phases after a confirmation
   - within-phase ordering respects priority
2. **Verify CLI help.** Exits 0 and prints the SKILL.md description.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, forthcoming) Ch5 — Reasoning &
Planning: "Dynamic DAG construction" (Example 5-15,
`GraphConstructingPlanningNode`) and the DevOps agent's "Constructing the
Investigation DAG" section (phases, max-duration parallel model, early
termination on confirmation). The topological-sort framing connects to the
chapter's "Task graphs at developer scale" (Beads `bd ready`).
