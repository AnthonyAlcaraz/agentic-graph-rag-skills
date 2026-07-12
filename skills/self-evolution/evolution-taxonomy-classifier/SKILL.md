---
name: evolution-taxonomy-classifier
description: |
  Locate a proposed self-evolution in the four-dimensional design space Gao
  et al. (2025) formalize: WHAT evolves (model / context / tool / architecture),
  WHEN it fires (intra-test-time within one request / inter-test-time between
  requests), HOW the agent learns (reward / imitation / population), and WHERE
  it applies (general-purpose / domain-specialized). Each axis value carries
  the graph-dependency rationale the chapter gives, and a diagnosed failure
  type routes to its primary evolution axis, timing, and mechanism (Table
  7-1). Use AFTER the
  diagnostic report exists and BEFORE you pull an evolution lever, so you fix
  the right target instead of wasting compute or introducing regressions. NOT
  for producing the diagnosis itself (that is the execution-graph plus
  cognitive-fault-isolator upstream), NOT for executing the evolution (this
  classifies and routes; it does not fine-tune, rerank, or restructure).
osmani-pattern: Reviewer
ghosh-layer: Reasoning
chapter-source: "Agentic GraphRAG (O'Reilly) Ch7 — Self-Evolution and Evaluation — A Taxonomy for Self-Evolution + Table 7-1 + Example 7 intervention routing"
references:
  - "Gao et al. (2025) four-axis self-evolution taxonomy"
  - "Waseem Alshikh (2025) GNN-inspired self-evolving models — each adaptation becomes a traceable node"
  - "Composes with execution-graph (the substrate) and the three-way intervention strategy (prompt / fine-tune / constrain)"
---

# Evolution Taxonomy Classifier

## Overview

Your agent has diagnosed a reasoning failure. The execution graph shows where
it went wrong and the cognitive-fault isolator has classified the breakdown.
Now what? The temptation is to jump straight to a fix: tweak a prompt, retrain
an adapter, add a guardrail. But self-evolution spans more than a single lever: it is a
four-dimensional design space, and pulling the wrong lever wastes compute,
introduces regressions, or both.

This skill locates any proposed evolution on the four Gao et al. axes:

- **WHAT evolves** — `model` (weights or prompts; needs execution graphs for
  causal tracing) | `context` (retrieval; this IS graph evolution: rewire
  edges, merge nodes, prune subgraphs) | `tool` (rewires the tool subgraph by
  reweighting task-type-to-tool edges on observed success) | `architecture`
  (graph surgery on the workflow graph itself).
- **WHEN it fires** — `intra_test_time` (within one request; must be
  sub-second; Reflect-Retry-Reward) | `inter_test_time` (between requests; can
  afford fine-tuning or graph restructuring; SEAL overnight, semantic
  backpropagation).
- **HOW the agent learns** — `reward_based` (scalar signals: InfoGain, user
  satisfaction) | `imitation_based` (copy successful trajectories) |
  `population_based` (maintain variants, select fittest).
- **WHERE it applies** — `general_purpose` (all tasks) | `domain_specialized`
  (one vertical, e.g. cascade failures in microservice topologies).

Every axis requires graph structure to operate. As the chapter states: the
graph is not optional infrastructure here, it is the substrate that makes any
of these axes operable. Alshikh's production research reinforces the point: the
first methodology is GNN-inspired, where "each adaptation becomes a traceable
node." The classifier attaches that graph-dependency rationale to every value
it assigns, and `route_failure` maps a diagnosed failure to its axis per Table
7-1.

## When to Use

- AFTER a diagnostic report exists and you are deciding which evolution lever
  to pull
- To sanity-check a proposed evolution: is this really model evolution, or is
  it context evolution wearing a model-evolution costume?
- To route a diagnosed failure type (FORMAT, REASONING, KNOWLEDGE) to its
  primary axis, timing, and mechanism
- When designing a self-evolution loop and you need the four-axis vocabulary to
  keep intra-test-time and inter-test-time paths distinct

