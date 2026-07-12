---
name: information-flow-control-gate
description: |
  A deterministic security-policy layer for chained tools. Does two things:
  (1) discovers tool dependency chains by matching one tool's output TYPE to
  another tool's input TYPE (the NESTFUL failure mode where LLMs miss that
  COVID stats need a country code first); (2) tracks data taint with FIDES-style
  TRUSTED/UNTRUSTED labels that propagate through operations, so a sensitive
  action is blocked when its data is tainted, with opaque-variable references
  keeping raw untrusted content out of the LLM's reasoning. Use when tools chain
  and untrusted data can reach a sensitive action. NOT a replacement for
  authentication (that verifies the caller; this governs the data), NOT for
  single-tool calls with no chaining, NOT a general policy engine (it enforces
  the two IFC mechanisms the chapter names, not arbitrary rules).
osmani-pattern: Reviewer
ghosh-layer: Primitive
chapter-source: "Agentic GraphRAG (O'Reilly) Ch6 — Tool Orchestration"
---

# Information Flow Control Gate

## Overview

Authentication answers "is this agent allowed to call this tool?" It cannot
answer "is this DATA allowed to flow into this action?" When tools chain
together, two new problems appear, and this gate is the deterministic layer that
handles both.

**Type matching (the NESTFUL problem).** The NESTFUL benchmark shows even the
most advanced LLMs achieve only ~41% success on nested API calls when tool
relationships are implicit. They fail to recognize that getting COVID statistics
for a country requires first obtaining the country code; they struggle with type
matching between one API's output and another's input. Modeling `REQUIRES_INPUT`
and `PRODUCES_OUTPUT` types explicitly reduces multi-step reasoning to a graph
traversal: `get_country_details("India") -> "IN"` (type `ISO_3166_1_alpha_2`),
then `get_covid_stats(location="IN")`.

**Taint tracking (FIDES IFC).** Every value carries a trust label from its
provenance. An email from an internal domain is `TRUSTED`; an external one is
`UNTRUSTED`. The taint propagates: mix trusted with untrusted and the result
inherits `UNTRUSTED`. A deterministic policy then blocks sensitive actions on
tainted data. Opaque-variable management hardens this: the LLM sees only an
opaque UUID reference, and must call `read_variable` to materialize content, so
malicious instructions embedded in untrusted content never directly steer the
model's reasoning. This stops two threats authentication cannot: agent tool
misuse (a legitimate tool used for a malicious purpose on tainted data) and
agent goal manipulation (untrusted instructions overriding the objective).

## When to Use

- Tools chain: one tool's output feeds another tool's input
- The agent may ingest external/untrusted content (emails, scraped docs,
  third-party API responses) that could reach a sensitive action
- You want deterministic type-matched execution planning instead of hoping the
  LLM tracks variables between calls
- You need an auditable "why was this action blocked" answer

Phrases that invoke this skill: "tool dependencies", "type matching", "taint
tracking", "information flow control", "block sensitive action on untrusted
data", "opaque variable", "IFC".

## When NOT to Use

- **As authentication.** This governs data flow; it does not verify the caller.
  Pair it with OAuth / per-agent access control (Layer 1).
- **Single-tool calls with no chaining and no untrusted input** — nothing to
  match, nothing to taint.
- **As a general policy engine.** It enforces the two IFC mechanisms the chapter
  names (type-matched dependencies + taint labels), not arbitrary business rules.
