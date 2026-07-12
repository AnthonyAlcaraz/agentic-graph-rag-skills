---
name: cost-performance-scorer
description: |
  Score a multi-model routing policy on cost versus quality using the two
  metrics that actually decide selective intelligence: cost per successful
  completion (not cost per token) and a per-node quality parity threshold with
  domain-specific failure weights. Wraps a NodeInvocation log, computes
  cost-per-success and p95 latency per node, and evaluates a candidate model
  against a per-node evaluation set drawn from production data. Use to justify
  or recalibrate a routing decision AFTER you have run traffic. NOT for deciding
  routing a priori (that is model-routing-selector), NOT for generic benchmarks
  (MMLU/HumanEval do not capture your alert taxonomy), NOT for latency/KV
  budgeting (that is kv-cache-latency-budgeter).
osmani-pattern: Reviewer
ghosh-layer: Primitive
chapter-source: "Agentic GraphRAG (O'Reilly) Ch8 — Optimization"
---

# Cost-Performance Scorer

## Overview

Routing strategies are only as good as the data that informs them. Selective
intelligence works only if you can measure it, and the book names two metrics
that matter:

- **Cost per successful completion.** Cost per *task completed correctly*, not
  cost per token. A cheap model that fails 40% of the time is not cheaper than
  an expensive model that succeeds on the first attempt — the wasted spend on
  failures is amortized over the successes.
- **Quality parity threshold.** The minimum acceptable quality per node type.
  The AlertClassifier may need 0.99 (a wrong validation is worse than none); the
  QueryAnalyst may tolerate 0.90 because downstream nodes recover from
  misclassification.

The book's harness wraps every node and logs a `NodeInvocation` per call
(Example 8-3). Success is judged per node — matching a human-labeled severity
for the AlertClassifier, an SRE accepting the recommendation for
PredictionSynthesis. Each candidate model is scored against a *per-node*
evaluation set with domain failure weights (Example 8-4): a P1 alert
misclassified as P3 is 10x worse than the reverse, an asymmetry a generic
accuracy metric cannot express. Kakao's AI Shopping Mate is the worked anchor:
restructuring GPT-4o-everywhere into a workflow graph of fine-tuned 27-32B
models moved format adherence from 0.655 to 0.987 and accuracy from 0.578 to
0.890, with the smaller models preferred over GPT-4o in 63% of 2,100 turns.

## When to Use

- You have run production traffic through a routed pipeline and need to know
  which node is over- or under-provisioned.
- You are choosing a specialist SLM and must evaluate it on your data, not MMLU.
- A cheap node looks cheap per token but you suspect its failure rate erases the
  savings.
- You need a per-node quality gate before promoting a routing change.

Phrases that should invoke this skill: "cost per successful completion", "is
this model actually cheaper", "per-node evaluation set", "quality parity
threshold", "score the routing policy", "weighted error rate".

## When NOT to Use

- **Deciding routing before you run** — that is `model-routing-selector` (Ch8).
  This skill measures what happened; that one decides what should happen.
