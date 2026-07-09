---
name: harness-node-splitter
description: |
  Split a workflow description into constrained harness nodes using the chapter's
  rule "nodes differ by tool surface, not by prompt." Given candidate operations
  each with a declared tool set, merge the ones whose tool surfaces overlap >= 80%
  (prompt variations of one role) and split the ones with distinct tool surfaces
  (different roles), then emit the per-node constrained context scope the harness
  enforces (tool surface + memory reads/writes + input/output contract). Implements
  the RedAI scanner-vs-validator distinction and the 80%-overlap Tip from Agentic
  Graph RAG Ch2. Use when turning a horizontal-workflow sketch into executable
  nodes. NOT for scheduling nodes into parallel phases (that is
  investigation-dag-planner, Ch5), NOT for deciding vertical-vs-horizontal
  (that is dual-graph-router), NOT for selecting which tools a query needs
  (that is rag-mcp-tool-selection, Ch6).
osmani-pattern: Generator
ghosh-layer: Orchestration
chapter-source: "Agentic Graph RAG (O'Reilly) Ch2 — Architecture Foundations — Defining the harness + Splitting a workflow into nodes"
references:
  - "Ch2 'The Horizontal Workflow Graph' — reasoning / execution / decision / validation nodes; each node has a focused responsibility (Example 2-3)"
  - "Ch2 'Defining the harness' — the six harness surfaces: workflow-state, advancement policy, typed tool registry, typed memory interface, schema validator, append-only observation record"
  - "Ch2 'Splitting a workflow into nodes' — 'nodes differ by tool surface, not by prompt'; RedAI scanner (filesystem) vs validator (browser/ios/network/scripting); the 80%-tool-overlap Tip"
---

# Harness Node Splitter

## Overview

The horizontal workflow graph says what the agent should do; the harness
executes it. Before the harness can run anything, the workflow must be split
into nodes with focused responsibilities. The chapter gives one rule that cuts
through the design space:

> Nodes differ by tool surface, not by prompt.

The sharpest example is security tooling. Kyle Polley's RedAI splits vulnerability
discovery across two roles whose distinction is entirely tool-level. The
**scanner** node holds a filesystem and threat-models source code (optimized for
recall). The **validator** node holds a browser driver, an iOS simulator, a
network stack, and a scripting runtime, and drives each candidate into a live
environment. Swap the prompts and nothing changes — the validator can still
drive the browser because it holds the tool. The role lives in the tool surface.

The chapter's Tip operationalizes this:

> Before you add a node, list the tools it will call. If the list overlaps more
> than 80% with an existing node, you have a prompt variation of that node —
> merge them and vary the prompt. If the tool lists differ substantially, split.

