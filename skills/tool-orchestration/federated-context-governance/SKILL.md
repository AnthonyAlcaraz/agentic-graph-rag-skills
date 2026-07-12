---
name: federated-context-governance
description: |
  Govern agent-configuration drift once tool orchestration scales from one
  developer to a team. Detects where independently-authored context configs
  (CLAUDE.md-style settings + installed skills) diverge, classifies the
  fragmentation stage, enforces a FEDERATED org base whose nonnegotiable
  settings (security, architectural, compliance) every team must inherit
  unchanged while owning their negotiable extensions, and routes a governance
  need to the right architectural layer (Config-as-Code / Shared Knowledge Layer
  / Governance Control Plane). Use when multiple developers or teams configure
  agents independently and their outputs are diverging. NOT for a single
  developer's setup (there is no drift), NOT a code linter (it governs agent
  CONTEXT, not source code), NOT a secrets manager (it flags a policy key, it
  does not store secrets).
osmani-pattern: Reviewer
ghosh-layer: Orchestration
chapter-source: "Agentic GraphRAG (O'Reilly) Ch6 — Tool Orchestration — Context Governance: The Missing Layer in Tool Orchestration"
---

# Federated Context Governance

## Overview

The tool-orchestration stack (discovery, selection, gateway, execution) assumes a
single coherent context. That assumption breaks when orchestration scales from
one developer to a team. When one developer configures an AI coding agent — a
CLAUDE.md, installed skills, hooks — the result is coherent and personalized.
When five developers do the same thing independently, the result is five
divergent architectures: each agent receives different instructions, applies
different patterns, and produces code shaped by different assumptions.

Marc Baselga documented this after deploying Claude Code across an engineering
team; Ben Erez called it the "unexpected tax." Two developers asking their agents
to "follow our coding standards" receive different standards if their contexts
diverge. The fragmentation follows a predictable progression:

    individual optimization -> silent divergence -> visible inconsistency
    -> coordination overhead

The chapter's three solution architectures are not competing options but LAYERS
of one federated architecture (Table 6-4), mapped to organizational scale:

| Scale | Layer | Tool | Mechanism |
|-------|-------|------|-----------|
| Team | Configuration as Code | APM (Meppiel) | versioned, composable skill/rule/prompt packages; `apm install` gives everyone the same base |
| Department | Shared Knowledge Layer | Nia Skills (Rakhmetzhanov) | a central indexed knowledge base any agent queries |
| Enterprise | Governance Control Plane | Runtime (Jarjoura) | business rules, constraints, ownership, decisions as infrastructure |

The architecture is FEDERATED, not centralized: teams own domain-specific context
but inherit an organizational base encoding nonnegotiable standards (security
policies, architectural constraints, code-review requirements, compliance rules).
Jarjoura's diagnosis is the decisive one: "Context failure, not AI failure."
Agents amplify whatever structure they receive; incomplete or inconsistent
structure produces amplified ambiguity at the speed of token generation.

## When to Use

- Multiple developers or teams configure agents independently
- Code reviews reveal conflicting patterns produced by different agents
- Onboarding is hard because no single config represents team practice
- You need to enforce nonnegotiable standards (security/compliance) across teams
  while letting teams keep their domain-specific extensions

Phrases that invoke this skill: "config drift", "our agents diverge", "context
governance", "federated config", "enforce the org base", "which governance
layer".

## When NOT to Use

- **A single developer's setup** — one config is coherent by definition; there is
  no drift to detect.
- **As a code linter** — it governs agent CONTEXT (settings, skills, rules), not
  source code. Lint code with a code linter.
- **As a secrets manager** — `secrets_in_env_only` is a policy KEY it enforces;
  it does not store or rotate secrets.
- **Where teams legitimately need different nonnegotiables** — then the setting is
  not actually nonnegotiable; move it to the negotiable set rather than forcing
  false uniformity.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Governance JSON (org_base + team_configs) | `lib.load_governance(path)` | Governance dict | Has `org_base` (with `nonnegotiable`) and `team_configs` |
