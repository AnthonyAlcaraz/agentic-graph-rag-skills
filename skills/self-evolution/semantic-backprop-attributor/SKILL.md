---
name: semantic-backprop-attributor
description: |
  Ch7 self-evolution primitive: attribute a failure to the node that actually
  caused it, then generate NEIGHBOR-AWARE textual feedback that flows backward
  through the execution graph from the point of failure. Adapts TextGrad's
  textual-gradient insight (feedback as a gradient signal) plus the chain rule:
  when generating feedback for a node based on what its successor needed, the
  feedback includes the outputs of ALL OTHER predecessors of that successor.
  That neighbor context is what prevents incorrect credit assignment. Use AFTER a
  diagnostic report has localized a failing node and you need coherent,
  cross-graph feedback before an intervention. NOT for single-node pipelines
  with no neighbors (there is no action-at-a-distance to prevent), NOT the
  intervention itself (this decides where and what should change, SEAL/TPT/prompt
  refinement make the change stick).
osmani-pattern: Generator
ghosh-layer: Workflow
chapter-source: "Agentic GraphRAG (O'Reilly) Ch7 — Self-Evolution and Evaluation — Semantic Backpropagation: Coherent Evolution Across the Graph + the neighbor-aware feedback example"
references:
  - "TextGrad — textual feedback as a gradient signal (chapter foundational cite)"
  - "Composes on top of the execution-graph primitive and the diagnostic report"
---

# Semantic Backpropagation Attributor

## Overview

Agents are graphs, not pipelines. The dangerous failure mode in a self-evolving
system is not a bad update. It is a good update to one node that silently breaks
another. In a deeply interconnected graph, improving a component in isolation
causes "action at a distance" failures that are hard to trace. Semantic
backpropagation is the mechanism that prevents this.

The idea adapts the chain rule. In numerical backpropagation, gradients flow
backward through a computational graph, updating each parameter by how it
contributed to the loss. Semantic backpropagation does the same in natural
language: the gradient is a structured description of the required change, and it
flows backward through the execution graph from the point of failure.

Neighbor-awareness is the decisive part. When generating feedback for node v
based on what successor w needed, the feedback includes not just v's output and
w's error but the outputs of ALL OTHER predecessors of w. That context is what
makes the feedback precise.

