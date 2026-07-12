---
name: schema-pattern-selector
description: |
  Select and validate the four agent schema design patterns from Ch3 —
  Event-Centric (temporal reasoning), Contextual-Boundary (scope/validity
  boundaries), Multi-Perspective (contradictory viewpoints with attribution
  and confidence), and Capability-Model (agent self-awareness of authority
  limits). Given a free-text description of a knowledge shape, it scores which
  pattern(s) fit and flags composition when several apply; given a pattern
  instance, it validates the required relationships/fields without which the
  pattern is broken. Use when modeling knowledge for agent reasoning, when
  deciding how to structure events / contexts / conflicting data / agent
  authority, or when reviewing a schema for the missing temporal- or
  attribution-relationship that breaks the pattern. NOT for choosing the
  graph model class (use graph-model-selector), NOT for runtime authorization
  enforcement (use capability-authorization-gate), NOT for entity-centric data
  with no temporal/perspectival/scope dimension (a plain node is fine).
osmani-pattern: Reviewer
ghosh-layer: Primitive
chapter-source: "Agentic GraphRAG (O'Reilly) Ch3 — Knowledge Representation — Schema Design Patterns (Examples 3-3, 3-4, 3-5)"
references:
  - "Ch3 Event-Centric (Example 3-3), Contextual-Boundary (Example 3-4), Multi-Perspective (Example 3-5), Capability-Model"
  - "Ch3 Tip: hybrid composition of schema patterns"
  - "Ch3 DevOps section: event-centric deployments, multi-perspective config drift (Example 3-14)"
---

# Schema Pattern Selector

## Overview

Effective agent reasoning begins with schema patterns designed for machine
cognition across temporal, contextual, and perspectival dimensions. Ch3 names
four:

- **Event-Centric** — structure knowledge around occurrences, not static
  entities. A `Meeting` event with participants, start/end timestamps, location,
  and `hasPrecedingEvent` / `hasFollowingEvent` links. Enables "what meetings
  did Alice attend before the project review?" In DevOps: a `DeploymentEvent`
  node with timestamp + git commit + affected services (Example 3-14).
- **Contextual-Boundary** — encapsulate information within explicit scopes. A
  `Context(Project-X)` that `contains` tasks, is `validDuring` a time range, and
  `appliesTo` a team. Prevents context mixing — the agent won't apply Task-1's
  facts to the wrong team or period.
- **Multi-Perspective** — model contradictory viewpoints with attribution. A
  `Revenue-Forecast` where Finance says 10M (confidence 0.8) and Sales says 12M
  (confidence 0.7), each `according-to` a source. In DevOps: config drift where
  Terraform-state and AWS-api are two perspectives on the same setting.
- **Capability-Model** — represent the agent's own capabilities, requirements,
  and authorization limits as queryable nodes. A support agent that can answer
  product questions (Public) but needs Supervisor authorization and a $500 limit
  to process refunds.

The selector matches a knowledge-shape description to the fitting pattern(s),
flagging composition when several apply (Ch3 Tip: an event can carry
multi-perspective viewpoints; a capability can be bounded by contextual
constraints). The validator enforces each pattern's contract — the
relationships and fields without which the pattern is broken: an event MUST
have a temporal link (else it is just an entity); a context MUST declare a
scope boundary; every perspective MUST attribute its value to a source with
confidence in [0,1] (else contradiction-handling loses its attribution); every
capability MUST declare an authorization level.

## When to Use

- Modeling events, contexts, conflicting data, or agent authority for reasoning
- Deciding which schema pattern (or composition) a knowledge shape needs
- Reviewing a graph schema for the missing temporal/scope/attribution link
- DevOps: deployment-history modeling, config-drift detection structure

Phrases: "event-centric", "contextual boundary", "multi-perspective",
"capability model", "schema design pattern", "temporal reasoning structure",
"model conflicting data", "config drift schema".

## When NOT to Use

- **Choosing the graph model class.** Use `graph-model-selector` (LPG vs RDF vs
  hypergraph); this picks the schema pattern within a model.
- **Runtime authorization enforcement.** This validates that a Capability-Model
  instance is well-formed; `capability-authorization-gate` enforces the limit at
  request time.
- **Plain entity data.** If the knowledge has no temporal, scope, perspectival,
  or capability dimension, a simple node/edge is correct — no pattern needed.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | free-text knowledge-shape description | `lib.select_patterns(desc)` | `[{pattern, score, matched_signals}, ...]` desc | top pattern matches the dominant signal class |