| 2 | Team configs | `lib.detect_drift(configs)` | Settings that disagree + partial skills | A key with differing values across ≥2 teams is reported |
| 3 | Team configs | `lib.fragmentation_stage(configs)` | Stage on the four-stage progression | More drift → later stage (coordination overhead) |
| 4 | Org base + team configs | `lib.check_federation(org_base, teams)` | Per-team compliance + violations | A team overriding a nonnegotiable key is flagged non-compliant |
| 5 | Org base + one team | `lib.resolve_effective_config(org_base, team)` | Effective config with nonnegotiable keys locked to base | A team's override of a locked key is ignored; base value wins |
| 6 | Scale (team/department/enterprise) | `lib.recommend_layer(scale)` | The matching layer + tool + composition | Larger scales inherit the smaller layers beneath |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|---------------------|
| "Each developer's config working for them is fine." | It is fine individually and incoherent at the team level. Two agents given "follow our standards" produce different standards — the exact drift the chapter names. Individual coherence is not team coherence. |
| "Centralize all config in one file everyone shares." | The architecture is FEDERATED, not centralized. Teams own domain-specific context; forcing one file loses the backend/frontend/data specialization that made per-team config valuable. Inherit the base, extend locally. |
| "A team can override any setting it needs to." | Not the nonnegotiable ones. Security, architectural, and compliance keys are locked to the org base; a team disabling code review is a violation, not a preference. `resolve_effective_config` locks them by construction. |
| "Config drift is a people problem, not infrastructure." | Jarjoura: "Context failure, not AI failure." Agent config is shared infrastructure requiring versioning, testing, deployment, and monitoring — the same engineering discipline as any other shared infra. |
| "Pick one governance tool and use it everywhere." | The three layers map to scale and COMPOSE: Config-as-Code (team) inside Shared Knowledge (department) inside a Governance Control Plane (enterprise). One tool cannot span all three scales. |

## Red Flags

- **Zero drift reported across many independently-authored configs.** Either the
  configs are already governed (good) or the drift detector is not comparing the
  right setting keys.
- **A nonnegotiable violation reported as compliant.** The federation check is
  bypassed — a locked key must fail closed.
- **`resolve_effective_config` lets a team override a locked key.** The lock is
  inert; nonnegotiable keys must always resolve to the base value.
- **Fragmentation stuck at "individual optimization" despite obvious divergence.**
  The stage thresholds are miscalibrated for the number of configs.
- **CLI `--help` exits non-zero.** SKILL.md / CLI mismatch; multi-harness invariant broken.

## Non-Negotiable Verification

1. **Run the benchmark battery.**
   ```
   python cli.py benchmark
   ```
   Confirm drift is detected across teams, the fragmentation stage reflects it,
   and the seeded `rogue-frontend` nonnegotiable violation (disabling
   `code_review_required`) is caught.

2. **Prove the lock holds in the effective config.**
   ```
   python cli.py effective rogue-frontend
   ```
   `code_review_required` MUST resolve to `True` (the base value) even though the
   team set it `False`.

3. **Prove federation fails closed on the nonnegotiable.**
   ```
   python cli.py federate --json | python -c "import json,sys; d=json.load(sys.stdin); assert not d['all_compliant']"
   ```

4. **Prove layer composition.**
   ```
   python cli.py layer enterprise
   ```
   Enterprise scale must inherit `[team, department, enterprise]`.

## Security Posture

- **Prompt injection.** Context configs are the agent's instructions; a
  compromised config is a direct injection vector. The nonnegotiable base is the
  defense — security-relevant keys (`secrets_in_env_only`, `code_review_required`)
  are locked and a team cannot silently disable them.
- **Data exfiltration.** No network calls in `lib.py`; governance is read from an
  explicit path. In production the org base is itself a versioned, reviewed
  artifact (the chapter's "agent config is shared infrastructure" point).
- **Privilege escalation.** `resolve_effective_config` locking nonnegotiable keys
  to the base is exactly the anti-escalation control — a team cannot grant itself
  a laxer security posture than the org mandates.

## Composition

- **Wraps** the whole tool-orchestration stack: `rag-mcp-tool-selection`,
  `mcp-gateway-two-meta-tools`, `hierarchical-orchestration-router` all assume a
  coherent context — this skill is the layer that keeps it coherent at team scale.
- **Pairs with** `hierarchical-orchestration-router` — hierarchical routing needs
  a coherent per-domain context to route into; this governs that context.
- **The nonnegotiable base** is the natural home for the security policies from
  `information-flow-control-gate` and the quality thresholds from
  `skill-quality-evaluator`.
- Mirrors an org-baseline-plus-local-extensions config-sync discipline: an
  org base every machine inherits, with local extensions composed on top.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly), Chapter 6 — Tool Orchestration,
section "Context Governance: The Missing Layer in Tool Orchestration". Named
references:

- Marc Baselga — documented config drift after team Claude Code deployment;
  Ben Erez — the "unexpected tax"
- Daniel Meppiel — APM (Agent Package Manager), Configuration as Code (team scale)
- Arlan Rakhmetzhanov — Nia Skills, Shared Knowledge Layer (department scale)
- Daniel Jarjoura — Runtime, Governance Control Plane (enterprise scale);
  "Context failure, not AI failure"
