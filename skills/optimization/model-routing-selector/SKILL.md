---
name: model-routing-selector
description: |
  Match model capability to task complexity across a horizontal workflow graph.
  Given a node, pick the cheapest model that meets its quality bar, using one of
  three routing strategies: static routing by node type, threshold-based
  cascading (FrugalGPT), or learned routing (RouteLLM / MixLLM). Re-derives the
  book's DevOps DEVOPS_MODEL_CONFIG from first principles and reports the blended
  cost reduction (~80%). Use when every node of an agentic pipeline runs on the
  same frontier model and the invoice is unsustainable. NOT for single-model
  systems, NOT for choosing WHICH graph model to use (that is graph-model-selector),
  NOT for measuring a policy after the fact (that is cost-performance-scorer).
osmani-pattern: Inversion
ghosh-layer: Primitive
chapter-source: "Agentic Graph RAG (O'Reilly) Ch8 — Optimization"
---

# Model Routing Selector

## Overview

The horizontal workflow graph (Chapters 5-6) decomposes the agent into
specialized nodes: a query analyst, a retrieval strategist, a synthesis node, a
validation node. Most teams start with the same frontier model powering every
node. It works, and it is wildly expensive.

Selective intelligence matches model capability to task complexity. Running a
3B SLM can be 10-30x cheaper per token than its 405B sibling; at thousands or
millions of invocations per day, that difference decides whether the project
survives its first budget review. The chapter's key insight is that most nodes
do not need frontier reasoning — a fine-tuned 3B model classifies alerts, a
3.8B Triplex model beats GPT-4o at knowledge-graph construction, and only the
open-ended synthesis and causal-reasoning nodes (10-20% of invocations)
reliably benefit from a frontier model.

This skill re-derives the book's DevOps assignment (Example 8-13) from a node's
`required_quality` bar and a per-model cost/capability catalog, so you can see
*why* each node gets the model it gets rather than accepting an opaque config.

## When to Use

- A pipeline runs every node on one frontier model and cost is unsustainable.
- You are adding a node and need to know the cheapest model that clears its bar.
- A node's per-query difficulty varies and you are deciding static vs cascade.
- You have production traffic and want to justify a learned router.

Phrases that should invoke this skill: "which model for this node", "selective
intelligence", "cheapest model that meets the bar", "static vs cascade routing",
"cut inference cost", "RouteLLM", "FrugalGPT cascade".

## When NOT to Use

- **Single-model systems.** With one node type and one model there is nothing
  to route.
- **Choosing the graph data model** (property graph vs RDF vs hypergraph) — that
  is `graph-model-selector` (Ch3).
- **Measuring a routing policy after deployment** — that is
  `cost-performance-scorer` (Ch8). This skill decides routing *before* you run;
  that skill scores what actually happened.
- **KV-cache / latency budgeting** — that is `kv-cache-latency-budgeter` (Ch8).
  Routing lowers cost per weight; it does not lower the concurrency ceiling.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Node name | `lib.NODES[name]` | Node with task_class + required_quality | Node exists; bar in [0,1] |
| 2 | Node | `lib.cheapest_meeting_bar(name)` | Cheapest model whose effective quality clears the bar | `effective_quality >= required_quality`, or a cascade recommendation |
| 3 | Node + confidence | `lib.cascade_route(name, confidence)` | Served tier (cheap/mid/frontier) | High confidence -> cheap SLM; low -> frontier |
| 4 | Node + cost threshold | `lib.learned_route(name, t)` | RouteLLM-style model id | `router-mf-<t>`; lower t -> weak model |
| 5 | Escalation rate | `lib.pipeline_cost(rate)` | Blended cost vs frontier-everywhere | `reduction_pct` >= 65% equal-weight (book: ~80% token-weighted) |
| 6 | Selected model | (your runtime) invoke via vLLM multi-LoRA / API | Model response | If quality below bar in production, re-evaluate with cost-performance-scorer |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|-----------------------|---------------------|
| "Context windows are cheap now — just use the frontier model everywhere." | The book's economics are per-token, not per-window. A 3B SLM is 10-30x cheaper per token; at production volume the frontier-everywhere invoice is what shelves the project (Ch8 opening). |
| "A small model can't be trusted on a high-stakes node." | The AlertClassifier needs 0.99 accuracy AND runs on a 3B model — because a *fine-tuned specialist* reaches the bar on a narrow task. Capability on the task, not raw size, is the criterion (Example 8-4, Triplex, Kakao 63% preference). |
| "Cascades add latency, skip them." | For nodes where difficulty varies, a cascade serves the easy majority cheaply and escalates the hard minority. Static routing to the frontier pays frontier cost on every query, including the 80% that a mid-tier model handles (Ch8 threshold-based cascading). |
| "Learned routing is the sophisticated choice, always use it." | RouteLLM/MixLLM need production traffic to train and engineering to maintain. The book: static routing or threshold cascading covers 80% of the benefit at 20% of the complexity. Start static. |
| "Route CausalAttributionNode straight to the frontier — it's reasoning." | It is open-ended, so a small model can't handle *every* case, but it handles the routine ones. The cascade (8B -> sonnet, escalate below 0.7) is why blended cost lands at ~1/5th, not 1x (Example 8-13). |

