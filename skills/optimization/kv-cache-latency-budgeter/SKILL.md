---
name: kv-cache-latency-budgeter
description: |
  Budget a specialist model fleet against the two production bottlenecks:
  KV-cache-bound concurrency and end-to-end latency. Computes how many concurrent
  users a GPU can host (peak KV per active user, not model size, is the binding
  constraint), proves that quantizing weights does not move that ceiling while KV
  compression (MEMENTO) does, estimates GPU speedups for graph analytics (cuGraph
  / nx-cugraph), and checks a multi-node workflow against the book's latency
  budget and the sub-2s target. Use when scaling a multi-model agent to real-time
  latency. NOT for model selection (that is model-routing-selector), NOT for
  cost/quality scoring (that is cost-performance-scorer), NOT for defining GPU
  terms (that is gpu-glossary-anchor).
osmani-pattern: Reviewer
ghosh-layer: Primitive
chapter-source: "Agentic Graph RAG (O'Reilly) Ch8 — Optimization"
---

# KV-Cache Latency Budgeter

## Overview

The architecture distributes work across two channels that both bottleneck at
production scale: graph traversals that navigate the knowledge graph, and
model-inference calls that power the workflow nodes.

Graph analytics (PageRank, community detection, centrality) are bound by memory
bandwidth, not compute — irregular random access CPUs handle poorly and GPUs
handle well. cuGraph / nx-cugraph report order-of-magnitude speedups: PageRank
137x on A100, Louvain 125x over NetworkX, multi-GPU PageRank 80x over a 100-node
Spark cluster, and betweenness centrality on the LiveJournal graph (4.8M nodes,
69M edges) from 7 minutes to 5 seconds — a 485x speedup. For the DevOps agent,
blast-radius analysis drops from 3-5 seconds on CPU to under 100 ms on one GPU.

Inference latency is bound by the KV cache. Multi-LoRA serving lowers cost per
weight but not the binding constraint: **peak KV per active user, not model
size, sets how many concurrent analyses one H100 (80 GB) can host.** Quantizing
the weights does not move this ceiling — you have to bound the cache itself. The
chapter's first production-ready recipe is Microsoft MEMENTO: a two-stage
supervised fine-tune on 228,000 traces teaches the model to segment its chain of
thought into blocks, emit a compressed summary token per block, and mask the
original block from future attention, producing a sawtooth KV pattern.

> The chapter's source redacts the exact MEMENTO reduction factor, per-block
> compression factor, and concurrent-incident multiplier. This skill treats
> those as **caller-measured inputs** and never fabricates them — consistent
> with the chapter's own [Tip]: measure peak KV per active user first.

## When to Use

- Scaling a multi-model agent and deciding how many concurrent incidents one GPU
  can host.
- Choosing between weight quantization and KV compression to raise concurrency.
- Estimating whether GPU-accelerated graph analytics fit the latency budget.
- Setting an end-to-end latency target for a multi-step workflow.

Phrases that should invoke this skill: "how many concurrent users per GPU", "KV
cache bound", "peak KV per user", "MEMENTO", "latency budget", "cuGraph speedup",
"is this pipeline fast enough".

## When NOT to Use

- **Model selection / routing** — that is `model-routing-selector` (Ch8).
- **Cost per successful completion** — that is `cost-performance-scorer` (Ch8).
- **Defining GPU terms** (VRAM, tensor core, quantization) — that is the
  `gpu-glossary-anchor` skill.
- **When peak KV is unmeasured.** The concurrency math needs a measured peak KV
  per active user. Measure it on a representative reasoning-heavy workload first;
  do not guess.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | GPU GB, weights GB, peak KV GB | `lib.kv_bound_concurrency(...)` | Concurrent users | Bound by KV, not weights |
| 2 | Same + factors | `lib.weight_quant_vs_kv_compression(...)` | Concurrency gain comparison | KV compression out-gains weight quant when KV dominates |
| 3 | (design) | `lib.memento_note()` | MEMENTO recipe + measure-first tip | Reduction factor marked caller-measured, not fabricated |
| 4 | CPU seconds + algo | `lib.estimate_gpu_time(s, algo)` | GPU wall-clock estimate | Uses the published speedup |
| 5 | (design) | `lib.LATENCY_BUDGET` | Component budget + targets | Ranges match the book (5-50 / 50-200 / 500-2000 ms) |
| 6 | SLM calls, graph ops, parallelism | `lib.budget_pipeline(...)` | End-to-end estimate vs 2s target | within_2s_target true for the DevOps pipeline |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|-----------------------|---------------------|
| "Use a smaller model to fit more concurrent users." | Model size is not the ceiling — peak KV per active user is. An 80 GB GPU hosts a small number of concurrent reasoning-heavy users regardless of how small the model is (Ch8). |
| "Quantize the weights to raise concurrency." | Quantizing weights frees a little memory but does not move the KV ceiling. Bounding the cache (MEMENTO) multiplies concurrency; the comparison in this skill shows the KV gain dominating the weight-quant gain. |
| "KV compression always helps, turn it on." | Not if peak KV is already small (short prompts, no reasoning traces) — then multi-LoRA dominates and KV compression is secondary. The chapter's tip is to MEASURE peak KV first and optimize the binding constraint. |
| "GPU acceleration is fast, load the graph per query." | Cold-start data transfer to GPU memory can take seconds for large graphs, negating the speedup. Keep a warm GPU-resident copy of the hot subgraphs (Ch8 pitfall). |
| "Optimize per-call latency." | The user perceives the whole workflow. The meaningful target is end-to-end task completion time, not per-call latency (Ch8 Latency Budgets). |

