"""
KV-cache-bound concurrency and end-to-end latency budgeting for a specialist
model fleet + GPU-accelerated graph analytics — distilled from Agentic Graph RAG
(O'Reilly), Chapter 8 — Optimization, "Hardware Acceleration".

The architecture distributes work across two channels: graph traversals that
navigate the knowledge graph and model-inference calls that power the workflow
nodes. Both bottleneck at production scale.

Graph analytics (PageRank, community detection, centrality) are bound by memory
bandwidth, not compute — irregular random access that CPUs handle poorly and
GPUs (cuGraph / nx-cugraph) handle well. Published speedups span 80x-485x.

Inference latency is bound by the KV cache. Multi-LoRA serving lowers cost per
weight but not the binding constraint: PEAK KV PER ACTIVE USER, not model size,
sets how many concurrent analyses one H100 (80 GB) can host. Quantizing the
weights does not move this ceiling — you have to bound the cache itself. The
chapter's first production-ready recipe is Microsoft MEMENTO: a two-stage
supervised fine-tune on 228,000 traces teaches the model to segment its chain of
thought into blocks, emit a compressed summary token per block, and mask the
original block from future attention. The KV cache follows a sawtooth: it grows
while a block is open, compresses on summary, then starts fresh.

IMPORTANT — the chapter's source redacts the exact MEMENTO reduction factor, the
per-block compression factor, and the concurrent-incident multiplier. This
module therefore treats those as CALLER-MEASURED inputs (see the [Tip]: measure
peak KV per active user on a representative reasoning-heavy workload first). It
never fabricates them.

Pure Python, stdlib only.
"""

from __future__ import annotations

from typing import Any


# --- KV-cache-bound concurrency ---------------------------------------------
H100_MEMORY_GB = 80.0  # the chapter's reference accelerator