Phrases: "which evolution lever", "classify this evolution", "self-evolution
taxonomy", "what evolves / when / how / where", "route this failure",
"Table 7-1 routing", "is this model or context evolution".

## When NOT to Use

- **Producing the diagnosis.** The failure classification comes from the
  execution graph plus the cognitive-fault isolator upstream. This skill
  consumes a diagnosis; it does not generate one.
- **Executing the evolution.** This is a Reviewer, not an Actuator. It tells
  you `model / inter_test_time / reward_based / domain_specialized`; it does not
  run the fine-tune, the rerank, or the graph surgery.
- **One-shot single-call agents.** No evolution loop, no axes to place.
- **Choosing K in a retrieval pipeline or any within-axis hyperparameter.** The
  classifier picks the axis, not the setting inside it.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | (none) | `cli.py axes` | Pretty-print the four axes, allowed values, and each value's graph rationale | Four axes printed; every value has a non-empty rationale line |
| 2 | what + when + how + where (+ notes) | `lib.classify_from_signals(...)` | `EvolutionClassification` with `graph_rationale` filled per axis | Each axis value in its allowed set; unknown value raises ValueError |
| 3 | free-form proposal dict {description, target, timing, mechanism, scope} | `lib.classify(proposal)` | `EvolutionClassification` (keywords mapped to axis values, then delegated to step 2) | "fine-tune adapter" -> model; "rerank KG subgraph" -> context; "API endpoint" -> tool |
| 4 | failure_type (+ recurring, + is_format) | `lib.route_failure(...)` | `{evolution_axis, timing, mechanism, rationale}` per Table 7-1 | FORMAT -> architecture / structural-constraint / inter; REASONING single-node -> model / prompt / intra; KNOWLEDGE systemic -> model / fine-tune / inter |
| 5 | classification | `EvolutionClassification.to_dict()` | JSON-serializable dict | Round-trips through `json.dumps` without error |
| 6 | scenario name `devops` | `cli.py scenario devops` | Classifies the DevOps prompt-refinement evolution (model / inter_test_time / reward_based / domain_specialized) | Output places all four axes and prints the failure routing for the cascade-misprediction pattern |
| 6b | when_fires + measured op ms + request budget ms | `lib.budget_check(when, ms, budget)` | verdict OK_IN_PATH / MOVE_TO_INTER / OK_OFF_PATH | an over-budget intra-test-time op MUST verdict MOVE_TO_INTER |
| 7 | (none) | `cli.py benchmark` | Assertion battery | Prints `N/M passed`, exits 0 on all-pass |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "The diagnosis is clear, I'll just fix it — I don't need to classify." | The chapter is explicit: "self-evolution is not a single lever. It is a four-dimensional design space, and pulling the wrong lever wastes compute, introduces regressions, or both." Classification is what prevents the wrong lever. |
| "Rerankng retrieval is model evolution — the model does the reranking." | No. Ch7: context evolution "restructures what the agent retrieves." It IS graph evolution: "you evolve context by rewiring edges, merging redundant nodes, and pruning stale subgraphs." Reranking a subgraph touches `context`, not `model`. Calling it model evolution routes you to a fine-tune you do not need. |
| "A format error just needs the model to speak JSON better — that's fine-tuning." | Ch7 rejects this directly: "Rather than teaching the model to speak JSON better through more training, attach an output schema constraint directly to that specific node." FormatViolation routes to `architecture` (structural constraint), a permanent fix, not `model`. |
| "Intra-test-time and inter-test-time are the same thing at different speeds." | The distinction is what the latency budget rests on: "intra-test-time evolution must be fast (sub-second decisions), while inter-test-time evolution can afford expensive operations like fine-tuning or graph restructuring." Mis-timing a fine-tune into the request path breaks the latency budget. |
| "One localized reasoning miss means we should fine-tune." | Ch7 three-way strategy: a "localized reasoning failure (low InfoGain on one or two steps)" calls for prompt refinement, which is "fast, reversible, and the right first resort." Fine-tuning is for a "recurring pattern of the same reasoning failure type." `recurring=False` stays on the prompt path. |
| "Domain-specialized versus general-purpose is a soft preference, not a real axis." | Ch7: "Your DevOps agent does not need to improve at poetry, but it absolutely needs to get better at predicting cascade failures in microservice topologies." WHERE scopes the evolution to a subgraph region; skipping it spends compute improving tasks the agent will never run. |

