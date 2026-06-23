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