def kv_bound_concurrency(gpu_memory_gb: float, model_weights_gb: float,
                         peak_kv_per_user_gb: float, overhead_gb: float = 2.0) -> int:
    """How many concurrent users a GPU can host, bound by peak KV per user.

    available_for_kv = gpu_memory - weights - overhead
    concurrency = floor(available_for_kv / peak_kv_per_user)

    This is the chapter's core claim made concrete: with a large per-user KV
    footprint, an 80 GB GPU hosts a small number of concurrent users regardless
    of how small the model is.
    """
    available = gpu_memory_gb - model_weights_gb - overhead_gb
    if available <= 0 or peak_kv_per_user_gb <= 0:
        return 0
    return int(available // peak_kv_per_user_gb)


def weight_quant_vs_kv_compression(
    gpu_memory_gb: float, model_weights_gb: float, peak_kv_per_user_gb: float,
    weight_quant_factor: float = 2.0, kv_compression_factor: float = 2.0,
    overhead_gb: float = 2.0,
) -> dict[str, Any]:
    """Demonstrate the chapter's claim: quantizing weights does NOT move the
    concurrency ceiling; bounding the KV cache does.

    weight_quant_factor: divide model weights by this (e.g. fp16 -> int8 ~= 2).
    kv_compression_factor: divide peak KV per user by this (e.g. MEMENTO); the
        book redacts the empirical factor, so the caller supplies a measured one.
    """
    base = kv_bound_concurrency(gpu_memory_gb, model_weights_gb, peak_kv_per_user_gb, overhead_gb)
    quantized = kv_bound_concurrency(gpu_memory_gb, model_weights_gb / weight_quant_factor,
                                     peak_kv_per_user_gb, overhead_gb)
    kv_compressed = kv_bound_concurrency(gpu_memory_gb, model_weights_gb,
                                         peak_kv_per_user_gb / kv_compression_factor, overhead_gb)
    return {
        "baseline_concurrency": base,
        "after_weight_quant": quantized,
        "after_kv_compression": kv_compressed,
        "weight_quant_gain": quantized - base,
        "kv_compression_gain": kv_compressed - base,
        "verdict": "kv_compression" if (kv_compressed - base) > (quantized - base) else "weight_quant",
        "lesson": "Peak KV per active user, not model size, is the binding "
                  "concurrency constraint (Ch8). Quantizing weights frees a "
                  "little memory; bounding the cache multiplies concurrency.",
    }


def memento_note() -> dict[str, Any]:
    """The MEMENTO recipe (Ch8). Exact reduction/compression factors are redacted
    in the source and must be measured on your workload."""
    return {
        "recipe": "MEMENTO (Microsoft) — first production-ready KV-bounding recipe",
        "training": "two-stage supervised fine-tune on 228,000 reasoning traces",
        "mechanism": "segment chain-of-thought into blocks; emit one compressed "
                     "summary token (the memento) per block; mask the original "
                     "block from future attention",
        "kv_pattern": "sawtooth — grows while a block is open, compresses on "
                      "summary, starts fresh for the next block",
        "peak_kv_reduction_factor": "measured (redacted in source)",
        "per_block_compression_factor": "measured (redacted in source)",
        "tip": "Measure peak KV per active user on a representative "
               "reasoning-heavy workload BEFORE optimizing. If it is small "
               "(short prompts, no reasoning traces), multi-LoRA dominates and "
               "KV compression is secondary. If it is large (causal attribution, "
               "multistep planning), KV compression is where the first gains live.",
    }


# --- GPU-accelerated graph analytics (cuGraph / nx-cugraph) ------------------
# Published speedups (Ch8): algorithm / baseline specific, order-of-magnitude.
CUGRAPH_SPEEDUPS: dict[str, dict[str, Any]] = {
    "pagerank": {"speedup": 137, "baseline": "CPU", "hardware": "A100"},
    "louvain": {"speedup": 125, "baseline": "NetworkX", "hardware": "GPU"},
    "pagerank_multi_gpu": {"speedup": 80, "baseline": "100-node Apache Spark", "hardware": "DGX-2"},
    "betweenness_centrality": {"speedup": 485, "baseline": "CPU (7 min -> 5 s)",
                               "hardware": "GPU", "graph": "LiveJournal 4.8M nodes / 69M edges"},
}


def estimate_gpu_time(cpu_seconds: float, algo: str) -> dict[str, Any]:
    """Estimate GPU wall-clock from a CPU baseline and the published speedup."""
    if algo not in CUGRAPH_SPEEDUPS:
        raise ValueError(f"unknown algo {algo}; known: {sorted(CUGRAPH_SPEEDUPS)}")
    s = CUGRAPH_SPEEDUPS[algo]["speedup"]
    gpu_seconds = cpu_seconds / s
    return {
        "algo": algo, "speedup": s, "cpu_seconds": cpu_seconds,
        "gpu_seconds": round(gpu_seconds, 4), "gpu_ms": round(gpu_seconds * 1000, 1),
    }


def blast_radius_report() -> dict[str, Any]:
    """The DevOps blast-radius figure (Example 8-14): full infrastructure graph
    dependency analysis, 3-5 s on CPU, under 100 ms with nx-cugraph on one GPU —
    the SRE sees the blast radius before finishing the alert."""
    return {
        "operation": "blast radius (PageRank over the infrastructure dependency graph)",
        "cpu_seconds": "3-5",
        "gpu_result_ms": "<100",
        "source": "Example 8-14 (empirical; not derived from the LiveJournal speedup)",
    }


# --- End-to-end latency budgets ---------------------------------------------
# Component ranges (Ch8 "Latency Budgets"), milliseconds unless noted.
LATENCY_BUDGET: dict[str, Any] = {
    "graph_traversal_ms": (5, 50),       # GPU acceleration on warm data
    "slm_inference_ms": (50, 200),       # optimized serving (vLLM or equivalent)
    "multistep_5_10_calls_ms": (500, 2000),  # with parallelization
    "e2e_specialized_hw": "single-digit seconds for 30+ model calls",
    "low_latency_target_ms": 100,        # industry sub-100ms
    "ultra_low_latency_target_ms": 30,   # industry sub-30ms
    "vllm_ttft_ms": (50, 80),            # vLLM, 100 concurrent users (Example 8-12)
}


def budget_pipeline(n_slm_calls: int, n_graph_ops: int = 1,
                    parallel_factor: float = 1.0) -> dict[str, Any]:
    """Estimate end-to-end latency for a workflow and check it against the
    book's full-pipeline target (< 2 s). parallel_factor > 1 models independent
    nodes running concurrently (the cheapest optimization: exploit the DAG)."""
    slm_lo, slm_hi = LATENCY_BUDGET["slm_inference_ms"]
    g_lo, g_hi = LATENCY_BUDGET["graph_traversal_ms"]
    seq_lo = n_slm_calls * slm_lo + n_graph_ops * g_lo
    seq_hi = n_slm_calls * slm_hi + n_graph_ops * g_hi
    pf = max(parallel_factor, 1.0)
    est_lo, est_hi = seq_lo / pf, seq_hi / pf
    return {
        "n_slm_calls": n_slm_calls,
        "n_graph_ops": n_graph_ops,
        "parallel_factor": pf,
        "estimated_ms": (round(est_lo, 1), round(est_hi, 1)),
        "within_2s_target": est_hi <= 2000,
        "note": "Meaningful target is end-to-end task completion time, not "
                "per-call latency, since the user perceives the full workflow.",
    }
