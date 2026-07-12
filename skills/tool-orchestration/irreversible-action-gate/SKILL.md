---
name: irreversible-action-gate
description: |
  Gate agent tool calls by reversibility BEFORE execution: classify each
  action REVERSIBLE / SEMI_REVERSIBLE / IRREVERSIBLE from its declared
  properties (side-effect scope, idempotency, destructiveness, compensating
  action), prescribe the matching delivery contract (idempotency key, retry
  policy, dry-run-first, human approval, compensation registration), check
  deterministic preconditions against graph facts, and analyze multi-step
  plans as sagas with an explicit point of no return. Use whenever an agent
  executes tools with side effects — anything beyond pure reads. NOT for
  read-only pipelines (nothing to gate), NOT a transaction manager (it
  prescribes the contract; your executor enforces it), NOT a substitute for
  the Ch6 information-flow or trust gates (those govern data and tool
  quality; this governs consequence).
osmani-pattern: Inversion
ghosh-layer: Primitive
chapter-source: "Agentic GraphRAG (O'Reilly) Ch6 — Tool Orchestration — the execution boundary; composes Ch5 'Action irreversibility' + structured plans with explicit rollback procedures, Ch3 SHACL precondition gates (RollbackDeployment :rollbackApproved), Ch4 escalate-to-strong before irreversible decisions, Ch7 reversibility hierarchy"
references:
  - "Ch5 — Risks: action irreversibility; Outlines-constrained plans with preconditions, expected outcomes, and rollback procedures"
  - "Ch3 — SHACL precondition validation before tool invocation"
  - "Ch4 — consistency escalation for decision points that trigger irreversible actions"
  - "Ch7 — reversibility hierarchy (prompt < weights < code) and rollback-path requirement"
  - "Saga pattern (Garcia-Molina & Salem, 1987) — compensation-based recovery for long-lived transactions"
---

# Irreversible-Action Gate

## Overview

An agent that can call tools can cause consequences, and consequences are not
uniform: re-reading a metric is free, scaling a service down is undoable,
deleting a snapshot or paging a human is not. Most agent failures that make
postmortems are not wrong answers — they are wrong actions that could not be
taken back, retried into duplication, or executed before their preconditions
held.

This skill is the deterministic gate at the execution boundary. It does four
things, all before any tool runs: classifies the action's reversibility,
prescribes the delivery contract that class demands, checks the action's
preconditions against known graph facts (fail-closed), and — for multi-step
plans — computes the compensation stack and the **point of no return**: the
first irreversible step, before which recovery is backward (undo what was
done) and after which recovery is forward only (finish what was started).

The classification is property-driven, not name-driven: an action is what its
declared side-effect scope, idempotency, destructiveness, and compensation
say it is. "The tool is called `cleanup`" carries no information; "the tool
is data-destructive, external, and has no compensating action" does.

## When to Use

- Any agent whose tools mutate state: deployments, configuration changes,
  scaling, deletions, notifications, payments, ticket creation.
- Before executing a multi-step remediation plan — the saga analysis tells
  you where the point of no return sits and whether reversible steps are
  needlessly ordered after it.
- When designing a tool registry: run every tool through `classify` once and
  store the class as a tool property the orchestrator can filter on.
- When an executor needs a retry policy and nobody has written one: the
  prescription (at-most-once vs at-least-once-with-key vs safe-retry) is
  derivable from the action's properties.

## When NOT to Use

- Read-only pipelines: every action classifies REVERSIBLE and the gate adds
  a no-op. Skip it.
- As a transaction manager: this skill prescribes the contract (register
  compensation first, require the key, dry-run first); enforcing it is the
  executor's job. The gate cannot roll anything back itself.
- As a replacement for the other Ch6 gates: `information-flow-control-gate`
  governs what data may flow between tools; `draft-tool-trust-verifier`
  governs whether a tool does what it claims. This skill governs what
  happens if the tool DOES what it claims and you wish it hadn't.
- For human-approval workflow design: the gate says WHEN approval is
  required (irreversible without dry-run); how approval is collected is out
  of scope.

