---
name: capability-authorization-gate
description: |
  Runtime authorization gate built on the Ch3 Capability Model Pattern — a
  self-aware agent represents its own capabilities, required resources/grants,
  authorization level, and quantitative limits as queryable structure, then
  checks at PLANNING time whether it may perform an action BEFORE attempting it.
  Returns one of three decisions: allow (capability declared, auth level met,
  resources present, within limit), escalate (the agent itself cannot but a
  higher authority could — auth too low, missing grant, or amount over limit —
  route appropriately), or deny (the capability is undeclared; the agent has no
  such ability). The canonical case: a support agent with a $500 refund limit
  receiving a $600 request recognizes it exceeds authority and escalates instead
  of attempting a prohibited action. DevOps manifestation: agent tool-use
  capabilities (read_metrics / query_logs / restart_instance / scale) as
  queryable authority nodes (the model gating tool orchestration in Ch6). Use
  when an agent must decide can-I-do-this before acting, when modeling agent
  operational boundaries, or when building the queryable authority layer for
  tool use. NOT for human RBAC/IAM policy enforcement (use the platform's IAM),
  NOT for validating that a capability NODE is well-formed (use schema-pattern-
  selector's capability_model validation), NOT a replacement for actual
  credential checks at the API boundary (this is the planning-time gate).
osmani-pattern: Reviewer
ghosh-layer: Workflow
chapter-source: "Agentic Graph RAG (O'Reilly) Ch3 — Knowledge Representation — Capability Model Pattern (Example 3-5)"
references:
  - "Ch3 Capability Model Pattern (Example 3-5: Customer-Support-Agent, $500 refund limit -> escalate $600)"
  - "Ch3 DevOps 'Applying schema patterns to infrastructure' — capability model as queryable authority for tool orchestration (Ch6)"
---

# Capability Authorization Gate

## Overview

Self-aware agents must understand their own capabilities and limitations. The
Capability Model Pattern (Ch3, Example 3-5) makes operational parameters
explicit, queryable structure: each capability declares what it `requires`, an
`authorization-level`, and an optional quantitative `limit`. During planning the
agent determines whether it has the access, authorization, and headroom to
fulfill a request **before attempting it** — and routes/escalates when it does
not.

The chapter's worked example: a `Customer-Support-Agent` can
`Answer-Product-Question` (Public, needs only Product-Knowledge) but
`Process-Refund` requires Supervisor authorization, Financial-System-Access, and
caps at 500 USD. A 600-USD refund must be recognized as exceeding authority and
routed appropriately — "creating more reliable, trustworthy automation with
appropriate human oversight" — instead of attempting a prohibited action.

The gate returns three decisions:

- **allow** — capability declared, granted auth level >= required, all required
  resources present, amount (if any) within limit.
- **escalate** — the agent itself cannot, but a higher authority could:
  authorization too low, a required grant missing, or the amount over the limit.
  This is the "route appropriately" path.
- **deny** — the capability is undeclared. The agent has no such ability at all.

The DevOps manifestation (anchored in fictional AWS account `123456789012`):
capabilities like `read_metrics` (Public), `query_logs` (User),
`restart_instance` (Supervisor + `ec2:write`), and `scale_autoscaling_group`
(Supervisor, limit 10 instances) become the queryable authority model that gates
tool orchestration in Ch6. A User-level latency investigator can read metrics
and logs but escalates a restart or an over-limit scale.

## When to Use

- An agent must decide "can I do this?" before invoking a tool or taking an action
- Modeling agent operational boundaries (authority, required grants, limits)
- Building the queryable authority layer that gates tool orchestration (Ch6)
- Implementing graceful escalation/routing instead of attempting prohibited actions

Phrases: "capability model", "can the agent do X", "authorization level",
"operational limit", "escalate", "refund limit", "agent authority",
"queryable authority", "tool authorization gate".

## When NOT to Use

- **Human RBAC/IAM enforcement.** This is the agent's planning-time self-check,
  not your platform's identity policy. Real credential checks still happen at the
  API boundary.
- **Validating the capability NODE shape.** Use `schema-pattern-selector`
  (`capability_model` validation) to confirm a capability declaration is
  well-formed; this skill consumes well-formed declarations and decides.
- **As the only security control.** The gate prevents the agent from ATTEMPTING
  an over-authority action; it does not replace server-side authorization. Defense
  in depth: gate at planning AND enforce at the boundary.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | agent spec JSON (id, granted_level, granted_resources, capabilities[]) | `lib.agent_from_spec(spec)` | `Agent` with `Capability` map | unknown auth level raises at construction |
| 2 | agent + capability type + optional amount | `lib.authorize(agent, cap, amount)` | `{decision, capability, reasons, required_level, granted_level}` | allow only if level met, resources present, within limit |
| 3 | over-limit amount | `lib.authorize(agent, "Process-Refund", 600)` | `decision == "escalate"`, reason cites limit | $600 vs $500 limit escalates, never allows |
| 4 | undeclared capability | `lib.authorize(agent, "X")` | `decision == "deny"` | deny is distinct from escalate |
| 5 | agent + capability + amount | `lib.can_do(agent, cap, amount)` | bool | True only when decision is allow |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "I'll just try the refund and let it fail downstream if it's too big." | Attempting a prohibited action is the failure mode the pattern exists to prevent. The chapter: recognize $600 exceeds the $500 limit and route it — do not attempt. Trying-and-failing leaks intent, may partially execute, and erodes the trustworthy-automation guarantee. |
| "Escalate and deny are the same — both mean 'no'." | They are different and the difference is actionable. Deny = the agent has no such capability at all (dead end). Escalate = a higher authority CAN do it (route to a supervisor / human). Collapsing them loses the routing decision the pattern enables. |
| "The agent is Supervisor now, so any refund amount is fine." | Authorization level and quantitative limit are independent checks. Even a Supervisor escalates a $600 refund if the capability's limit is $500. Raising the actor's level does not raise the capability's limit. |
| "Required resources are implicit — skip the grants check." | The chapter ties capabilities to concrete requirements (Financial-System-Access; in DevOps, `ec2:write`). A capability the agent is authorized for but lacks the resource grant for must still escalate. Skipping the grant check produces a confident "allow" the downstream API will reject. |
| "This duplicates IAM, just rely on AWS IAM." | This is the planning-time self-check that lets the agent decide BEFORE making the call (and route gracefully). IAM enforces at the boundary. They compose — defense in depth — they do not substitute. |

## Red Flags

- **Gate returns `allow` for an action the downstream API then rejects.** The
  agent's granted_resources/level are out of sync with reality — refresh the
  capability model from the actual authority source.
- **Everything escalates.** The agent's granted_level/resources are
  under-provisioned, or the capability declarations over-require. Re-check the
  spec; constant escalation defeats automation.
- **A capability has a limit but callers never pass an amount.** The gate warns;
  an unchecked limit is a silent over-authority risk. Always pass the amount for
  limited capabilities.
- **`deny` for a capability the agent clearly should have.** The capability is
  missing from the declaration — add it, do not work around the gate.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 10/10:
   - Public capability with resources -> allow
   - $600 refund over $500 limit -> escalate (reason cites the limit)
   - undeclared capability -> deny (distinct from escalate)
   - Supervisor + resources allows $400 but still escalates $600
   - DevOps: User escalates restart_instance and over-limit scale, allows read_metrics
   - unknown authorization level raises at construction
2. **Run the scenarios.** `python cli.py scenario support-refund` and
   `python cli.py scenario devops-latency` print allow/escalate/deny across the
   chapter's cases (DevOps anchored in AWS account 123456789012).
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints this SKILL.md
   description (CLAUDE.md CLI mandate).

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, forthcoming) Ch3 — Knowledge
Representation, section "Capability Model Pattern" (Example 3-5: the
Customer-Support-Agent with a $500 refund limit that escalates a $600 request).
The DevOps capability-as-queryable-authority manifestation is from "Applying
schema patterns to infrastructure", feeding the tool-orchestration authority
model in Ch6.
