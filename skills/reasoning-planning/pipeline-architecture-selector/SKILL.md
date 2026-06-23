---
name: pipeline-architecture-selector
description: |
  Treat pipeline-architecture choice as a routing decision inside a
  meta-pipeline (Ch5 Hybrid Architectures, Examples 5-10/5-11). A single
  analysis pass over task characteristics — complexity and answer-uncertainty
  — selects sequential (simple + certain), tree (high uncertainty, explore
  hypotheses), or loop (iterative refinement); a resource-aware wrapper then
  degrades gracefully when memory or time budgets bite (tree -> sequential
  fallback, loop -> single-pass best effort). Use when the same agent must
  handle tasks of variable complexity and committing to one architecture
  wastes resources on simple tasks or under-serves hard ones. NOT for systems
  with a single fixed task shape (just hard-code the pipeline), NOT for
  choosing between models (that is model selection), NOT for sub-50-task/day
  systems where event-driven scaling is the real question.
osmani-pattern: Inversion
ghosh-layer: Orchestration
chapter-source: "Agentic Graph RAG (O'Reilly) Ch5 — Reasoning & Planning — Hybrid Architectures (Dynamic architecture selection + Graceful degradation, Examples 5-10/5-11)"
references:
  - "Ch5 Example 5-10 — analyze_and_route(complexity, uncertainty) -> sequential / tree / loop"
  - "Ch5 Example 5-11 — route_with_constraints: resource-aware graceful degradation"
---

# Pipeline Architecture Selector

## Overview

Production tasks have variable complexity. A research query about a
well-documented topic needs simple sequential processing; an ambiguous query
exploring cutting-edge developments needs parallel hypothesis exploration with
iterative refinement. Committing to one pipeline shape means simple tasks pay
the parallel-coordination tax and hard tasks get under-served.

The chapter's answer: make architecture selection a routing decision inside a
meta-pipeline. Run one cheap analysis pass over the task — `complexity` and
`uncertainty` — then route:

```
if complexity < SIMPLE and uncertainty < LOW:   sequential
elif uncertainty > HIGH:                         tree (explore hypotheses)
else:                                            loop (iterative refinement)
```

Then wrap that with runtime-constraint checks so the agent **delivers results
within constraints rather than failing or timing out** (Example 5-11):

- ideal=tree but free memory < threshold  ->  `sequential_fallback`
- ideal=loop but time budget < one iteration  ->  `single_pass_best_effort`

Per the chapter: "Build these fallback paths explicitly rather than relying on
exception handling — graceful degradation is a feature, not an error case."

In the DevOps latency investigation (account `123456789012`), "what is the
checkout error rate?" routes sequential; "why did checkout latency spike from
200ms to 2.5s?" scores high uncertainty and routes to a tree of parallel
hypothesis tests — unless memory is tight, in which case it degrades to
sequential testing of the same hypotheses.

## When to Use

- One agent handling a stream of tasks with genuinely variable complexity
- You observe simple tasks paying parallel-coordination overhead, or hard
  tasks failing under a too-simple pipeline
- You need an explicit, auditable record of WHY a task took a given path

Phrases: "route to the right pipeline", "dynamic architecture selection",
"sequential vs tree vs loop", "graceful degradation", "resource-aware routing".

## When NOT to Use

- The task shape is fixed (just hard-code sequential / tree / loop)
- The decision is which *model* to call (that is model selection)
- The real scaling question is in-process vs event-driven (>50 tasks/day) —
  that is a different axis the chapter covers separately
- Complexity and uncertainty cannot be estimated cheaply (then the analysis
  pass costs more than it saves)

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | task query string | `lib.assess_task_complexity(q)` / `lib.estimate_uncertainty(q)` | two floats in 0..1 | both in [0,1]; a multi-service investigation scores higher than a single-field lookup |
| 2 | complexity, uncertainty | `lib.analyze_and_route(c, u)` | one of sequential / tree / loop | simple+certain -> sequential; high uncertainty -> tree; middle -> loop |
| 3 | + available_memory_mb, remaining_budget_s | `lib.route_with_constraints(...)` | `RouteDecision` (ideal + final + degraded + reason) | tree under memory floor degrades; loop under time floor degrades; otherwise final==ideal |
| 4 | raw query + constraints | `lib.route_query(q, mem, budget)` | end-to-end `RouteDecision` | `reason` names the constraint when degraded |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Just always use a tree — parallel is fastest." | Parallel coordination is overhead the chapter explicitly bounds: simple+certain tasks get sequential because "the predictability is a feature." Uncoordinated parallelism is the failure mode, not the win. |
| "The routing LLM call adds latency, skip it." | The chapter measures it: "a single analysis pass... adding minimal latency while dramatically improving resource efficiency." One classification call gates every downstream path choice. |
| "If memory runs low I'll just let it crash and retry." | Graceful degradation is a designed path, not an exception. Example 5-11 returns `sequential_fallback` / `single_pass_best_effort` so the agent still delivers a result under the constraint. |
| "Complexity and uncertainty are the same thing." | They are two axes (Axis 1 context control, Axis 2 workflow autonomy in the foundations). A simple-but-uncertain task and a complex-but-certain task route differently. Collapsing them reintroduces the one-dial failure mode. |

## Red Flags

- **Everything routes to one architecture.** The estimators are not
  discriminating — either the thresholds are wrong for the domain or the
  heuristics need the production LLM call.
- **`degraded` fires on most tasks.** Resource floors are mis-set or the host
  is genuinely under-provisioned; selecting a richer architecture you cannot
  run is theatre.
- **`final != ideal` with `reason == "ideal path available"`.** A bug — the
  degradation branch and the reason string are out of sync.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report:
   - simple+certain -> sequential, high-uncertainty -> tree, middle -> loop
   - tree under the memory floor degrades to `sequential_fallback`
   - loop under the time floor degrades to `single_pass_best_effort`
   - unconstrained routing leaves `final == ideal` and `degraded == False`
2. **Verify CLI help.** Exits 0 and prints the SKILL.md description.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, forthcoming) Ch5 — Reasoning &
Planning, "Hybrid Architectures" section: Dynamic architecture selection
(Example 5-10, `analyze_and_route`) and Graceful degradation (Example 5-11,
`route_with_constraints`). The two-axis framing (context control vs workflow
autonomy) is from the chapter's Foundations section.