## Process

| Step | What happens | CLI |
|------|--------------|-----|
| 1 | Classify reversibility from declared properties | `classify --action-spec action.json` |
| 2 | Prescribe the delivery contract (key, retry, dry-run, approval, compensation, consistency) | `prescribe --action-spec action.json` |
| 3 | Check preconditions against graph facts, fail-closed | `gate --action-spec action.json --facts facts.json` |
| 4 | Analyze a multi-step plan: compensation stack + point of no return + reorder flags | `saga --plan-spec plan.json` |
| 5 | Walk the checkout-service remediation end-to-end | `scenario devops-remediation` |
| 6 | Run the verification battery | `benchmark` |

## Rationalizations (and why they fail)

| Rationalization | Why it fails |
|-----------------|--------------|
| "The model is careful; it won't call the destructive tool wrongly." | Care is a probability; the gate is a contract. The classification runs in microseconds and does not have good days and bad days. |
| "We can always retry on timeout." | A timeout on a non-idempotent mutation is not a failure receipt — the action may have succeeded. Retrying without an idempotency key is how one deployment becomes two. That is why the prescription forces at-most-once or a key, never blind retry. |
| "We'll add rollback handling later if we need it." | After the point of no return there is no later. The saga analysis exists precisely because compensation must be registered BEFORE the step executes, not designed during the incident. |
| "Everything in our system is reversible; we have backups." | Backups make internal destruction semi-reversible. They do nothing for external effects: pages sent, customers emailed, money moved. Scope is part of the classification for exactly this reason. |
| "Preconditions slow the agent down." | The gate is one dict lookup per precondition. The Ch3 SHACL discipline it mirrors runs in milliseconds. The slow version is executing RollbackDeployment against a target that never carried :rollbackApproved. |

## Red Flags

- An action classified IRREVERSIBLE executing without dry-run or human
  approval — the prescription was ignored, not wrong.
- A non-idempotent mutation with `retry_policy` anything other than
  at-most-once or at-least-once-with-idempotency-key.
- A saga whose compensation stack is empty while it contains SEMI_REVERSIBLE
  steps — compensations declared but not registered.
- Reversible steps ordered after the point of no return without a stated
  reason — the reorder flags exist to be read.
- A tool registry where every action classifies REVERSIBLE — almost
  certainly under-declared properties, not a genuinely harmless toolset.

## Non-Negotiable Verification

1. `python cli.py benchmark` exits 0 — the battery covers all three classes,
   the retry-policy matrix, fail-closed gating, PONR placement, and the
   reorder flag.
2. `python cli.py --help` exits 0 and prints this skill's frontmatter
   description (so any harness can discover the skill from --help).
3. For your own tool registry: run `classify` on every tool and have a human
   confirm the class of anything marked REVERSIBLE — under-declared
   properties are the failure mode the battery cannot catch for you.

## Security Posture

- Prompt injection: action properties come from the tool registry, not from
  retrieved text. If an attacker can edit the registry to mark a destructive
  tool `idempotent: true, side_effect_scope: none`, the gate is defeated —
  registry entries are privileged configuration and must be write-protected.
- Data exfiltration: the gate itself reads only declared properties and
  boolean facts; it never sees payloads. Keep it that way — a gate that logs
  full tool arguments becomes a sensitive-data sink.
- Privilege escalation: fail-closed is the invariant. A precondition absent
  from the facts dict blocks execution; treat any "default allow on missing
  fact" patch as a vulnerability, not a convenience.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam
Julien), Chapter 6 — Tool Orchestration, composing the execution-boundary
discipline the book states across chapters: Ch5's "action irreversibility"
risk and Outlines-constrained plans with explicit rollback procedures, Ch3's
SHACL precondition gates before tool invocation, Ch4's consistency escalation
before irreversible decision points, and Ch7's reversibility hierarchy.
External anchor: the saga pattern (Garcia-Molina & Salem, SIGMOD 1987) for
compensation-based recovery.