| 2 | same | `lib.recommend_pattern(desc)` | `{recommended, scores, contract, compose?}` | composition flagged when 2+ patterns score > 0 |
| 3 | pattern + instance dict | `lib.validate_instance(pattern, instance)` | `{valid, errors, pattern}` | required relationships/fields enforced per contract |
| 4 | event instance | `lib.validate_instance("event_centric", ...)` | invalid if no temporal link | enforces "event needs >= 1 temporal relationship" |
| 5 | multi-perspective instance | `lib.validate_instance("multi_perspective", ...)` | invalid if a perspective lacks source/confidence or confidence outside [0,1] | enforces attribution contract |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "I'll model the deployment as a property on the service node." | Then "what deployments affected payment-service last week?" and "which commit deployed v2.3.1?" become impossible. The Event-Centric pattern makes the deployment a first-class node with temporal links precisely so the agent can reason about sequence and cause/effect (Example 3-14). |
| "Conflicting values mean my data is dirty — I'll pick one and move on." | Forcing a single value loses the disagreement the agent needs to reason about. Multi-Perspective turns the contradiction into a structural advantage: each value is attributed to a source with confidence, and config-drift detection becomes a graph traversal instead of custom comparison logic. |
| "Context boundaries are bureaucratic — facts are facts." | Context mixing is a named, common source of reasoning errors. Without `validDuring` / `appliesTo`, the agent applies Task-1's engineering-team facts to the wrong team or period. The boundary is what scopes the inference correctly. |
| "Capabilities are obvious from the code — I don't need them in the graph." | "Obvious from the code" means not queryable at planning time. The Capability-Model makes authorization a node the agent checks BEFORE acting (refund $600 vs $500 limit -> escalate). Vague operational guidelines become concrete, queryable structure. |
| "The selector said compose two patterns — that's too complex." | Ch3 explicitly recommends hybrids: an event can carry multi-perspective viewpoints, a capability can be bounded by contextual constraints. Composition is the intended design, not accidental complexity. |

## Red Flags

- **An event node with no `hasStartTime`/`hasPrecedingEvent`/etc.** It is an
  entity wearing an event label; temporal queries will return nothing.
- **A perspective with no confidence or a confidence outside [0,1].** The
  attribution is unusable for source-weighted reasoning; the validator fails it.
- **A context with `contains` but no `validDuring`/`appliesTo`.** No scope
  boundary means no protection against context mixing — the pattern's whole job.
- **A capability with no authorization-level.** The agent cannot decide whether
  to act or escalate; the self-awareness is incomplete.
- **Selector recommends `None` on a real modeling task.** The description is too
  vague — re-describe the temporal/scope/perspectival/capability dimension.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 10/10:
   - each signal class selects the right pattern; irrelevant text recommends None
   - composition flagged when patterns co-occur
   - validator passes well-formed instances and fails missing-temporal-link,
     out-of-range-confidence, and missing-authorization-level instances
2. **Run the scenario.** `python cli.py scenario devops-drift` selects
   event-centric for deployments, multi-perspective for drift, and shows a broken
   event failing validation.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints this SKILL.md
   description (so any harness can discover the skill from --help).

## Security Posture

- **Prompt injection.** The knowledge-shape description is untrusted free text
  tokenized against a fixed signal vocabulary - embedded instructions can at
  most mis-select a pattern. Instance dicts are validated against fixed
  contracts; field values are never executed or interpolated.
- **Data exfiltration.** No network calls, no file writes. Instance payloads
  (forecasts, org data, capability limits) stay in-process and appear only in
  the stdout validation report the caller owns.
- **Privilege escalation.** No shell invocation, no eval, no dynamic import.
  Validating a Capability-Model instance as well-formed does NOT authorize it -
  enforcement is capability-authorization-gate plus the platform's IAM.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien) Ch3 — Knowledge
Representation, section "Schema Design Patterns": Event-Centric (Example 3-3),
Contextual-Boundary (Example 3-4), Multi-Perspective (Example 3-5),
Capability-Model, and the composition Tip. DevOps manifestations
(DeploymentEvent, Terraform-vs-AWS config drift) are from the chapter's
"Applying schema patterns to infrastructure" section (Example 3-14).
