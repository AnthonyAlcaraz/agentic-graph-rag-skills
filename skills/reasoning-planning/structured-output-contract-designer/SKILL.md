---
name: structured-output-contract-designer
description: |
  Design the OUTPUT CONTRACT for a graph-agent node's seam, per Ch5
  "Structured Generation: The Keystone of Reliable Communication" (Outlines).
  Most graph-agent failures are internode COMMUNICATION breakdowns, not bad
  reasoning — a node that emits free text is unreliable exactly where its
  output feeds the next node or a graph write. The designer picks an
  enforcement level (FREE_TEXT / JSON_SCHEMA / GRAMMAR_CONSTRAINED), emits a
  minimal contract for common DevOps-investigation node types, and validates a
  payload against that contract deterministically — the primitive that makes a
  seam verifiable. Use when wiring a node's output into
  another node, a graph write, or a tool call and free text would make the
  seam fragile. NOT for choosing WHICH pipeline shape to run (that is pipeline
  selection), NOT for terminal human-facing prose with no downstream parser,
  NOT for picking a model or a graph model class.
osmani-pattern: Primitive
ghosh-layer: Primitive
chapter-source: "Agentic GraphRAG (O'Reilly) Ch5 — Reasoning & Planning — Structured Generation: The Keystone of Reliable Communication (Outlines constrained decoding); cross-chapter pillar with Ch6 grammar-constrained tool output"
references:
  - "Outlines — constrained decoding via a finite-state machine over valid token sequences (Ch5 keystone mechanism)"
  - "Ch5 insurance-claims example — enumerated determination, non-negative amount, pattern-matched code, mandatory appeal-rights language valid by construction"
  - "Ch6 — grammar-constrained structured output for MCP tool calls (the seam's other half)"
---

# Structured Output Contract Designer

## Overview

After the graph architecture is in place, one failure dominates production:
even with perfect reasoning and validated retrieval, the system collapses when
nodes cannot parse each other's outputs. The chapter is blunt — most
graph-agent failures are internode COMMUNICATION breakdowns, not bad reasoning.
A workflow graph is useless when output formats vary unpredictably.

Structured output is the keystone that fixes this. Instead of hoping a node
produces a parseable format, you constrain generation so producing anything
else is impossible. Outlines builds a finite-state machine over the valid token
sequences of your schema/grammar and zeros out any token that would leave the
valid set, so the output is valid **by construction**, not by post-hoc
validation that can be bypassed or fail silently.

The designer chooses an enforcement level per node seam:

- **FREE_TEXT** — terminal, human-facing prose with no downstream parser. A
  schema would only add latency. Admissible only when the reader is human and
  the output is not reliability-critical.
- **JSON_SCHEMA** — the default for any machine seam: node-to-node hand-off, a
  graph write, or a tool call. The next node relies on the shape instead of
  defensively parsing prose.
- **GRAMMAR_CONSTRAINED** — the output must match a formal grammar, draw from a
  closed vocabulary, or land on a specific graph node-type. The grammar makes
  every out-of-vocabulary / off-type sequence physically ungenerable.

It also emits minimal contracts for common DevOps-investigation node types
(hypothesis, remediation, reasoning, validation) and validates a payload
against a contract deterministically — required fields present, types match,
closed vocabularies honored. That validation is the concrete form of the
chapter's claim that structured output makes the seam verifiable. Because
structure compounds with the graph, this same primitive carries into Ch6, where
grammar-constrained decoding makes MCP tool calls syntactically valid too.

## When to Use

- Wiring a node's output into another node, a graph write, or a tool call
- Deciding whether a node's output needs a schema or a grammar, or can stay prose
- Designing the contract for a hypothesis / remediation / reasoning / validation node
- Justifying "this seam is reliable by construction" in a design doc

Phrases: "structured output", "output contract", "constrained decoding",
"Outlines schema", "grammar-constrained", "node output format", "internode
contract", "make this seam parseable".

## When NOT to Use

- **Choosing which pipeline shape to run** (sequential / tree / loop) — that is
  pipeline-architecture selection, a different axis.
- **Terminal human-facing prose.** If the only reader is a human and nothing
  downstream parses it, a schema is latency for no reliability gain.
- **Picking a model or a graph model class.** This designs the output contract
  at a seam, not the model behind it or the store under it.
- **A seam that already has an enforced contract.** If the interface is fixed
  and validated upstream, adopt it.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | A node's seam `NodeProfile` (consumed_by, needs_valid_parse, fixed_vocabulary, reliability_criticality, latency_budget) | `lib.recommend_enforcement(profile)` | `{recommended, rationale, scores}` | machine seams >= JSON_SCHEMA; fixed vocabulary -> GRAMMAR_CONSTRAINED; FREE_TEXT only for non-critical human output |
