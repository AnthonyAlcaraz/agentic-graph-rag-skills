---
name: loop-pipeline-router
description: |
  The conditional-edge routing that turns a validate node into a bounded
  self-correcting loop (Ch5 Loop Pipeline + Error-handling strategies, Examples
  5-6/5-9). Consumes a validation result, an error severity (correctable vs
  fundamental), and a retry budget, and returns exactly one of: proceed,
  refine (loop back with a remaining retry), fallback (alternative strategy
  once retries are exhausted), or terminate-with-partial (fundamental error).
  The finite retry budget is the explicit bound that prevents infinite loops.
  Use when first-attempt success is unrealistic and validation can identify
  correctable errors — plan refinement, documentation-gap re-requests,
  transient-failure recovery. NOT for strict sequential pipelines with no
  feedback (use a sequential pipeline), NOT for parallel branch reconciliation
  (that is a merge/tree concern), NOT as a substitute for the validator itself
  (this routes on the validator's output; it does not validate).
osmani-pattern: Reviewer
ghosh-layer: Workflow
chapter-source: "Agentic Graph RAG (O'Reilly) Ch5 — Reasoning & Planning — Loop Pipeline (Example 5-6) + Error-handling strategies (Example 5-9)"
references:
  - "Ch5 Example 5-6 — check_plan_validity: execute_plan / refine_plan / fallback_planner with retry_count < 3 and recursion_limit"
  - "Ch5 Example 5-9 — route_after_validation: proceed / refine / fallback_strategy / terminate_with_partial by severity"
---

# Loop Pipeline Router

## Overview

Loop pipelines introduce feedback for self-correction when perfect
first-attempt reasoning is unrealistic. The decision that makes a loop a loop
is the conditional edge after the validate node. Naively this is
"valid -> proceed, else -> retry" (Example 5-6), but production needs the
nuance of Example 5-9: distinguish **correctable** errors (refine) from
**fundamental** ones (stop), and handle the retries-exhausted case
(fall back to an alternative strategy) so the loop neither terminates
prematurely nor spins forever.

The unified decision table:

```
valid                            -> proceed
correctable + retries remaining  -> refine (retry_count += 1, loop back)
correctable + retries exhausted  -> fallback_strategy
fundamental                      -> terminate_with_partial
```

The finite retry budget (Example 5-6's `retry_count < 3` / `recursion_limit`)
is the explicit termination guarantee. An invalid result with no error
diagnostic is treated as fundamental — you cannot safely refine what you cannot
diagnose.

In the DevOps latency investigation (account `123456789012`), document
verification on a related claim returns "incomplete" — the operative report
lacks anesthesia-time records. That is a **correctable** error: refine
(request the specific missing documentation, re-verify), bounded to three
request cycles before escalating. A schema-level contradiction in the plan
("synchronous AND event-driven for the same operation") is **fundamental**:
terminate with partial results rather than burn the retry budget on an
unfixable error.

## When to Use

- First-attempt success is unrealistic and a validator can flag correctable
  errors
- Documentation-gap re-requests, plan refinement, transient-failure recovery
- You need a guaranteed-terminating self-correction loop with an audit trace

Phrases: "loop pipeline", "refine and re-validate", "retry with feedback",
"correctable vs fundamental error", "fallback planner", "recursion limit".

## When NOT to Use

- Strict sequential pipeline with no feedback (use a sequential pipeline)
- Parallel-branch reconciliation (that is a merge/tree concern)
- The validator does not distinguish error kinds (then add severity to the
  validator first; routing on undifferentiated errors collapses to blind retry)

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | is_valid, error, retry_count, max_retries | `lib.route_after_validation(...)` | `RouteResult(decision, retry_count, rationale)` | valid->proceed; correctable+budget->refine(+1); correctable+exhausted->fallback; fundamental->terminate |
| 2 | attempt_fn, validate_fn, max_retries, fallback_fn | `lib.run_loop(...)` | dict (decision, candidate, iterations, trace) | loop always terminates; iterations <= max_retries |
| 3 | run_loop trace | inspect `trace` | per-iteration routing decisions | each refine increments retry_count; one terminal decision |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Just retry until it passes." | Unbounded retry is the infinite-loop failure mode. The chapter bounds it explicitly (`retry_count < 3`, `recursion_limit=10`). After the budget, fall back — do not spin. |
| "Any failure should retry." | No — fundamental errors do not become correct by retrying (Example 5-9 routes them to `terminate_with_partial`). Retrying a schema contradiction wastes the whole budget on an unfixable error. |
| "If retries run out, just give up entirely." | Exhausted correctable retries route to a *fallback strategy*, not termination. The chapter distinguishes "retries exhausted" (try another approach) from "fundamental" (stop). |
| "An invalid result with no error detail — I'll guess and refine." | You cannot safely refine what you cannot diagnose. Treat missing-diagnostic-on-invalid as fundamental and terminate with partial; surfacing it beats guessing. |

## Red Flags

- **Every error is classified correctable.** The validator is not detecting
  fundamental errors; the loop will exhaust the budget then fall back on
  genuinely unfixable inputs.
- **`iterations` regularly hits `max_retries` then falls back.** The refine
  step is not actually improving the candidate — the feedback is not making it
  back into `attempt_fn`.
- **No terminal `proceed` across many runs.** The validator threshold may be
  unsatisfiable, or refine is a no-op; the loop is theatre.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report:
   - valid -> proceed; fundamental -> terminate_with_partial
   - correctable with budget -> refine and increments retry_count
   - correctable with budget exhausted -> fallback_strategy
   - invalid-with-no-error -> terminate_with_partial
   - `run_loop` terminates and never exceeds `max_retries` iterations
   - a candidate that becomes valid after N refines yields proceed at N
2. **Verify CLI help.** Exits 0 and prints the SKILL.md description.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, forthcoming) Ch5 — Reasoning &
Planning: "Loop Pipeline: Iterative Refinement" (Example 5-6,
`check_plan_validity`) and "Error-handling strategies" (Example 5-9,
`route_after_validation`). The bounded-loop / `recursion_limit` guarantee is
from Example 5-6.