- **Generic capability benchmarking** — MMLU/HumanEval scores do not predict
  performance on your alert taxonomy (Ch8 Common Pitfalls: "benchmarking models
  on the wrong evaluation set").
- **Latency / KV-cache budgeting** — that is `kv-cache-latency-budgeter`.
- **When you have no ground-truth success signal.** Cost-per-success requires a
  per-node evaluator (gold labels or downstream acceptance). Without it, you can
  only report cost per call, which is the metric this skill exists to replace.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Invocation log JSON | `_load_tracker(path)` | CostTracker of NodeInvocations | Each row has node_name, cost_usd, success |
| 2 | Node name | `tracker.cost_per_success(node)` | $/successful completion | Finite, > 0; higher than $/call by the failure ratio |
| 3 | Node name | `tracker.node_report(node)` | success_rate + p95 latency + $/success | success_rate in [0,1] |
| 4 | (gold, pred) pairs + eval set | `lib.evaluate_candidate(preds, set)` | accuracy + meets_threshold + weighted_error_rate | weighted_error applies the domain failure weights |
| 5 | Full tracker | `lib.score_policy(tracker)` | Pipeline total + blended $/success | Sums per-node; blended ≥ max single-node $/success/pipeline-len |
| 6 | Two model profiles | `lib.compare_cost_per_success(...)` | Which is cheaper per call vs per success | Cheaper-per-call and cheaper-per-success can disagree |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|-----------------------|---------------------|
| "This model is 10x cheaper per token, ship it." | Cost per token is not cost per *success*. If it fails 40% of the time and each failure triggers a retry or a downstream error, the true cost per completed task can exceed the reliable model (Ch8). Measure cost-per-success. |
| "It scores 85% on MMLU, that's good enough." | MMLU does not contain your alert-classification taxonomy. The book's pitfall is exactly this: build a per-node eval set from production data and re-evaluate when the task distribution shifts. |
| "Accuracy is 0.985, close enough to the 0.99 bar." | For the AlertClassifier a missed P1 is catastrophic; the bar is 0.99 and 0.985 fails it. The weighted_error_rate exists to price that asymmetry (P1_as_P3 = 10x). |
| "One eval set for the whole pipeline is simpler." | Nodes have different stakes: 0.99 for the AlertClassifier, 0.90 for the QueryAnalyst. A shared set over- or under-gates half the pipeline (Example 8-4). |
| "Smaller models always cost quality." | Kakao's fine-tuned 27-32B models beat GPT-4o on their task (0.987 vs 0.655 format adherence) and were preferred in 63% of 2,100 turns. Specialization can *improve* quality because the training signal is focused. |

## Red Flags

- **Cost per success reported as cost per call.** If success is not evaluated,
  the headline metric is missing; wire a per-node evaluator first.
- **A node's success_rate is 1.0 across thousands of calls.** Either the
  evaluator is a no-op or the eval set is trivial — real production nodes fail.
- **weighted_error_rate equals the raw error rate.** The failure weights are not
  being applied; check the `<gold>_as_<pred>` keys.
- **Blended $/success unchanged after a routing change.** The change moved cost
  between nodes without improving completions; re-inspect per-node reports.
- **CLI `--help` exits non-zero.** SKILL.md / CLI mismatch.

## Non-Negotiable Verification

Before trusting a policy score:

1. **Run the benchmark battery.**
   ```
   python cli.py benchmark
   ```
   Confirms cost-per-success is computed, the domain failure weights apply
   (P1_as_P3 = 10.0), the 0.99 threshold gate is honoured, and the
   cost-per-success inversion holds (cheaper-per-call ≠ cheaper-per-success).

2. **Score the sample policy and read the per-node table.**
   ```
   python cli.py score
   ```
   Confirm the SLM nodes are far cheaper per success than the frontier synthesis
   node, and that a node with seeded failures shows success_rate < 1.0.

3. **Evaluate a candidate against a real per-node set.**
   ```
   python cli.py evaluate AlertClassifier
   ```
   Confirm a single P1-as-P3 miss produces a weighted_error_rate of 10.0, not 1.0.

4. **Domain test in the notebook.** Run `notebooks/ch8-optimization.ipynb`;
   confirm the cost-performance section reads `moto`-mocked CloudWatch cost and
   latency signals into the tracker and computes cost-per-success per node.

## Security Posture

- **Read-only over the invocation log.** `lib.py` makes no network calls and
  writes nothing; it consumes a log the caller supplies.
- **Cost figures are inputs, not authority.** The log's `cost_usd` values come
  from the caller's pricing; verify them against live pricing before acting.
- **Untrusted logs.** If the invocation log is machine-generated from an
  external system, validate the schema (numeric costs, boolean success) before
  scoring — a poisoned log could hide a failing node behind fabricated successes.

## Composition

- **Closes the loop with** `model-routing-selector` (Ch8): the cost-per-success
  numbers here recalibrate the cascade thresholds and per-node bars there.
- **Feeds** the Ch7 self-evolution loop: cost-per-success and weighted-error are
  evaluation signals the diagnostic engine can act on.
- **Pairs with** `kv-cache-latency-budgeter` (Ch8): this scores cost/quality;
  that scores latency/concurrency. Both gate a production routing change.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien),
Chapter 8 — Optimization, "Measuring Cost-Performance Tradeoffs". Key references:

- Example 8-3 `CostTracker` / `NodeInvocation` (cost per successful completion)
- Example 8-4 per-node evaluation sets with domain failure weights
- Kakao AI Shopping Mate (0.655 -> 0.987 format adherence, 0.578 -> 0.890
  accuracy, 63% preference over GPT-4o across 2,100 turns)
