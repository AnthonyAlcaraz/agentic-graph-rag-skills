---
name: dual-graph-router
description: |
  Route an incoming request to the VERTICAL knowledge graph (what the agent
  knows — a single relationship/temporal traversal), the HORIZONTAL workflow
  graph (how the agent acts — a decomposed multi-step process), BOTH (a workflow
  whose nodes query the knowledge graph and write results back), or UNROUTABLE
  (neither fits — ask for clarification). Implements the central dual-graph
  distinction of Agentic Graph RAG Ch2 and the "Where the Two Graphs Meet"
  bidirectional interaction. Use when an agent receives an on-call request and
  must decide whether it is a knowledge lookup or a process. NOT for building the
  workflow DAG itself (that is harness-node-splitter / investigation-dag-planner),
  NOT for choosing a graph data model (that is graph-model-selector), NOT for
  requests where the structure is already fixed by a hardcoded pipeline.
osmani-pattern: Inversion
ghosh-layer: Orchestration
chapter-source: "Agentic Graph RAG (O'Reilly) Ch2 — Architecture Foundations — The Dual-Graph Architecture + Where the Two Graphs Meet"
references:
  - "Ch2 'The Dual-Graph Architecture' — vertical knowledge graph (the map, what the agent knows) vs horizontal workflow graph (the route, how the agent acts)"
  - "Ch2 'The Vertical Knowledge Graph' — nodes/edges/properties; DEPENDS_ON traversal; temporal `since` metadata; point-in-time queries (Example 2-1, Example 2-2)"
  - "Ch2 'The Horizontal Workflow Graph' — reasoning / execution / decision / validation nodes; the DAG (Example 2-3)"
  - "Ch2 'Where the Two Graphs Meet' — the workflow graph drives the process, the knowledge graph supplies and receives the facts; the value emerges at the intersection"
---

# Dual-Graph Router

## Overview

The dual-graph architecture is the central framework of the book. An agentic
system needs two complementary structures: a representation of what it KNOWS
(the vertical knowledge graph — entities, relationships, constraints) and a
representation of how it ACTS (the horizontal workflow graph — reasoning,
execution, decision, and validation nodes with explicit dependencies). "The
vertical graph is the map. The horizontal graph is the route."

This skill routes a request to the right structure before any work begins:

- **vertical** — a knowledge question answerable by one traversal. "Which
  services depend on payments-db and were deployed in the last 24 hours?" is a
  single `MATCH` over `DEPENDS_ON` edges with a temporal filter (Example 2-1),
  not a workflow.
- **horizontal** — a process the agent must carry out. "Classify the alert,
  plan remediation, decide whether to roll back" decomposes into focused nodes.
- **both** — the load-bearing case from "Where the Two Graphs Meet." "Diagnose
  why checkout is slow and correlate the evidence" is a horizontal workflow
  whose reasoning/retrieval nodes traverse the vertical graph for the dependency
  chain, then write the result back (a new `CAUSED_BY` edge). The architecture's
  value emerges at this intersection.
