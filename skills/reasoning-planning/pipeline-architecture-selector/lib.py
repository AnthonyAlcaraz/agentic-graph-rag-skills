"""
Pipeline architecture selector (Ch5 — Hybrid Architectures).

Treats pipeline selection as a routing decision inside a meta-pipeline
(Examples 5-10, 5-11). A single analysis pass over task characteristics
(complexity + uncertainty) picks sequential / tree / loop, then a
resource-aware wrapper degrades gracefully when memory or time budgets bite.

Pure Python, stdlib only. The complexity/uncertainty estimators are
heuristic stand-ins.

Production swap: replace `assess_task_complexity` / `estimate_uncertainty`
with a single LLM classification call (the chapter notes the analysis "typically
completes in a single LLM call"). The signatures here are the seam.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

# Thresholds from Example 5-10. Tunable per domain.
SIMPLE_THRESHOLD = 0.40
LOW_UNCERTAINTY = 0.35
HIGH_UNCERTAINTY = 0.65

# Resource floors from Example 5-11.
TREE_MEMORY_THRESHOLD = 512        # MB needed before a tree fan-out is safe
ITERATION_TIME_MINIMUM = 30.0      # seconds needed for at least one refine loop

ARCHITECTURES = ("sequential", "tree", "loop")
FALLBACKS = ("sequential_fallback", "single_pass_best_effort")


@dataclass
class RouteDecision:
    architecture: str          # ideal architecture before constraints
    final: str                 # after resource-aware degradation
    complexity: float
    uncertainty: float
    degraded: bool
    reason: str


def assess_task_complexity(query: str) -> float:
    """Heuristic 0..1 complexity. Production: single LLM classification call.

    Proxies: token length, count of conjunctions/dependencies, multi-entity
    mentions. A latency investigation touching several services scores high.
    """
    tokens = query.split()
    length_signal = min(len(tokens) / 40.0, 1.0)
    conj = sum(query.lower().count(w) for w in (" and ", " then ", " after ", " across ", " between "))
    dep_signal = min(conj / 4.0, 1.0)
    return round(min(0.5 * length_signal + 0.5 * dep_signal, 1.0), 4)


def estimate_uncertainty(query: str) -> float:
    """Heuristic 0..1 answer uncertainty. Production: LLM self-estimate.

    Proxies: presence of hedging / open-ended markers ("why", "investigate",
    "root cause", "could", "unknown"). A known-cause lookup scores low.
    """
    ql = query.lower()
    markers = ("why", "investigate", "root cause", "unclear", "could", "unknown",
               "diagnose", "spike", "anomaly", "intermittent")
    hits = sum(1 for m in markers if m in ql)
    return round(min(hits / 4.0, 1.0), 4)


def analyze_and_route(complexity: float, uncertainty: float) -> str:
    """Example 5-10 routing. Simple+certain -> sequential; high-uncertainty ->
    tree (explore hypotheses); else loop (iterative refinement)."""
    if complexity < SIMPLE_THRESHOLD and uncertainty < LOW_UNCERTAINTY:
        return "sequential"
    if uncertainty > HIGH_UNCERTAINTY:
        return "tree"
    return "loop"


def route_with_constraints(
    complexity: float,
    uncertainty: float,
    available_memory_mb: float = float("inf"),
    remaining_budget_s: float = float("inf"),
) -> RouteDecision:
    """Example 5-11. Wrap ideal selection with runtime constraint checks.

    Build the fallback paths explicitly rather than relying on exception
    handling — graceful degradation is a feature, not an error case.
    """
    ideal = analyze_and_route(complexity, uncertainty)
    final = ideal
    degraded = False
    reason = "ideal path available"

    if ideal == "tree" and available_memory_mb < TREE_MEMORY_THRESHOLD:
        final = "sequential_fallback"
        degraded = True
        reason = (f"tree needs >= {TREE_MEMORY_THRESHOLD}MB, "
                  f"only {available_memory_mb}MB free -> sequential_fallback")
    elif ideal == "loop" and remaining_budget_s < ITERATION_TIME_MINIMUM:
        final = "single_pass_best_effort"
        degraded = True
        reason = (f"loop needs >= {ITERATION_TIME_MINIMUM}s for one iteration, "
                  f"only {remaining_budget_s}s left -> single_pass_best_effort")

    return RouteDecision(
        architecture=ideal,
        final=final,
        complexity=complexity,
        uncertainty=uncertainty,
        degraded=degraded,
        reason=reason,
    )


def route_query(
    query: str,
    available_memory_mb: float = float("inf"),
    remaining_budget_s: float = float("inf"),
    complexity_fn: Optional[Callable[[str], float]] = None,
    uncertainty_fn: Optional[Callable[[str], float]] = None,
) -> RouteDecision:
    """End-to-end: estimate characteristics, then route under constraints."""
    cfn = complexity_fn or assess_task_complexity
    ufn = uncertainty_fn or estimate_uncertainty
    return route_with_constraints(
        cfn(query), ufn(query), available_memory_mb, remaining_budget_s
    )


def estimate_latency(
    architecture: str,
    node_seconds: list,
    merge_seconds: float = 0.0,
    retry_probability: float = 0.0,
    max_iterations: int = 1,
) -> dict:
    """End-to-end latency estimate per architecture, with the bottleneck named.

    sequential: sum of node times (single-responsibility nodes in a chain).
    tree: parallel fan-out -- max branch time + the merge/reconcile cost
      (`node_seconds` is per-branch duration here).
    loop: one pass costs sum(node_seconds); the expected number of passes with
      per-pass retry probability p, bounded by the retry budget n, is the
      truncated geometric expectation E = (1 - p^n) / (1 - p). The bound is
      the same explicit loop cap the loop-pipeline-router enforces.
    """
    if architecture not in ARCHITECTURES:
        raise ValueError(f"unknown architecture {architecture!r}; expected one of {ARCHITECTURES}")
    if not node_seconds or any(s < 0 for s in node_seconds):
        raise ValueError("node_seconds must be non-empty and non-negative")
    if not (0.0 <= retry_probability < 1.0):
        raise ValueError("retry_probability must be in [0, 1)")
    if max_iterations < 1:
        raise ValueError("max_iterations must be >= 1")

    bottleneck = max(range(len(node_seconds)), key=lambda i: node_seconds[i])
    if architecture == "sequential":
        total = sum(node_seconds)
        detail = "sum of chained nodes"
    elif architecture == "tree":
        total = max(node_seconds) + merge_seconds
        detail = "slowest parallel branch + merge"
    else:  # loop
        p, n = retry_probability, max_iterations
        expected_passes = (1 - p ** n) / (1 - p) if p else 1.0
        total = sum(node_seconds) * expected_passes
        detail = (f"per-pass cost x E[passes]={expected_passes:.2f} "
                  f"(truncated geometric, p={p}, cap={n})")

    return {
        "architecture": architecture,
        "expected_seconds": round(total, 3),
        "bottleneck_index": bottleneck,
        "bottleneck_seconds": node_seconds[bottleneck],
        "detail": detail,
    }
