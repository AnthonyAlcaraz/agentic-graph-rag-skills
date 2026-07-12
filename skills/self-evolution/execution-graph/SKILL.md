---
name: execution-graph
description: |
  Foundational Ch7 primitive: an immutable, queryable graph of every
  decision / retrieval / tool-call / LLM-call an agent made for a specific
  query. Nodes are atomic operations carrying input/output/timestamp/
  latency/cost/tokens; edges are TRIGGERED relationships establishing the
  full causal lineage. Two-phase write — create-on-start (captures structure
  even on failure), fill-on-complete (latency + cost + output). Enables
  diagnostic queries that flat logs cannot answer ("every tool invocation
  that followed an LLM call with confidence < 0.7 and resulted in latency
  > 3s"). Use BEFORE building any Ch7 evaluation or self-evolution
  machinery — it is the substrate everything else depends on. NOT for
  one-shot single-call agents (no graph to trace), NOT for systems where
  observability already lives in OpenTelemetry-to-graph pipeline (you have
  it already).
osmani-pattern: Generator
ghosh-layer: Primitive
chapter-source: "Agentic GraphRAG (O'Reilly) Ch7 — Self-Evolution and Evaluation — The Execution Graph subsection + the chapter's execution-graph example"
references:
  - "OpenTelemetry distributed tracing as the production substrate"
  - "Composes with all Ch7 evaluation layers (0/1/2/3) and Semantic Backpropagation"
---

# Execution Graph

## Overview

The execution graph is the dynamic counterpart to the static workflow
graph (Ch5). The workflow graph is the blueprint; the execution graph is
the autobiography. Each query produces one execution graph instance —
immutable after completion, queryable, the substrate for cognitive
autopsy.

Each node represents one atomic operation:

- **Node ID** — unique per operation instance (span_id from OpenTelemetry
  in production)
- **Node type** — `LLM_Call`, `Tool_Invocation`, `Retrieval`, `Decision_Point`
- **Timestamp** — high-resolution for latency analysis
- **Input payload** — exact data received
- **Output payload** — exact data produced
- **Performance metrics** — latency_ms, token_count, cost_usd
- **Parent-child edges** — `TRIGGERED` relationships establishing causal
  lineage

Two-phase write is the central primitive (the chapter's execution-graph example):

1. **Phase 1 (on-start)**: create node + link to parent. If the operation
   fails or crashes, the graph still captures *what was about to happen*.
2. **Phase 2 (on-complete)**: fill in output + latency + cost.

A simple one-phase write loses the causal structure when nodes fail —
exactly the cases that need diagnosis most.

## When to Use

- BEFORE building any Ch7 evaluation layer (0/1/2/3) — they all query the
  execution graph
- Multi-step agent workflows where you need to attribute a failure to a
  specific node (the chapter quote: "the error isn't lost in a sea of
  model parameters")
- Self-evolution loops — every evolution decision needs the execution
  graph as input
- DevOps incident reconstruction — answer "which node failed and what
  preceded it"

Phrases: "execution graph", "trace the agent's run", "cognitive autopsy",
"causal chain", "which node failed", "self-evolution foundation".

## When NOT to Use

- One-shot single-call agents — no graph to trace; just log the call
- Production systems where you already pipe OpenTelemetry → Neo4j and
  have execution-graph reconstruction working
- High-frequency request paths where the per-node Cypher write latency
  blocks the request — buffer to async writer or sample

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | execution_id (per-query unique) | `lib.ExecutionGraph(execution_id)` | empty graph | graph has zero nodes |
| 2 | node_type + input + parent_id (optional, None for root) | `graph.begin_node(...)` | node_id (graph captures structure even on crash) | node has timestamp, parent edge, no output yet |
| 3 | node_id + output + metrics (latency_ms, token_count, cost_usd) | `graph.complete_node(node_id, ...)` | node updated | node has output + all metric fields populated |
| 4 | Cypher-like query string | `graph.query(predicate_fn)` | list of nodes matching predicate | predicate is callable, returns matching node list |
| 5 | failed node_id | `graph.causal_chain(node_id)` | full ancestor chain from root to node | chain endpoints connect; root has no parent |
| 6 | execution_id | `graph.snapshot()` / `graph.from_snapshot(d)` | serialize / deserialize | round-trip preserves nodes, edges, metrics |
| 7 | graph | `graph.summary()` | counts by type, total latency, total cost, total tokens, failure indicators (nodes without output) | sums match individual node values |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Logs are good enough — I don't need a graph." | The Ch7 chapter quote is explicit: "That kind of query is only possible when execution data lives in a graph database rather than a flat log file." The query "every tool invocation that followed an LLM call with confidence < 0.7 and resulted in latency > 3s" requires graph-traversal semantics. Flat logs cannot answer it. |
| "One-phase write is simpler — just record on complete." | Then a crashed node produces no record, and the causal chain is broken at the point of greatest diagnostic interest. Ch7 the chapter's execution-graph example is explicit about this: "the graph captures the causal structure even if the operation fails." |
| "I'll skip cost / token tracking — those are billing concerns." | Cost and tokens are reasoning-shape signals (Ch7 Reasoning Shape Analysis section). A reasoning trace with high cost and low InfoGain is a "grinding" failure mode that you cannot detect without the cost field. |
| "Parent edges are redundant with timestamps — temporal order is enough." | Temporal order tells you what happened *when*. Parent edges tell you what happened *because of what*. Sibling nodes that ran in parallel (e.g. two retrieval channels) have the same parent but different timestamps. Without the edge, the causal structure is lost. |

## Red Flags

- **Nodes without `parent_id` other than the root.** Causal chain broken;
  caller forgot to thread the span context.
- **Nodes with `output` filled but no `latency_ms`.** One-phase write that
  bypassed the begin-then-complete pattern; metrics are lost.
- **`causal_chain(failed_node)` returns empty.** Either the failed node
  has no parent edge or the chain query is broken. Both block diagnosis.
- **Total cost in `summary()` does not match sum of node costs.** Schema
  drift — some nodes have `cost_usd` and others have `cost`, or stringly-
  typed values. Enforce numeric at lib boundary.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report:
   - two-phase write produces complete node even after simulated crash
     during execution (begin_node persists, complete_node is skipped, the
     incomplete node is queryable)
   - causal_chain traces from any node to root
   - parallel siblings share parent but are distinct nodes
   - query predicate works (filter by type + latency)
2. **Run the DevOps scenario.** `python cli.py scenario incident-trace`
   produces a realistic multi-node execution graph for one incident-
   investigation query, then identifies the failing node.
3. **Verify CLI help.** Exits 0 and prints SKILL.md description.

## Security Posture

- **Prompt injection.** Node payloads capture raw inputs/outputs verbatim,
  including untrusted content the agent processed. The graph never executes
  payloads, but any later LLM pass over the trace (cognitive autopsy,
  semantic backprop) re-reads them - treat trace payloads as data, not
  instructions, in those consumers.
- **Data exfiltration.** The execution graph is a high-value concentration:
  exact inputs/outputs (possibly secrets, PII, credentials in tool args)
  persisted immutably per query. Redact secrets before `begin_node` /
  `complete_node` and access-control the graph store like a log with secrets.
- **Privilege escalation.** No shell invocation, no eval. Post-completion
  immutability is the audit invariant: an agent that can rewrite its own
  trace can launder its history. Restrict writes to the two-phase API and
  deny updates to completed nodes.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien) Ch7 — The
Foundation of Self-Awareness section + the chapter's execution-graph example. Production substrate:
OpenTelemetry distributed tracing → Neo4j graph store.