The chapter's concrete example: an Extractor pulls "Revenue: $10M", a
CurrencyConverter converts it to "EUR 9.5M", and a Validator (which also received
a DateChecker's "Date: 2022") flags that the exchange rate was 0.9, not 0.95.
Without neighbor context, feedback to the Extractor reads "your $10M led to a
conversion error" and the Extractor might wrongly change its extraction. With
neighbor context, the error is correctly assigned to the CurrencyConverter's rate
lookup and the Extractor is left unchanged. the neighbor-aware feedback example shows the same shape for
a DevOps CausalAttributionNode, with ChangelogRetrieval and KnowledgeGraphQuery
as the neighbor predecessors.

**Honesty note on the metaphor:** "backpropagation" here is an analogy, not a
mechanism. A numerical gradient is exact and deterministic; this skill's
"gradient" is credit assignment produced by LLM judgment over the execution
graph — structured, neighbor-aware, and far better than unstructured blame, but
still a hypothesis about causality, not a derivative. Treat every attribution
as a claim to verify (rerun the trace with the blamed node patched) before
committing an intervention on it. What IS deterministic in this skill: the
graph traversal, the neighbor-context assembly, and the routing of the verdict.

## When to Use

- After a diagnostic report has localized a failing node and you need feedback
  that will not break the node's neighbors
- Multi-node agent graphs where a fix to one node could ripple ("action at a
  distance")
- Before any intervention (prompt refinement, SEAL curriculum, fine-tune) so the
  change is grounded in what every connected node needed
- Attributing a surfaced error to its true origin when the node that flagged it
  is not the node that caused it

Phrases: "semantic backpropagation", "neighbor-aware feedback", "which node
caused this", "credit assignment", "textual gradient", "action at a distance",
"leave the Extractor unchanged".

## When NOT to Use

- Single-node or linear pipelines with no sibling predecessors: there is no
  neighbor context to add and no action-at-a-distance to prevent
- As the intervention itself: this decides WHERE and WHAT should change; SEAL /
  TPT / prompt refinement make the change stick (chapter, A Suite of
  Self-Improvement Frameworks)
- Before diagnosis: run the execution-graph and diagnostic layers first so you
  have a localized failing node to backpropagate from
- When neighbor outputs are untrusted external content: sanitize first (see
  Security Posture) before folding them into feedback

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | edges (parent, child), node_id | `lib.predecessors_of(edges, node_id)` | parents of node_id, in edge order | returns [Extractor] for CurrencyConverter; [CurrencyConverter, DateChecker] for Validator |
| 2 | edges, node_outputs, target_node, successor | `lib.neighbor_context_for(...)` | dict "<node>_output" of every OTHER predecessor of successor | target_node excluded; sibling predecessor included |
| 3 | edges, node_outputs, failure_node, predicted, actual | `lib.attribute(...)` | responsible node_id (may differ from failure_node) | currency case returns CurrencyConverter, not Extractor or Validator |
| 4 | target_node, successor, edges, node_outputs, predicted, actual, feedback_text | `lib.generate_feedback(...)` | `SemanticFeedback` (the neighbor-aware feedback example shape) | neighbor_context populated; empty feedback_text synthesizes a neighbor-grounded string |
| 5 | edges, node_outputs, failure_node, predicted, actual, feedback_text | `lib.backprop(...)` | attribute then generate_feedback for the responsible node | devops case targets CausalAttributionNode with both neighbor outputs |
| 6 | `SemanticFeedback` | `.to_dict()` / `SemanticFeedback.from_dict(d)` | serialize / deserialize | round-trip preserves all four fields |
| 7 | list of `NodeIO` | `lib.outputs_from(nodes)` | node_outputs mapping | keys match node ids, values are output strings |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "The node that flagged the error is the node to fix." | The chapter is explicit: the Validator surfaces the error but "the error originated in the CurrencyConverter's rate lookup." Attribution is a graph question, not a which-node-raised-it question. |
| "Feedback to a node only needs that node's output and the error." | That is exactly the failure mode the chapter names. Without the DateChecker's output as neighbor context, the Extractor "might reasonably conclude it should have extracted a different number, a wrong fix." Include all other predecessors of the successor. |
| "Improving one node in isolation is fine if its own tests pass." | Ch7: "improving a component in isolation can cause 'action at a distance' failures." A change to one node must be evaluated in the context of what every other connected node needs. |
| "A vague 'consider more factors' directive is enough feedback." | the neighbor-aware feedback example: the neighbor_context (timeout 30s->10s present in input, no batch_charge usage found) is "what makes the feedback specific enough to generate a targeted prompt update rather than a vague directive." |
| "Attribution and the intervention are the same step." | Ch7: "semantic backpropagation determines where to change and what the change should accomplish. The remaining question is how to make that change stick." Different frameworks (SEAL / TPT / prompt refinement) own the how. |

## Red Flags

- **Feedback sent to the node that surfaced the error rather than the node that
  caused it.** Attribution collapsed to failure_node. Check that a predecessor
  carrying the wrong value is being implicated.
- **neighbor_context is empty on a node with sibling predecessors.** The
  successor was mis-identified or predecessors_of returned nothing. The feedback
  is now un-grounded and can trigger a wrong fix.
- **neighbor_context includes the target node's own output.** The exclusion in
  `neighbor_context_for` was bypassed. Neighbor evidence must be about the
  siblings, not the target.
- **Attribution changes the Extractor in the currency case.** Incorrect credit
  assignment. The DateChecker + Validator evidence exonerates the Extractor; the
  CurrencyConverter's rate lookup is the origin.
- **Synthesized feedback names no neighbor evidence.** An empty feedback_text
  produced a generic string. The default must weave in the neighbor outputs.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 6/6:
   predecessors_of returns correct parents; neighbor_context_for excludes the
   target and includes the sibling predecessor; the currency case attributes to
   CurrencyConverter (not Extractor); the devops feedback contains the neighbor
   evidence (timeout 30s->10s present in input); SemanticFeedback.to_dict
   round-trips.
2. **Run the currency scenario.** `python cli.py scenario currency` shows
   attribution landing on CurrencyConverter with the Extractor left unchanged.
3. **Run the devops scenario.** `python cli.py scenario devops-prediction`
   emits the the neighbor-aware feedback example neighbor-aware feedback for the CausalAttributionNode.
4. **Verify CLI help.** `python cli.py --help` exits 0 and prints the SKILL.md
   description.

## Security Posture

- **Prompt injection.** node_outputs and neighbor evidence are folded into the
  textual gradient. If any node output originates from untrusted external
  content (a scraped changelog, a retrieved document), sanitize it before it
  enters the feedback string. Treat neighbor outputs as untrusted until
  validated; a malicious changelog line could inject instructions into the
  synthesized feedback that a downstream prompt-update step would then apply.
- **Data exfiltration.** `lib.py` makes no network calls and no file writes. The
  CLI reads a caller-supplied `--path` JSON and prints results to stdout; the
  caller owns downstream piping. Nothing leaves the process.
- **Privilege escalation.** No shell invocation, no concatenated input to a
  shell, no file writes outside the given paths. Attribution is a deterministic
  numeric-evidence heuristic over in-memory dicts; the production swap to an LLM
  judge is a documented seam, not an ambient capability.

## Composition

- **Composes on top of** the execution-graph primitive: the edges and
  node_outputs it operates over are the graph that primitive captures.
- **Composes after** the diagnostic report: attribution starts from the
  localized failing node the diagnosis produced.
- **Feeds into** the intervention frameworks (SEAL targeted curriculum, TPT,
  prompt refinement): the SemanticFeedback is their input. This skill decides
  where and what; they make the change stick.
- **Generator pattern / Ghosh Workflow.** It generates a structured feedback
  artifact by orchestrating graph traversal, attribution, and synthesis across
  several nodes, one workflow layer above a single primitive.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien) Ch7 — Semantic
Backpropagation: Coherent Evolution Across the Graph, plus the neighbor-aware feedback example
(Neighbor-aware semantic feedback for the causal attribution node). The chapter
credits TextGrad for the foundational insight that textual feedback can serve as
a gradient signal, and adapts the chain rule so a structured natural-language
gradient flows backward through the execution graph with neighbor-aware context.