| 2 | A node-type name | `lib.schema_from_node_type(node_type)` | contract dict `{node_type, required, types, enums}` | required fields + types present; enum'd fields carry a closed vocabulary |
| 3 | A payload + a contract | `lib.validate_against_contract(payload, contract)` | `{valid, violations}` | catches missing field, type mismatch, vocabulary violation; clean payload -> valid |
| 4 | before/after parse rates | `lib.reliability_gain(free, constrained)` | seam delta + failures eliminated / million | 99.9% -> 100% eliminates 1000 failures / million |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "The model almost always returns valid JSON, so a plain prompt is fine." | "Almost always" is the failure. At scale even a 0.1% malformed rate is real exposure (the insurance-claims example). Constrained decoding drives the malformed rate to zero — valid by construction, not by hoping. |
| "I'll validate the output after generation and retry on failure." | Post-hoc validation can be bypassed or fail silently, and retry loops cost latency. Outlines makes the invalid output ungenerable, so every generation succeeds on the first attempt — no retry loop exists to bypass. |
| "This node just talks to a human, give it a schema anyway to be safe." | FREE_TEXT is correct for a terminal human reader with no downstream parser. A schema there is latency for no reliability gain. The level must match the seam: prose for humans, schema/grammar for machines. |
| "A JSON schema is enough for a field that must be one of a fixed set." | A schema can type the field as a string but not forbid an out-of-vocabulary value at the token level. A closed vocabulary / node-type target needs GRAMMAR_CONSTRAINED so the wrong token is never emitted. |
| "Structured output is just formatting, it doesn't affect reasoning." | It is what makes reasoning composable: when each node can rely absolutely on its inputs' shape, it spends capacity on reasoning instead of defensive parsing. The contract carries the reliability of the whole graph, and it carries into Ch6 tool calls. |

## Red Flags

- **A node-to-node or graph-write seam recommended FREE_TEXT.** The profile is
  wrong — a machine seam is not a human terminal reader. Re-check `consumed_by`.
- **GRAMMAR_CONSTRAINED chosen but no closed vocabulary or node-type exists.**
  You are paying grammar cost for a plain structured hand-off; JSON_SCHEMA
  suffices unless a formal grammar is genuinely required.
- **`validate_against_contract` returns valid on a payload missing a required
  field.** The contract's `required` list drifted from the node type — the
  seam is not actually verified.
- **Every node routes to the same enforcement level.** The seam profiles are
  not discriminating; a terminal human summary and a graph-write node should
  not share a level.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 11/11:
   - graph-write / next-node / tool-call seams route to JSON_SCHEMA or stricter
   - a fixed vocabulary / node-type target routes to GRAMMAR_CONSTRAINED
   - FREE_TEXT only for a non-critical human terminal reader; a critical human
     seam is not FREE_TEXT
   - validation catches a missing required field, a type mismatch, and a
     closed-vocabulary violation; a well-formed payload validates clean
   - `reliability_gain` reports the correct seam delta
2. **Run the scenario.** `python cli.py scenario` shows a hypothesis node's
   hand-off: the recommended enforcement, the contract, a passing and a failing
   payload, and the reliability delta from constraining the seam.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints this
   SKILL.md description (so any harness can discover the skill from --help).

## Security Posture

- **Prompt injection.** Seam profiles and payloads are untrusted input handled
  as data - validation is deterministic key/type/enum checking, nothing is
  executed. Note the limit: a contract constrains SHAPE, not content. A
  schema-valid payload can still carry injected text in its string fields;
  contract validation is not sanitization.
- **Data exfiltration.** No network calls, no file writes. Payloads under
  validation stay in-process and appear only in the stdout violations report
  the caller owns.
- **Privilege escalation.** No shell invocation, no eval. Contracts are a
  security boundary: a closed vocabulary bounds what a node can emit into a
  tool call or graph write, so loosening an enum or dropping a required field
  widens the downstream attack surface - treat contract edits as privileged
  changes.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien) Ch5 — Reasoning &
Planning, section "Structured Generation: The Keystone of Reliable
Communication". The constrained-decoding mechanism (a finite-state machine over
valid token sequences that zeros out invalid tokens) is the Outlines library;
the insurance-claims example (enumerated determination, non-negative amount,
pattern-matched explanation code, mandatory appeal-rights language, valid by
construction) is the chapter's real-world impact case. Structured output is a
cross-chapter pillar: Ch5 constrains node output, and Ch6 applies the same
grammar-constrained decoding to MCP tool calls so the seam is reliable on both
sides.
