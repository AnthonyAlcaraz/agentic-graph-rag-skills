"""
Agent-constraint-triangle scorer (Agentic Graph RAG, Ch1 — The Agent
Constraint Triangle).

Ch1 names three interconnected constraints that create "an inherently
difficult operational problem":

  * complexity management  — multistep planning and reasoning; cognitive
    load "increases exponentially" with step count, producing "compounding
    errors as the step count increases".
  * tool orchestration     — translating natural language into precisely
    structured API calls; the failure mode is "bloated tool sets that cover
    too much functionality or lead to ambiguous decision points". Anthropic's
    principle: "If a human engineer can't definitively say which tool should
    be used in a given situation, an AI agent can't be expected to do better."
  * context utilization    — organizing a fixed context window (the "model's
    attention budget"). Chroma's needle-in-a-haystack research names *context
    rot*: as tokens increase, recall decreases — "a performance gradient",
    not "a hard cliff".

The three do not exist in isolation; improving one applies pressure to the
others, forming three cyclic trade-offs (Ch1):

  * complexity -> tools -> context
  * tools -> context -> complexity
  * context -> complexity -> tools

The governing principle Ch1 states is "the smallest possible set of
high-signal tokens that maximizes the likelihood of some desired outcome":
minimal-but-sufficient complexity decomposition, minimal-but-complete tool
coverage, and minimal-but-adequate context retention.

This module scores an agent configuration against that triangle. The scoring
curves below are transparent HEURISTICS that embody the chapter's qualitative
claims (exponential complexity load, ambiguity-dominated tool pressure,
context-rot gradient). They are NOT chapter-cited benchmarks; the production
seam is documented at each function.

Pure Python, stdlib only.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

# The three constraints, in the chapter's order.
CONSTRAINTS = ("complexity_management", "tool_orchestration", "context_utilization")

# Pressure bands applied to each 0-100 sub-score.
_BANDS = (
    (0, 40, "manageable"),
    (40, 60, "elevated"),
    (60, 85, "high"),
    (85, 101, "critical"),
)


def _band(pressure: float) -> str:
    for lo, hi, name in _BANDS:
        if lo <= pressure < hi:
            return name
    return "critical"


def score_complexity(avg_task_steps: int) -> float:
    """Complexity-management pressure from reasoning-chain length.

    Ch1: "As tasks require more steps and deeper analysis, cognitive load
    increases exponentially ... resulting in compounding errors as the step
    count increases." Modeled as a saturating exponential in step count.

    TODO(production): replace the fixed curve with an empirical
    error-rate-vs-steps measurement from your own eval harness; the contract
    (int steps -> float 0-100 pressure, monotincreasing) is the seam.
    """
    steps = max(0, int(avg_task_steps))
    return round(100.0 * (1.0 - math.exp(-0.15 * steps)), 1)


def score_tool_orchestration(tool_count: int, tools_disambiguable: bool) -> float:
    """Tool-orchestration pressure from catalog size and ambiguity.

    Ch1 / Anthropic: the dominant failure is ambiguity ("if a human engineer
    can't definitively say which tool should be used ..."), amplified by
    bloated tool sets. Catalog size sets a base pressure; non-disambiguable
    tool sets are penalised because ambiguity is the primary failure, while a
    cleanly disambiguable set relieves it.

    TODO(production): derive the ambiguity signal from a real selection-accuracy
    eval over your registry rather than a boolean; the contract is the seam.
    """
    count = max(0, int(tool_count))
    base = 100.0 * (1.0 - math.exp(-0.02 * count))
    if tools_disambiguable:
        pressure = base * 0.6
    else:
        pressure = min(100.0, base + 40.0)
    return round(pressure, 1)


def score_context_utilization(context_window_tokens: int, avg_context_tokens_used: int) -> float:
    """Context-utilization pressure from fill ratio (context-rot gradient).

    Ch1 / Chroma: "as the number of tokens in the context window increases,
    the model's ability to accurately recall information from that context
    decreases ... a performance gradient." Modeled as a monotonic function of
    the fill ratio (used / budget), clamped at full.

    TODO(production): replace with a measured recall-vs-fill curve for your
    specific model; the contract (fill ratio -> 0-100 pressure) is the seam.
    """
    window = max(1, int(context_window_tokens))
    used = max(0, int(avg_context_tokens_used))
    ratio = min(1.0, used / window)
    pressure = 100.0 * (ratio ** 0.7)
    return round(pressure, 1)


# The three cyclic trade-offs (Ch1). Each fires when its SOURCE constraint is
# under high pressure — raising that constraint pushes pressure around the
# cycle onto the next two.
_PRESSURE_CYCLES = {
    "complexity_management": {
        "edge": "complexity -> tools -> context",
        "cascade": (
            "As task complexity increases, more specialized tools become "
            "necessary; each tool consumes context for its definition, "
            "increases tool-selection load, and adds ambiguity."
        ),
    },
    "tool_orchestration": {
        "edge": "tools -> context -> complexity",
        "cascade": (
            "Expanding the tool set depletes context available for actual "
            "task reasoning, forcing aggressive context management (risking "
            "information loss) or simplified task decomposition (limiting "
            "capability)."
        ),
    },
    "context_utilization": {
        "edge": "context -> complexity -> tools",
        "cascade": (
            "Aggressive context optimization (compaction, selective "
            "retrieval) can discard subtle context whose importance surfaces "
            "later, forcing incomplete-information operation or more tool "
            "calls to reconstruct it."
        ),
    },
}

# Minimal-but-sufficient recommendation per constraint (Ch1's governing
# principle: the smallest set of high-signal tokens that still succeeds).
_MINIMAL_RECOMMENDATION = {
    "complexity_management": (
        "minimal-but-sufficient complexity decomposition: split the task into "
        "the fewest independently verifiable sub-steps, not the most granular."
    ),
    "tool_orchestration": (
        "minimal-but-complete tool coverage: filter the registry to the "
        "high-signal tools for the query (RAG-MCP style) and rewrite "
        "descriptions until a human could disambiguate them."
    ),
    "context_utilization": (
        "minimal-but-adequate context retention: retrieve selectively, but "
        "beware the context -> complexity -> tools cycle — discarding subtle "
        "context forces reconstruction later."
    ),
}


def _overall_band(sub: Dict[str, float]) -> str:
    vals = list(sub.values())
    if any(v >= 85 for v in vals) or all(v > 60 for v in vals):
        return "OVERCONSTRAINED"
    if any(v > 60 for v in vals):
        return "STRESSED"
    return "BALANCED"


def score(config: Dict[str, Any]) -> Dict[str, Any]:
    """Score one agent configuration against the constraint triangle.

    Expected config keys:
      avg_task_steps          int   reasoning-chain length per task
      tool_count              int   tools exposed to the agent
      tools_disambiguable     bool  can a human definitively pick the tool?
      context_window_tokens   int   attention budget
      avg_context_tokens_used int   tokens the task typically consumes

    Returns per-constraint pressure (0-100) + band, the active pressure
    cycles (Ch1's three trade-offs), an overall band, and the
    minimal-but-sufficient recommendation for each high constraint.
    """
    complexity = score_complexity(config.get("avg_task_steps", 0))
    tools = score_tool_orchestration(
        config.get("tool_count", 0), bool(config.get("tools_disambiguable", True))
    )
    context = score_context_utilization(
        config.get("context_window_tokens", 1),
        config.get("avg_context_tokens_used", 0),
    )
    sub = {
        "complexity_management": complexity,
        "tool_orchestration": tools,
        "context_utilization": context,
    }

    active_cycles = []
    recommendations = []
    for name, pressure in sub.items():
        if pressure > 60:
            cyc = _PRESSURE_CYCLES[name]
            active_cycles.append(
                {"source": name, "edge": cyc["edge"], "cascade": cyc["cascade"]}
            )
            recommendations.append(
                {"constraint": name, "action": _MINIMAL_RECOMMENDATION[name]}
            )

    overall = _overall_band(sub)
    fill_ratio = min(
        1.0,
        max(0, config.get("avg_context_tokens_used", 0))
        / max(1, config.get("context_window_tokens", 1)),
    )
    return {
        "config": config,
        "pressures": {
            name: {"pressure": val, "band": _band(val)} for name, val in sub.items()
        },
        "dominant_constraint": max(sub, key=sub.get),
        "overall_band": overall,
        "active_pressure_cycles": active_cycles,
        "recommendations": recommendations,
        "context_fill_ratio": round(fill_ratio, 3),
        "principle": (
            "Ch1: the smallest possible set of high-signal tokens that "
            "maximizes the likelihood of the desired outcome — minimal but "
            "sufficient across all three constraints."
        ),
    }


def score_batch(configs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Score several agent configurations and rank them by overall pressure."""
    results = [score(c) for c in configs]
    ranked = sorted(
        results,
        key=lambda r: max(p["pressure"] for p in r["pressures"].values()),
        reverse=True,
    )
    return {
        "results": results,
        "most_constrained": ranked[0]["config"].get("name", ranked[0]["config"])
        if ranked
        else None,
        "order": [r["config"].get("name", "unnamed") for r in ranked],
    }