- **unroutable** — no signal for either graph; ask rather than guess (the
  chapter's ambiguous-situation discipline).

## When to Use

- An agent receives an on-call request and must decide: lookup or process?
- You are wiring the top of a harness and need a deterministic first-hop router
- Auditing a set of historical requests to see how the workload splits across
  the two graphs

Phrases that should invoke this skill: "route this request", "is this a lookup
or an action", "vertical or horizontal graph", "which graph handles this",
"where the two graphs meet".

## When NOT to Use

- **Building the workflow DAG.** Once a request routes to `horizontal`/`both`,
  decomposition into constrained nodes is `harness-node-splitter`; scheduling
  the nodes into parallel phases is `investigation-dag-planner` (Ch5).
- **Choosing a graph data model.** Property graph vs RDF vs hypergraph is
  `graph-model-selector` (Ch3), a different decision.
- **Fixed pipelines.** If the request always runs the same hardcoded steps,
  there is nothing to route.
- **Retrieving the actual facts.** This picks the STRUCTURE; it does not run the
  traversal or execute the workflow.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | request string | `lib.route(request)` | `RouteDecision` (target, scores, matched signals, rationale, node_hint) | target in {vertical, horizontal, both, unroutable}; scores are non-negative ints |
| 2 | a `both` decision | `lib.explain_meeting_point(decision)` | dict of workflow_role / knowledge_role / forward_flow / backward_flow | non-empty only when target == `both`; empty otherwise |
| 3 | list of requests | `lib.route_batch(requests)` | list of `RouteDecision` | one decision per request; order preserved |
| 4 | routed target | (your harness) builds the vertical traversal, the horizontal DAG, or both | structure ready to execute | `both` builds a workflow whose retrieval node queries the vertical graph |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Everything is a workflow — just always build a horizontal graph." | A single relationship/temporal lookup ("which services depend on payments-db") is one traversal. Wrapping it in a workflow adds nodes, latency, and failure surface for a question the vertical graph answers directly (Example 2-1). |
| "Everything is knowledge — just query the graph." | "A knowledge graph alone does not tell the agent how to use that knowledge." A diagnosis is a process: classify, retrieve, correlate, report. That is the horizontal graph's job. |
| "The `both` case is just horizontal — the KG query is only a detail." | The chapter names the intersection as where the architecture earns its keep. Collapsing `both` into `horizontal` loses the bidirectional contract: the workflow drives, the knowledge graph supplies AND receives (the `CAUSED_BY` write-back). Model it as `both`. |
| "If unsure, pick the more powerful option (horizontal)." | An unroutable request is ambiguous by construction. Guessing horizontal builds a workflow with no defined goal. The chapter's discipline is to resolve ambiguity by asking, not by defaulting. |
| "Keyword scoring is too crude for real routing." | Correct for production — swap `_score` for an LLM/intent classifier at the documented seam. The routing CONTRACT (vertical/horizontal/both/unroutable + rationale) is stable; the spike validates the contract, not the classifier. |

## Red Flags

- **Every request routes to `horizontal`.** The vertical-signal set is not
  matching real lookups — you are wrapping single traversals in workflows.
- **Every request routes to `both`.** The signal sets overlap too much, or the
  requests genuinely always mix — verify against a labeled sample before trusting.
- **`unroutable` on a clearly-actionable request.** The horizontal-signal set is
  too narrow for your domain vocabulary; extend it (or swap to a classifier).
- **A `both` decision with an empty meeting-point explanation.** The
  `explain_meeting_point` contract is broken; the bidirectional interaction is
  the whole point of `both`.
- **CLI `--help` exits non-zero.** SKILL.md / CLI mismatch; the multi-harness
  invariant is broken.

## Non-Negotiable Verification

1. **Run the benchmark battery.**
   ```
   python cli.py benchmark
   ```
   All labeled sample requests must route to their expected target, and the
   four invariant checks (mixed→both, both→meeting-point, non-both→no
   meeting-point, empty→unroutable) must pass.

2. **Inspect a `both` route visually.**
   ```
   python cli.py route "diagnose why checkout depends on payments-db and is slow"
   ```
   Confirm the target is BOTH and the printed meeting-point names both the
   forward (workflow→knowledge query) and backward (knowledge←workflow write)
   flows.

3. **JSON output round-trips.**
   ```
   python cli.py route "list services that use stripe-python" --json | python -c "import json,sys; json.load(sys.stdin)"
   ```
   No exception means the CLI is harness-portable.

4. **Batch the labeled sample.**
   ```
   python cli.py batch
   ```
   Confirm the `ok` column is all `ok` — every labeled request matches its route.

## Security Posture

- **Prompt injection.** The request string is untrusted input. This skill only
  tokenizes it against a fixed signal vocabulary and returns a routing label; it
  never executes the request, calls a tool, or interpolates the string into a
  shell/graph query. A malicious request can at most mis-route itself.
- **Data exfiltration.** No network calls, no file writes outside the bundled
  `sample-requests.json` (read-only). The `--json` output goes to stdout; the
  caller owns downstream piping.
- **Privilege escalation.** No shell invocation, no eval, no dynamic import.
  The route label carries no capability — the harness that consumes it is
  responsible for authorizing the actual traversal or workflow (see
  `capability-authorization-gate`, Ch3).

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, AnthonyAlcaraz / forthcoming),
Chapter 2 — Agentic Graph Architecture Foundations:

- "The Dual-Graph Architecture" — vertical knowledge graph vs horizontal
  workflow graph; "the vertical graph is the map, the horizontal graph is the
  route."
- "The Vertical Knowledge Graph" — nodes/edges/properties, `DEPENDS_ON`
  traversal, temporal `since` metadata (Example 2-1, Example 2-2).
- "The Horizontal Workflow Graph" — reasoning/execution/decision/validation
  nodes (Example 2-3).
- "Where the Two Graphs Meet" — the workflow drives, the knowledge graph
  supplies and receives; the value emerges at the intersection.

This is the Inversion-pattern router at the top of the dual-graph harness:
downstream skills (`harness-node-splitter`, `investigation-dag-planner`) build
the structures it routes to.
