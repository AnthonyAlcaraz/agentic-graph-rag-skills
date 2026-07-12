"""
Workflow-agent spectrum classifier (Agentic GraphRAG, Ch1 — Classifying
Agentic Systems).

Ch1 rejects the binary "is it an agent or not" framing. Following Andrew Ng
("systems can be agent-like to different degrees") and Anthropic's
workflow-vs-agent distinction, it positions systems on a CONTINUOUS SPECTRUM:

  * WORKFLOW end — "predefined execution paths: orchestrated sequences that
    follow explicit instructions." Reliable and deterministic, limited
    adaptability. Chapter examples: a FAQ generator, a fund-analysis app.
  * AGENT end — systems that "determine processes dynamically, providing
    flexibility at the cost of predictability." Chapter examples: coding
    agents, deep research agents.
  * BLENDED middle — "deterministic workflows with nondeterministic LLMs
    inserted at key points," humans in the loop at specific points. Chapter
    example: an investment firm's market-commentary report (retrieve /
    analyze / submit by LLM; compliance review + regulatory submission by
    humans).

The classification is grounded in the three dimensions of agency (Ch1),
which "exist on sliding scales, not as binary attributes":

  * AUTONOMY  — degree of independent decision-making without external
    direction.
  * ACTION    — ability to execute decisions that affect the environment.
    "Without this capability to effect change, you have an assistant or
    advisor, not an agent."
  * AUTHORITY — scope and limitations of permitted actions.

When a system operates across these dimensions, Ch1 says four capabilities
emerge: autonomous decision-making, contextual understanding, strategic tool
utilization, and memory persistence.

Pure Python, stdlib only. Numeric scoring is deterministic; the free-text
keyword classifier is a documented best-effort seam.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

AGENCY_DIMENSIONS = ("autonomy", "action", "authority")

# Below this action level the system is an assistant/advisor, not an agent,
# regardless of autonomy — Ch1: "Without this capability to effect change,
# you have an assistant or advisor, not an agent."
_ACTION_AGENT_THRESHOLD = 0.15

# Spectrum band cutoffs on the 0..1 position (0 = workflow, 1 = agent).
_WORKFLOW_MAX = 0.34
_AGENT_MIN = 0.67

SPECTRUM_EXAMPLES = {
    "workflow": ["FAQ generator", "fund-analysis application"],
    "blended": ["investment-firm market-commentary report (LLM + human-in-the-loop)"],
    "agent": ["coding agents", "deep research agents"],
}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def spectrum_position(autonomy: float, path_determinism: float) -> float:
    """Position on the workflow(0)..agent(1) spectrum.

    A system is agent-like to the degree it (a) makes independent decisions
    (autonomy) and (b) determines its process dynamically rather than
    following a predefined path (1 - path_determinism). Averaged, per Ch1's
    "continuous spectrum between workflows and agents."

    TODO(production): calibrate the weighting against a labeled corpus of your
    own systems; the contract (returns 0..1, higher = more agent-like) is the
    seam.
    """
    dynamic_process = 1.0 - _clamp01(path_determinism)
    return round(0.5 * _clamp01(autonomy) + 0.5 * dynamic_process, 3)


def _band(position: float) -> str:
    if position < _WORKFLOW_MAX:
        return "WORKFLOW"
    if position < _AGENT_MIN:
        return "BLENDED"
    return "AGENT"


def emergent_capabilities(
    autonomy: float, memory: bool, tool_use: bool, contextual: bool
) -> Dict[str, bool]:
    """The four capabilities Ch1 says emerge when a system operates across the
    agency dimensions. autonomous_decision_making is inferred from autonomy;
    the other three are supplied signals (they depend on architecture the
    three core dimensions do not fully determine)."""
    return {
        "autonomous_decision_making": _clamp01(autonomy) >= 0.5,
        "contextual_understanding": bool(contextual),
        "strategic_tool_utilization": bool(tool_use),
        "memory_persistence": bool(memory),
    }


def classify(
    autonomy: float,
    action: float,
    authority: float,
    path_determinism: float,
    memory: bool = False,
    tool_use: bool = False,
    contextual: bool = False,
    name: str = "system",
) -> Dict[str, Any]:
    """Place a system on the workflow-agent spectrum from its agency dimensions.

    All of autonomy / action / authority / path_determinism are 0..1 sliding
    scales. Returns the spectrum position + band, the agency-dimension
    readout, the true-agent test (action gate), and the four emergent
    capabilities.
    """
    a_ut = _clamp01(autonomy)
    a_ct = _clamp01(action)
    a_th = _clamp01(authority)
    det = _clamp01(path_determinism)

    position = spectrum_position(a_ut, det)
    band = _band(position)
    is_agent_by_action = a_ct >= _ACTION_AGENT_THRESHOLD

    notes: List[str] = []
    if not is_agent_by_action:
        notes.append(
            "Action below the agent threshold: this is an assistant/advisor, "
            "not an agent (Ch1) — it decides but cannot effect change."
        )
    if band == "BLENDED":
        notes.append(
            "Blended: deterministic workflow with nondeterministic LLM steps "
            "at key points — keep humans in the loop where judgment is required."
        )
    if a_th < 0.34 and a_ut >= 0.67:
        notes.append(
            "High autonomy under low authority: like a real-estate agent who "
            "can market freely but cannot set price — calibrate the boundary."
        )

    return {
        "name": name,
        "spectrum_position": position,
        "band": band,
        "agency_dimensions": {
            "autonomy": round(a_ut, 3),
            "action": round(a_ct, 3),
            "authority": round(a_th, 3),
        },
        "path_determinism": round(det, 3),
        "is_agent_by_action_test": is_agent_by_action,
        "emergent_capabilities": emergent_capabilities(a_ut, memory, tool_use, contextual),
        "examples_at_band": SPECTRUM_EXAMPLES[band.lower()],
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Best-effort free-text classifier. Maps descriptive language to approximate
# dimension values so a plain sentence can be placed on the spectrum. This is
# a convenience seam; the numeric classify() is the authoritative path.
# ---------------------------------------------------------------------------

_SIGNALS = {
    "autonomy": {
        "high": [r"\bautonomous", r"\bdetermines? (?:the )?(?:process|path|solution)",
                 r"\bdecides? (?:on its own|independently)", r"\bwithout (?:human|step-by-step)",
                 r"\bscamper", r"\bself-direct"],
        "low": [r"\bpredefined", r"\bscripted", r"\bexplicit instructions",
                r"\bfixed (?:path|sequence)", r"\bfollows? (?:a )?(?:runbook|template|workflow)",
                r"\bstep-by-step"],
    },
    "action": {
        "high": [r"\bexecutes?", r"\btakes? actions?", r"\bplaces? (?:an )?order",
                 r"\bsubmits?", r"\bsends?", r"\bmodif(?:y|ies)", r"\bremediat", r"\brolls? back",
                 r"\bwrites?"],
        "low": [r"\brecommends? only", r"\bsuggests? only", r"\badvisor", r"\bassistant",
                r"\bread-only", r"\breports? back", r"\banswers? (?:questions|queries)"],
    },
    "authority": {
        "high": [r"\bfull authority", r"\bunrestricted", r"\bany (?:action|resource)",
                 r"\bproduction (?:write|change)"],
        "low": [r"\bapproval", r"\bhuman(?:s)? (?:must|in the loop)", r"\bcompliance review",
                r"\brestricted", r"\bcannot", r"\blimited (?:scope|permission)", r"\bboundaries?"],
    },
    "determinism": {
        "high": [r"\bdeterministic", r"\bpredefined", r"\borchestrated sequence",
                 r"\bfixed transitions", r"\bexplicit path", r"\bworkflow"],
        "low": [r"\bdynamic", r"\bnondeterministic", r"\badapts?", r"\bnovel situations?",
                r"\bconditional", r"\bflexib"],
    },
}


def _score_axis(text: str, spec: Dict[str, List[str]], default: float = 0.5) -> float:
    high = sum(1 for p in spec["high"] if re.search(p, text, re.IGNORECASE))
    low = sum(1 for p in spec["low"] if re.search(p, text, re.IGNORECASE))
    if high == 0 and low == 0:
        return default
    # Map (high - low) net signal into 0..1 around the 0.5 midpoint.
    net = high - low
    return _clamp01(0.5 + 0.2 * net)


def classify_text(description: str, name: str = "system") -> Dict[str, Any]:
    """Best-effort spectrum placement from a free-text system description.

    Estimates each agency dimension by keyword signal, then runs classify().
    The estimated dimensions are returned under `estimated_dimensions` so the
    caller can see (and correct) the inference.

    TODO(production): swap the keyword scorer for an LLM that reads the
    description and emits the four 0..1 dimension values; keep this signature.
    """
    autonomy = _score_axis(description, _SIGNALS["autonomy"])
    action = _score_axis(description, _SIGNALS["action"])
    authority = _score_axis(description, _SIGNALS["authority"])
    determinism = _score_axis(description, _SIGNALS["determinism"])
    result = classify(autonomy, action, authority, determinism, name=name)
    result["estimated_dimensions"] = {
        "autonomy": autonomy,
        "action": action,
        "authority": authority,
        "path_determinism": determinism,
    }
    result["source_text"] = description
    return result
