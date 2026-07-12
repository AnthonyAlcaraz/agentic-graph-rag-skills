---
name: constraint-guided-plan-validator
description: |
  Validate a generated plan against extracted domain constraints AND the
  agent's capability model before execution (Ch5 Constraint-guided planning,
  Example 5-14, plus the DevOps hypothesis-formation capability filter). Scores
  the plan 0..1, returns structured per-step feedback so a planning node can
  refine when the score falls below threshold, and filters steps the agent is
  not authorized to perform (e.g. a step needing write access when the agent
  holds read-only monitoring). Forbidden-action and capability violations are
  HARD — a plan the agent cannot legally execute does not pass regardless of
  score. Use in regulated or capability-bounded environments where plans must
  respect business rules and operational authority before any action runs. NOT
  for free-form creative tasks with no constraints, NOT for validating
  execution results after the fact (this gates the plan, not the outcome), NOT
  as the constraint extractor itself (it consumes extracted constraints).
osmani-pattern: Reviewer
ghosh-layer: Workflow
chapter-source: "Agentic GraphRAG (O'Reilly) Ch5 — Reasoning & Planning — Constraint-guided planning (Example 5-14) + DevOps hypothesis-formation capability-model filter + Ontological grounding"
references:
  - "Ch5 Example 5-14 — ConstraintAwarePlanningNode: extract constraints, generate plan, verify, refine if score < THRESHOLD"
  - "Ch5 'Integrating the Knowledge Graph for Grounded Hypotheses' — capability-model filter removes hypotheses the agent cannot execute"
  - "Ch5 'Ontological Grounding' — domain/range validation rejects semantically invalid operations before they corrupt the decision"
---

# Constraint-Guided Plan Validator

## Overview

In regulated environments a planning node must ensure plans respect domain
constraints and business rules *before* committing to execution (Example 5-14):
extract the constraints from the request, generate the plan, validate, and if
validation fails, refine with the validator's feedback. The chapter pairs this
with two further gates:

- **Capability-model filter** (DevOps hypothesis-formation node): the agent's
  operational boundaries are queryable data specifying which actions it may
  perform and at what privilege. "A hypothesis requiring direct database access
  gets filtered if the agent only has read-only monitoring permissions." This
  prevents proposing investigations it cannot execute.
- **Ontological grounding**: domain/range validation rejects operations that
  are syntactically valid but semantically nonsensical before they corrupt the
  decision.

This skill validates a plan against extracted constraints and a capability
model, returning a 0..1 conformance score plus structured per-step feedback.
Below threshold (0.8) the plan should be refined and re-validated.
Forbidden-action and capability violations are **hard**: any single one forces
`passed=False` no matter the score — a plan the agent cannot legally execute is
not "mostly fine."

In the DevOps latency investigation (account `123456789012`), the agent holds
read-only monitoring permissions. A remediation plan whose step proposes
`modify_db` (write privilege) fails the capability gate and is sent back to the
planner; a plan that proposes only `query_metrics` and `read_logs` (read) with
the required `record_incident` step, within the 30-day emergency regulatory
deadline, passes.

## When to Use

- Regulated / capability-bounded environments (insurance, healthcare, finance,
  privileged DevOps)
- A planning node must gate plans against business rules and operational
  authority before any action runs
- You want a refine-on-low-score loop driven by structured feedback

Phrases: "validate the plan against constraints", "capability model",
"is the agent authorized", "constraint-guided planning", "plan conformance
score", "refine plan with feedback".

## When NOT to Use

- Free-form creative tasks with no domain constraints
- Validating execution *results* after the fact (this gates the plan, not the
  outcome)
- You have no constraints or capability model to check against (then there is
  nothing to validate)

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | constraint spec dict | `lib.extract_constraints(spec)` | list of `Constraint` | max_steps / deadline / forbidden / required parsed |
| 2 | plan rows | `lib.steps_from_dicts(rows)` | list of `PlanStep` | each step carries action + privilege |
| 3 | plan + capability | `lib.filter_executable_steps(plan, cap)` | list of capability `Violation`s | a write step under read-only capability is flagged |
| 4 | plan + constraints + capability | `lib.verify(...)` | `ValidationResult(score, violations, passed)` | score in [0,1]; hard violations force passed=False; `.feedback` lists per-violation messages |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Validate the result, not the plan — faster." | The chapter validates *before* execution so the agent "won't attempt searches outside specified date ranges, exceed computational budgets, or violate domain rules." A bad plan caught post-execution has already taken the unsafe action. |
| "Score is 0.85, ship it." | A high score does not override a hard violation. A forbidden action or an unauthorized step makes the plan illegal to run; `passed` is False regardless of score. Treat hard violations as blocking, not as score deductions. |
| "The agent can probably do that step anyway." | The capability model is the authority, not the agent's optimism. A step needing write access when the agent holds read-only is filtered — proposing investigations it cannot execute is a named failure mode. |
| "Refining wastes a turn — just run the plan." | Refine-on-low-score is the whole pattern (Example 5-14): the validator's feedback turns an invalid plan into a valid one before execution, which is far cheaper than a failed or non-compliant action. |

## Red Flags

- **Every plan scores 1.0.** No constraints were extracted or the capability
  model is empty — the gate is inert.
- **Hard violations present but `passed=True`.** A bug — capability /
  forbidden-action violations must force `passed=False`.
- **Capability model allows every action at admin.** The operational-authority
  boundary is not actually bounded; the filter cannot protect against
  over-privileged steps.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report:
   - a conforming plan passes with score 1.0
   - too-many-steps drops the score below threshold
   - a missing required action is flagged
   - a forbidden action is a hard violation (passed=False)
   - a write step under read-only capability is a hard violation
   - a deadline-exceeding step is flagged per-step
   - score stays within [0,1] and `.feedback` enumerates violations
2. **Verify CLI help.** Exits 0 and prints the SKILL.md description.

## Security Posture

- **Prompt injection.** Plans are typically LLM-generated from untrusted
  requests - exactly why they are validated. Plan steps and constraint specs
  are parsed as data, never executed; a malicious step name can at most fail
  validation. The constraint spec and capability model must come from the
  trusted policy source, not from the same LLM that wrote the plan.
- **Data exfiltration.** No network calls, no file writes. Plans and
  constraints may describe privileged operations; they stay in-process and
  surface only in the stdout feedback the caller owns.
- **Privilege escalation.** This gate exists to block it: a write step under a
  read-only capability is a hard violation. Keep it that way - `passed=False`
  on hard violations must never be softened into a score deduction, and the
  gate composes with (never replaces) boundary-side IAM enforcement.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien) Ch5 — Reasoning &
Planning: "Constraint-guided planning" (Example 5-14,
`ConstraintAwarePlanningNode`), the capability-model filter from "Integrating
the Knowledge Graph for Grounded Hypotheses," and the domain/range checks from
"Ontological Grounding: Keeping Your Agent in Reality."