This skill applies that rule to candidate operations and emits each node's
**constrained context scope** — the tool surface it may invoke, the memory
slices it reads/writes, and the input/output contract the schema validator holds
it to (three of the harness's six surfaces). A tool-less reasoning node (like
Example 2-3's `classify` vs `analyze`) is distinguished by prompt and DAG
position, not tools, so tool-less nodes default to split.

## When to Use

- Turning a horizontal-workflow sketch into executable nodes
- Auditing an existing workflow for the common failure mode: one
  retrieval-and-reasoning node that both queries the graph and does causal
  analysis, with neither pass at specialist quality
- Deciding whether a proposed new node is a real role or a prompt variation of
  an existing one (the Tip as a pre-add gate)

Phrases that should invoke this skill: "split this workflow into nodes", "should
this be one node or two", "nodes differ by tool surface", "merge or split these
nodes", "the 80% tool-overlap rule", "constrain the node's context".

## When NOT to Use

- **Scheduling nodes into parallel phases.** Once nodes exist, ordering them
  into topological phases with parallelism is `investigation-dag-planner` (Ch5).
- **Deciding vertical vs horizontal.** That first-hop routing is
  `dual-graph-router`; this skill runs after a request has routed to
  horizontal/both.
- **Selecting which tools a query needs.** Filtering a large tool registry for a
  query is `rag-mcp-tool-selection` (Ch6). This skill assumes each operation's
  tool set is already declared.
- **Writing the node prompts.** This decides the node BOUNDARIES; the prompt
  content per node is a separate step.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | operation rows (id, node_type, tools, reads, writes, contracts) | `lib.operations_from_dicts(rows)` | list of `Operation` | each op has a tool list (possibly empty) and a node_type |
| 2 | two tool sets | `lib.tool_overlap(a, b)` | float in [0,1] | identical sets → 1.0; disjoint → 0.0; empty+empty → 0.0 |
| 3 | operations + threshold | `lib.split_nodes(ops, threshold=0.8)` | `SplitResult` (nodes, per-pair decisions) | same-surface same-type ops merge; distinct-surface ops split |
| 4 | a `Node` | `lib.node_scope(node)` | dict: tool_surface / memory_reads / memory_writes / input_contract / output_schema / prompt_variants | scope names only that node's tools and memory, not the whole registry |
| 5 | a candidate op + existing nodes | `lib.audit_operation(op, nodes)` | dict with verdict merge/split + reason | the Tip as a pre-add gate |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "One retrieval-and-reasoning node is simpler — it queries the graph AND does the analysis." | That is the exact failure mode the chapter names: "neither pass the quality a specialist node would." The query node holds a graph-read surface; the analysis node holds none. Different surfaces → split. |
| "These two nodes have different prompts, so they are different nodes." | Different prompts on the SAME tool surface are one node with prompt variation at the input (the Tip). The role is the tool surface, not the wording. Merge and vary the prompt. |
| "Two reasoning nodes both call no tools — merge them, same (empty) surface." | Tool-less nodes have no tool surface to key on; their role lives in prompt + DAG position. Example 2-3 keeps `classify` and `analyze` separate for this reason. This skill scores empty+empty as 0.0 → split by default. |
| "Split everything — more nodes is more modular." | Over-splitting fragments a single role across nodes that share a tool surface, adding coordination overhead for no leverage. If the tool lists overlap ≥ 80%, it is one role. |
| "Jaccard overlap is too crude for the real tool surface." | Production derives the true surface from the typed tool registry (harness surface 3) and may weight by cost/risk. The merge/split CONTRACT (≥ threshold → merge) is the stable seam; swap the scorer, keep the contract. |

## Red Flags

- **A node with a graph-read tool AND a causal-analysis task.** This is the
  retrieval-and-reasoning conflation. Split into a retrieval node (holds the
  graph-read surface) and a reasoning node (holds none).
- **Zero merges on a workflow with obvious prompt variants.** Either every
  operation genuinely has a distinct surface, or the tool lists were declared too
  finely — check that "get latency" and "get CPU" both declare the same metrics
  tool.
- **Everything merged into one node.** The tool lists were declared too coarsely
  (every op claims "aws"); declare the specific tool each op actually calls.
- **A merged node whose prompt variants have incompatible input contracts.**
  Merging is safe only when the variants operate on the same input surface; a
  contract mismatch means these were different roles after all.
- **CLI `--help` exits non-zero.** SKILL.md / CLI mismatch; the multi-harness
  invariant is broken.

## Non-Negotiable Verification

1. **Run the benchmark battery.**
   ```
   python cli.py benchmark
   ```
   Confirm 9 sample operations collapse to 8 nodes, `get_metrics`+`get_cpu`
   merge (identical tool surface), the RedAI scanner/validator pair stays split
   (overlap 0.0), and `classify`/`analyze` stay separate reasoning nodes.

2. **Inspect the split visually.**
   ```
   python cli.py split
   ```
   Confirm the `[MERGED]` node fuses the two metric-query operations and lists
   both prompt variants, and that the two disjoint execution nodes remain apart.

3. **Run the Tip as a pre-add gate.**
   ```
   python cli.py overlap --a cloudwatch_get_metric_data --b cloudwatch_get_metric_data
   python cli.py overlap --a filesystem --b browser_driver network_stack
   ```
   The first must verdict merge (1.0), the second split (0.0).

4. **JSON scope round-trips.**
   ```
   python cli.py split --json | python -c "import json,sys; json.load(sys.stdin)"
   ```
   No exception means the CLI is harness-portable and each node scope serializes.

## Security Posture

- **Prompt injection.** Operation tasks and tool names are author-controlled
  workflow metadata. This skill only tokenizes tool names and compares sets; it
  never executes a task or invokes a tool. If operation definitions are ingested
  from untrusted sources, sanitize `tools` and `task` before splitting — a
  malicious tool name could bias a merge, but cannot execute.
- **Least privilege by construction.** The whole point of the per-node scope is
  that a node sees only its own tool surface and its own memory slice, not the
  full registry or the full vertical graph. Honoring `node_scope` at execution
  time is how the harness enforces least privilege (composes with
  `capability-authorization-gate`, Ch3, and subgraph access control, Ch8).
- **Privilege escalation.** No shell invocation, no eval, no dynamic import, no
  file writes outside the read-only bundled `sample-workflow.json`. Merging two
  nodes UNIONS their tool surfaces — review a merged node's combined surface so a
  merge does not silently grant a node more capability than either input had.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, AnthonyAlcaraz / forthcoming),
Chapter 2 — Agentic Graph Architecture Foundations:

- "The Horizontal Workflow Graph" — reasoning/execution/decision/validation node
  responsibilities (Example 2-3).
- "Defining the harness" — the six harness surfaces; the per-node scope this
  skill emits maps to surfaces 3 (tool registry), 4 (memory interface), and 5
  (schema validator).
- "Splitting a workflow into nodes" — "nodes differ by tool surface, not by
  prompt"; the RedAI scanner-vs-validator worked example; the 80%-tool-overlap
  Tip.

This Generator-pattern skill runs after `dual-graph-router` routes a request to
the horizontal graph and before `investigation-dag-planner` schedules the
resulting nodes into phases.