## Red Flags

- **A context-evolution proposal classified as `model`.** Reranking, merging
  memory nodes, or pruning subgraphs is graph evolution. Routing it to a
  fine-tune wastes a heavyweight lever on a retrieval fix.
- **A FormatViolation routed to `model` / fine-tune.** The chapter's permanent
  fix is a structural constraint on the workflow-graph node, not more training.
- **A fine-tune assigned `intra_test_time`.** Fine-tuning cannot run sub-second
  inside a request. If the timing says intra, the mechanism is wrong.
- **`graph_rationale` empty for a chosen axis value.** The whole point is that
  every axis depends on graph structure; an empty rationale means the
  classifier bypassed the chapter grounding.
- **`route_failure` called on an undiagnosed failure string.** Unknown
  failure_type raises ValueError by design; catch it and go back to the
  diagnosis, do not guess an axis.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report all
   gates passed:
   - every axis value validates through `classify_from_signals`
   - an unknown value on any axis raises ValueError
   - `classify()` maps a "fine-tune adapter" proposal to `what=model` and a
     "rerank KG subgraph" proposal to `what=context`
   - `route_failure(FORMAT)` returns `architecture` / `structural-constraint`;
     REASONING single-node returns `model` / `prompt` / `intra_test_time`;
     recurring REASONING and systemic KNOWLEDGE escalate to `model` /
     `fine-tune` / `inter_test_time`
   - `graph_rationale` is populated for all four chosen axis values
2. **Run the DevOps scenario.** `python cli.py scenario devops` classifies the
   prompt-refinement evolution as `model / inter_test_time / reward_based /
   domain_specialized` and prints the failure routing for the recurring
   cascade-misprediction pattern.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints the SKILL.md
   description.

## Security Posture

- **Prompt injection.** The free-form proposal passed to `classify` is treated
  as untrusted text. Keyword matching is read-only substring inspection; no
  part of the proposal is executed, eval'd, or used to construct a shell
  command. A proposal that embeds instructions has no path to action here: the
  output is a fixed-vocabulary classification, never a passthrough of proposal
  text into a privileged call.
- **Data exfiltration.** `lib.py` makes no network calls. Classification runs
  entirely in-memory over the caller-supplied dict and the module's own axis
  constants. CLI output goes to stdout; the caller owns downstream piping.
- **Privilege escalation.** No shell invocation, no concatenated input to a
  shell, no file writes. The only file read is an optional `--path
  proposal.json` the caller names explicitly, plus `SKILL.md` for the help
  description. Axis constants are author-controlled and stdlib-only.

## Composition

- **Composes with** the `execution-graph` primitive (the substrate every axis
  depends on). The diagnosis this skill consumes is a query over that graph.
- **Composes with** the three-way intervention strategy (prompt / fine-tune /
  constrain): `route_failure` is the routing function Ch7 Example 7 describes,
  turning a diagnostic report's failure type into an axis, timing, and
  mechanism.
- **Feeds** the actuation layer (semantic backpropagation, SEAL, TPT,
  Reflect-Retry-Reward). This skill picks the lever; those frameworks pull it.
- **Reviewer, does not compose with,** any actuator: it emits a classification
  and a route, never a weight update or a graph mutation.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien),
Chapter 7 — Self-Evolution and Evaluation, the "A Taxonomy for Self-Evolution"
section, Table 7-1 (failure-to-evolution routing), and the intervention-routing
Example. Key references named in the chapter: Gao et al. (2025) four-axis
self-evolution taxonomy; Waseem Alshikh (2025) production research on
self-evolving models, GNN-inspired methodology where "each adaptation becomes a
traceable node"; the SEAL, TPT, and Reflect-Retry-Reward learning frameworks.
This skill is the Reviewer-pattern routing front end for that section: it
classifies and routes, and the downstream frameworks execute the evolution.