## Red Flags

- **Every node routes to the frontier model.** Either the bars are set too high
  or the specialization mechanism is disabled. Re-check `effective_quality`.
- **A 3B model is selected for open-ended synthesis.** The specialist ceiling
  only applies to `classification`/`extraction` task classes; synthesis must
  fall through to a capable model.
- **Blended reduction below 70%.** The pipeline is mis-tiered — probably a
  routine node is still on the frontier model.
- **Cascade thresholds set so high nothing is served cheap.** You lose the
  savings; calibrate against a per-node eval set (cost-performance-scorer).
- **CLI `--help` exits non-zero.** SKILL.md / CLI mismatch; the multi-harness
  invariant is broken.

## Non-Negotiable Verification

Before shipping a routing policy built on this skill:

1. **Run the benchmark battery.**
   ```
   python cli.py benchmark
   ```
   Confirms the router re-derives the book's DEVOPS_MODEL_CONFIG for all five
   nodes and that blended reduction is >= 70%.

2. **Inspect the routing decision for a high-stakes node.**
   ```
   python cli.py route AlertClassifier
   python cli.py route CausalAttributionNode
   ```
   Confirm AlertClassifier picks the 3B SLM (specialist meets 0.99) and
   CausalAttributionNode is returned as a *cascade*, not raw frontier.

3. **Confirm the blended-cost math.**
   ```
   python cli.py pipeline --escalation-rate 0.3
   ```
   Equal-weight nodes land near 70%; the book's ~80% figure assumes token
   weighting where the frontier synthesis node dominates the baseline. Either
   way the reduction is the difference between a viable production system and a
   budget overrun (Ch8).

4. **Domain test in the notebook.** Run `notebooks/ch8-optimization.ipynb`;
   confirm the selective-intelligence section drives per-node model assignment
   and the blended cost is computed against `moto`-mocked CloudWatch cost signals.

## Security Posture

- **No model invocation here.** `lib.py` makes no network calls; it returns a
  model *identifier* and rationale. The caller invokes the model.
- **Cost figures are advisory.** The cost multipliers are book figures for
  relative reasoning; real per-token pricing changes. Recompute against live
  pricing before committing a budget.
- **Routing-as-attack-surface.** If a learned router ingests query text, treat
  that text as untrusted (an adversarial query could bias routing toward an
  expensive or a too-weak model). Sanitize before the router sees it — the
  Retrieved-Content Adversarial-Input discipline applies at the router seam.

## Composition

- **Composes with** `cost-performance-scorer` (Ch8): this skill decides routing
  a priori; that skill measures cost-per-successful-completion a posteriori and
  feeds the calibration back into the thresholds here.
- **Composes with** `kv-cache-latency-budgeter` (Ch8): routing lowers cost per
  weight; the budgeter checks the resulting fleet against the concurrency and
  latency ceiling.
- **Feeds** the vLLM multi-LoRA serving pattern (Ch8 Example 8-12): the selected
  specialist adapters share one base model on one GPU.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, AnthonyAlcaraz / forthcoming),
Chapter 8 — Optimization, "Selective Intelligence" / "Routing Strategies".
Key references named in the chapter:

- NVIDIA Research SLM-for-agentic-AI position paper (front-door router)
- FrugalGPT (threshold-based cascade)
- RouteLLM (>2x cost reduction, 95% GPT-4 quality on MT-Bench)
- MixLLM (contextual bandit; 97% GPT-4 quality at 24% cost)
- Triplex 3.8B (beats GPT-4o at KG construction)
- Kakao AI Shopping Mate (format adherence 0.655 -> 0.987, accuracy 0.578 -> 0.890,
  smaller fine-tuned models preferred over GPT-4o in 63% of 2,100 turns)
- Example 8-13 DEVOPS_MODEL_CONFIG (the derivation target for this skill)