- **For multi-hop type resolution beyond one bridge** — `plan_execution`
  resolves single-hop bridges (the chapter's worked cases); the `# TODO
  (production):` seam marks where a full topological sort goes.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Tool specs JSON (each has `requires`/`produces` typed fields) | `lib.load_tool_specs(path)` | List of tool dicts | Each tool has typed `requires` and/or `produces` entries |
| 2 | Tool specs | `lib.match_dependencies(tools)` | Producer→consumer edges where output type == input type | Every edge's `shared_type` appears in producer `produces` AND consumer `requires` |
| 3 | Target tool + available types | `lib.plan_execution(tools, target, have)` | Ordered execution plan bridging missing types | No step marked `UNRESOLVED`; the COVID chain inserts `get_country_details` |
| 4 | A value + its source domain | `lib.label_by_source(value, source, trusted_domains)` | `TaintedValue` with `TRUSTED`/`UNTRUSTED` | Internal-domain source → TRUSTED; external → UNTRUSTED |
| 5 | Multiple tainted inputs | `lib.propagate(inputs)` | Combined label | Any untrusted input yields UNTRUSTED |
| 6 | Action + propagated label | `lib.check_policy(action, label)` | `{allowed, reason}` | Sensitive action on UNTRUSTED data → `allowed=False` |
| 7 | Untrusted content | `OpaqueStore.put(...)` then `read_variable(ref)` | UUID ref; explicit dereference recorded | The LLM-facing value is the UUID, not the content; every read is logged |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|---------------------|
| "The LLM can figure out the country-code dependency itself." | NESTFUL: ~41% success on nested calls when relationships are implicit. Explicit type matching turns a failing reasoning task into a deterministic traversal. |
| "Authentication already secures this — the caller is authorized." | Authentication verifies the caller, not the data. An authorized agent can still be tricked into a sensitive action on untrusted content. IFC is a distinct layer (the chapter's Layer 2). |
| "Just check the final action, not the whole data lineage." | Taint must propagate: a summary mixing internal and external data inherits UNTRUSTED. Checking only the final action misses that a trusted-looking output was contaminated upstream. |
| "Let the LLM read the external content directly — it's just text." | FIDES opaque variables exist precisely because raw untrusted content can carry instructions that hijack reasoning. The LLM gets a UUID; `read_variable` keeps the taint policy in force. |
| "Blocking on untrusted data is too strict — it'll break workflows." | The block applies only to the SENSITIVE action set (send_email, transfer_funds, run_shell, delete, ...). Non-sensitive processing of untrusted data is permitted; the gate is targeted, not blanket. |

## Red Flags

- **A dependency edge whose `shared_type` is not in both `produces` and
  `requires`.** The match is spurious; the type graph is malformed.
- **`plan_execution` returns an `UNRESOLVED` step.** No registered producer emits
  the required type — the chain cannot complete; register the missing tool.
- **A sensitive action ALLOWED on UNTRUSTED data.** The policy gate is bypassed —
  this is the exact failure IFC exists to prevent.
- **Raw untrusted content reaching the LLM prompt instead of a UUID.** Opaque-
  variable management is not wired; the injection surface is open.
- **CLI `--help` exits non-zero.** SKILL.md / CLI mismatch; multi-harness invariant broken.

## Non-Negotiable Verification

1. **Run the benchmark battery.**
   ```
   python cli.py benchmark
   ```
   Confirm: type-matched edges discovered, the COVID chain resolves via a bridge
   producer, and the mixed-provenance `send_email` flow is BLOCKED.

2. **Prove taint propagation.**
   ```
   python cli.py taint --action send_email --input internal.acme.com --input external-sender.net
   ```
   One trusted + one untrusted input MUST propagate to UNTRUSTED and BLOCK.

3. **Prove the sensitive-action gate is targeted, not blanket.**
   ```
   python cli.py check-flows
   ```
   `internal-metrics-readout` (TRUSTED, non-sensitive) is ALLOWED;
   `external-doc-run-shell` (UNTRUSTED, sensitive) is BLOCKED.

4. **Prove opaque-variable indirection.**
   ```
   python cli.py opaque-demo --json | python -c "import json,sys; d=json.load(sys.stdin); assert d['what_the_llm_sees']!=d['after_read_variable']"
   ```
   The LLM-facing value is a UUID, distinct from the materialized content.

## Security Posture

- **Prompt injection.** This gate is a primary defense. Untrusted content is
  labeled and, via `OpaqueStore`, never enters the prompt verbatim — the LLM
  sees a UUID and must explicitly `read_variable`. The `# TODO(production):` seam
  in `label_by_source` marks where to replace substring domain-matching with
  verified sender identity.
- **Data exfiltration.** The sensitive-action set (`SENSITIVE_ACTIONS`) blocks
  send/transfer/external-post on tainted data. Extend the set for your domain;
  do not remove entries to "unblock" a workflow — re-source the data instead.
- **Privilege escalation.** `run_shell` / `execute_code` on UNTRUSTED data is
  blocked by construction. The policy is deterministic (no LLM judgment at the
  decision point), which is what makes it auditable.

## Composition

- **Composes after** authentication / per-agent access control (Layer 1): this
  is the Layer-2 data-flow governor in the chapter's defense-in-depth model.
- **Feeds** the hierarchical orchestrator and the Enterprise AI OS control plane
  (its `ifc_controller.apply_taint_tracking` step is this skill).
- **Pairs with** `draft-tool-trust-verifier` — DRAFT tells you what a tool
  actually does; IFC governs what data may flow into it.
- The type-matched execution plan is consumable by any orchestration layer that
  needs a deterministic call order.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly), Chapter 6 — Tool Orchestration,
sections "Tool Dependencies and Type Matching" and "Securing Data Flow with
Information Flow Control". Named references:

- NESTFUL benchmark — ~41% LLM success on nested API calls without explicit
  tool relationships
- Neo4j "Going Meta" — tools + typed dependencies as graph nodes (Examples
  6-4, 6-5)
- FIDES research — IFC via taint tracking + opaque-variable management;
  TRUSTED/UNTRUSTED labels; blocks agent tool misuse + agent goal manipulation
