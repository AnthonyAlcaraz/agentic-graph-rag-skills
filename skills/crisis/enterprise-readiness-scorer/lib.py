"""
Enterprise agentic-readiness scorer (Agentic GraphRAG, Ch1 — The Crisis).

Scores a proposed or deployed enterprise agent against the architectural
requirements Ch1 argues are non-negotiable: the absence of the five fatal
flaws of naive vector RAG, the three agency dimensions, the four agent
capabilities, and the decision-trace test for enterprise context.

Pure Python, no external deps. The retrieval-substrate probe is a stub
that swaps in a real graph/vector inspector at a documented seam.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


# The five fatal flaws of a naive vector-based approach (Ch1, The Crisis).
# Each flaw is "cured" only when the corresponding graph capability is present.
FIVE_FATAL_FLAWS: Dict[str, str] = {
    "context_amnesia": "Every conversation starts from scratch; no memory across interactions.",
    "relationship_blindness": "Information sits in silos; entities seen but not how they connect.",
    "temporal_ignorance": "Static embeddings treat outdated config as current truth.",
    "reasoning_paralysis": "Vector search finds similar text, not logical/causal connections.",
    "tool_chaos": "No understanding of tool relationships; agent guesses which API to call.",
}

# The graph capability that cures each flaw (Ch1, The Crisis).
FLAW_CURE: Dict[str, str] = {
    "context_amnesia": "evolving_memory",
    "relationship_blindness": "entity_relationships",
    "temporal_ignorance": "temporal_evolution",
    "reasoning_paralysis": "multi_hop_reasoning",
    "tool_chaos": "tool_orchestration",
}

# Three dimensions of agency (Ch1, Defining Agency). Sliding scales, not binary.
AGENCY_DIMENSIONS: Dict[str, str] = {
    "autonomy": "Degree of independent decisions without external direction.",
    "action": "Ability to execute decisions that affect the environment.",
    "authority": "Scope and limits of permitted actions.",
}

# Four capabilities that emerge across the three dimensions (Ch1, Defining Agency).
AGENT_CAPABILITIES: Dict[str, str] = {
    "autonomous_decision_making": "Navigates complexity without step-by-step guidance.",
    "contextual_understanding": "Aware of relationships, temporal and org structure.",
    "strategic_tool_utilization": "Knows when and why to use a tool, not just access.",
    "memory_persistence": "Short-term in-session and long-term cross-session memory.",
}

WEIGHTS = {
    "flaws_cured": 40,        # the architectural crisis Ch1 is named for
    "agency": 20,            # autonomy / action / authority calibrated
    "capabilities": 25,      # the four emergent capabilities
    "decision_trace": 15,    # enterprise context-graph test (Ch1, The Context Graph)
}

BANDS = [
    (85, "PRODUCTION-READY", "Graph-grade architecture; cures the five fatal flaws."),
    (60, "PILOT-READY", "Sound foundation; close the flagged gaps before scaling."),
    (35, "PROTOTYPE", "Works for local lookups; will fail on enterprise complexity."),
    (0, "NAIVE-VECTOR", "Architectural failure preventing truly agentic behavior."),
]


def score_flaws(graph_capabilities: Dict[str, bool]) -> Tuple[float, List[str], List[str]]:
    """A flaw is cured iff its curing graph capability is present.

    graph_capabilities: {capability_name: present?} for the FLAW_CURE values.
    Returns (points_0_to_WEIGHTS['flaws_cured'], cured_flaws, open_flaws).
    """
    cured, open_flaws = [], []
    for flaw, cure in FLAW_CURE.items():
        if graph_capabilities.get(cure, False):
            cured.append(flaw)
        else:
            open_flaws.append(flaw)
    pts = WEIGHTS["flaws_cured"] * len(cured) / len(FLAW_CURE)
    return pts, cured, open_flaws


def score_agency(agency: Dict[str, float]) -> Tuple[float, List[str]]:
    """Agency dimensions are 0.0-1.0 sliding scales (Ch1: not binary).

    A dimension is 'calibrated' if it is explicitly set (any value), because
    Ch1's point is calibration, not maximization: a real-estate agent has
    high autonomy but deliberately low pricing authority. We score coverage
    (was each dimension consciously calibrated) not magnitude.
    """
    missing = [d for d in AGENCY_DIMENSIONS if d not in agency]
    covered = len(AGENCY_DIMENSIONS) - len(missing)
    pts = WEIGHTS["agency"] * covered / len(AGENCY_DIMENSIONS)
    return pts, missing


def score_capabilities(capabilities: Dict[str, bool]) -> Tuple[float, List[str]]:
    """Four emergent capabilities (Ch1, Defining Agency)."""
    missing = [c for c in AGENT_CAPABILITIES if not capabilities.get(c, False)]
    present = len(AGENT_CAPABILITIES) - len(missing)
    pts = WEIGHTS["capabilities"] * present / len(AGENT_CAPABILITIES)
    return pts, missing


def decision_trace_test(captures_rejected_alternatives: bool) -> Tuple[float, str]:
    """Marple's test (Ch1, The Context Graph): can the system tell you not just what
    happened, but what alternatives were considered and rejected?

    This is the single discriminating test between a relabeled search index
    and a real enterprise context graph.
    """
    if captures_rejected_alternatives:
        return WEIGHTS["decision_trace"], "Captures decision traces (commit-time context)."
    return 0.0, "Records final states only (read-time); no decision traces."


def band_for(score: float) -> Tuple[str, str]:
    for threshold, name, desc in BANDS:
        if score >= threshold:
            return name, desc
    return BANDS[-1][1], BANDS[-1][2]


def assess(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Full readiness assessment.

    profile keys:
      graph_capabilities: {entity_relationships, evolving_memory,
        temporal_evolution, multi_hop_reasoning, tool_orchestration: bool}
      agency: {autonomy, action, authority: float 0-1}  (presence = calibrated)
      capabilities: {autonomous_decision_making, contextual_understanding,
        strategic_tool_utilization, memory_persistence: bool}
      captures_rejected_alternatives: bool
    """
    flaw_pts, cured, open_flaws = score_flaws(profile.get("graph_capabilities", {}))
    agency_pts, agency_missing = score_agency(profile.get("agency", {}))
    cap_pts, cap_missing = score_capabilities(profile.get("capabilities", {}))
    trace_pts, trace_note = decision_trace_test(
        profile.get("captures_rejected_alternatives", False)
    )
    total = round(flaw_pts + agency_pts + cap_pts + trace_pts, 1)
    band, band_desc = band_for(total)

    # Open flaws dominate (Ch1: the five fatal flaws ARE the architectural
    # failure). An agent with every flaw still open is naive-vector by
    # definition, regardless of how high its agency/capability/trace
    # self-reports push the numeric score. This enforces the SKILL.md
    # Red Flag: "All five flaws open but band is not NAIVE-VECTOR" is a bug.
    if len(open_flaws) == len(FLAW_CURE):
        band, band_desc = BANDS[-1][1], BANDS[-1][2]

    recommendations: List[str] = []
    for flaw in open_flaws:
        recommendations.append(
            f"OPEN FLAW [{flaw}]: {FIVE_FATAL_FLAWS[flaw]} "
            f"-> add graph capability '{FLAW_CURE[flaw]}'."
        )
    for dim in agency_missing:
        recommendations.append(
            f"UNCALIBRATED AGENCY [{dim}]: {AGENCY_DIMENSIONS[dim]}"
        )
    for cap in cap_missing:
        recommendations.append(
            f"MISSING CAPABILITY [{cap}]: {AGENT_CAPABILITIES[cap]}"
        )
    if trace_pts == 0:
        recommendations.append("NO DECISION TRACE: " + trace_note)

    return {
        "score": total,
        "band": band,
        "band_description": band_desc,
        "breakdown": {
            "flaws_cured": round(flaw_pts, 1),
            "agency": round(agency_pts, 1),
            "capabilities": round(cap_pts, 1),
            "decision_trace": round(trace_pts, 1),
        },
        "cured_flaws": cured,
        "open_flaws": open_flaws,
        "decision_trace_note": trace_note,
        "recommendations": recommendations,
    }


# TODO: production — replace the boolean self-report with an automated probe
# that inspects the actual retrieval substrate (graph DB schema for relationship
# types, temporal-edge presence, tool-dependency edges) instead of trusting the
# operator's claimed capabilities.