## Red Flags

- **Concurrency computed from model size instead of peak KV.** The binding
  constraint is misidentified; the estimate will be wildly optimistic.
- **A fabricated MEMENTO reduction factor.** The source redacts it; any hardcoded
  multiple is invented. Mark it measured.
- **Pipeline estimate ignores parallelism.** Independent DAG nodes run
  concurrently; a purely sequential estimate overstates latency.
- **cuGraph speedup applied to a Cypher traversal.** No major graph DB runs
  Cypher/Gremlin traversal on GPU; only analytics (PageRank, centrality) via
  cuGraph. The traversal query engine stays CPU-bound.
- **CLI `--help` exits non-zero.** SKILL.md / CLI mismatch.

## Non-Negotiable Verification

Before trusting a capacity or latency estimate from this skill:

1. **Run the benchmark battery.**
   ```
   python cli.py benchmark
   ```
   Confirms KV bounds concurrency (not model size), KV compression out-gains
   weight quantization, the MEMENTO factor is caller-measured, the cuGraph
   speedups match the book, and the 5-call pipeline lands within 2 seconds.

2. **Prove the KV-vs-weights claim on your numbers.**
   ```
   python cli.py kv-compress --gpu 80 --weights 16 --peak-kv 8 --kv-factor 2
   ```
   Confirm `verdict` is `kv_compression` and the KV gain exceeds the weight-quant
   gain.

3. **Measure peak KV before optimizing.**
   ```
   python cli.py memento
   ```
   Read the tip; run your representative reasoning-heavy workload and measure
   peak KV per active user before choosing multi-LoRA vs KV compression.

4. **Domain test in the notebook.** Run `notebooks/ch8-optimization.ipynb`;
   confirm the hardware-acceleration section estimates the blast-radius GPU
   speedup and checks the completed pipeline against the sub-2s budget using
   `moto`-mocked CloudWatch latency signals.

## Security Posture

- **Advisory calculator, no execution.** `lib.py` makes no network calls and
  runs no GPU code; it returns estimates the caller acts on.
- **Estimates are inputs, not guarantees.** The speedups are published figures
  for specific graphs/hardware; validate against your own workload before
  committing an SLO. A latency SLO backed by an un-measured estimate is an
  optimistic guess, not a design.
- **Do not fabricate the redacted factors.** Treat `peak_kv_reduction_factor`
  and `per_block_compression_factor` as measured on your workload; a hardcoded
  value is a fabricated capacity claim that fails silently at production load.

## Composition

- **Follows** `model-routing-selector` (Ch8): routing lowers cost per weight;
  this budgeter checks the resulting fleet against the concurrency + latency
  ceiling. Together they cover cost AND latency.
- **Pairs with** `cost-performance-scorer`: cost/quality on one axis, latency/
  concurrency on the other; both gate a production routing change.
- **Composes with** the `gpu-glossary-anchor` skill for term definitions and with
  the vLLM multi-LoRA serving pattern (Example 8-12).

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, AnthonyAlcaraz / forthcoming),
Chapter 8 — Optimization, "Hardware Acceleration". Key references:

- cuGraph / nx-cugraph speedups (PageRank 137x, Louvain 125x, multi-GPU 80x,
  betweenness 485x on LiveJournal 4.8M/69M; blast radius 3-5s -> <100ms)
- vLLM continuous batching + multi-LoRA (Example 8-12; 50-80ms TTFT, 100 users)
- Cerebras Inference (1,800 tok/s, 20x; 22s -> 1.5s; 75x Artificial-Analysis-
  verified) and SambaNova SN50 RDU (millisecond hot-swap)
- MEMENTO (Microsoft) — two-stage SFT on 228,000 traces; block-summary KV bound
- Latency budget framework (5-50 / 50-200 / 500-2000 ms; sub-100ms / sub-30ms)
