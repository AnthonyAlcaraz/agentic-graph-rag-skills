"""
Context-failure-mode classifier (Agentic Graph RAG, Ch1 — The Crisis).

Given an observed agent symptom (a sentence describing what went wrong),
classify it into the Ch1 failure taxonomy and name the architectural root
cause and the curing graph capability. Ch1 enumerates two interlocking
taxonomies:

  * the FIVE FATAL FLAWS of naive vector RAG (the architecture-level cause)
  * the FOUR AGENT FAILURE MODES that each flaw compounds into at the
    agent level (action blindness / memory fragmentation / planning
    paralysis / context drift), each reinforcing the others into "a
    cascade of agent incompetence".

Pure Python, no external deps. Classification is keyword/rule based; the
LLM-classifier swap is a documented seam.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


# Agent-level failure modes (Ch1 lines 159-168). Each compounds from one or
# more of the five fatal flaws and reinforces the others.
AGENT_FAILURE_MODES: Dict[str, Dict[str, Any]] = {
    "action_blindness": {
        "definition": "Without entity relationships, the agent can't predict "
                      "consequences; restarts a service unaware it cascades failures.",
        "root_flaw": "relationship_blindness",
        "cure": "entity_relationships",
        # Distinctive signals: action + unforeseen consequence / cascade.
        "signals": [
            r"\bcascad", r"\bdependen", r"\bbreak\w*\s+(?:dependen|other|down)",
            r"\brestart\w*", r"\bsecond[- ]order", r"\bripple", r"\bimpact\w* (?:other|down)",
            r"\bunaware (?:it|that)", r"\bwithout knowing",
        ],
    },
    "memory_fragmentation": {
        "definition": "Each query starts fresh; the agent can't build on prior "
                      "understanding or learn from past actions.",
        "root_flaw": "context_amnesia",
        "cure": "evolving_memory",
        "signals": [
            r"\bforg\w*", r"\bamnesi", r"\bstarts? (?:from )?(?:fresh|scratch)",
            r"\bno memory", r"\bcan'?t remember", r"\beach (?:query|conversation|session)",
            r"\bre-?ask\w*", r"\bprior (?:interaction|conversation)",
            r"\blast (?:week|month)'?s?\b",
        ],
    },
    "planning_paralysis": {
        "definition": "Multi-step tasks need dependency reasoning; without "
                      "relationship traversal or temporal sequence, goals can't "
                      "decompose into executable plans.",
        "root_flaw": "reasoning_paralysis",
        "cure": "multi_hop_reasoning",
        "signals": [
            r"\bmulti[- ]?step", r"\bdecompos", r"\bplan\w*", r"\bcan'?t (?:plan|sequence)",
            r"\bsynthesi[sz]", r"\bacross (?:multiple|several) (?:document|source)",
            r"\btransitive", r"\blogical chain", r"\bconnect\w* the (?:dots|facts)",
            r"\bwhich services were affected by",
        ],
    },
    "context_drift": {
        "definition": "The world changes; static embeddings cause the agent to "
                      "operate on outdated models of reality, getting more "
                      "dangerous as drift accumulates.",
        "root_flaw": "temporal_ignorance",
        "cure": "temporal_evolution",
        "signals": [
            r"\boutdated", r"\bstale", r"\bold config\w*", r"\bno longer exists?",
            r"\brevert\w*", r"\brollback", r"\bchanged over time", r"\bcurrent truth",
            r"\bfrozen", r"\bdrift", r"\bwhat (?:was|is) true (?:when|at)",
        ],
    },
}

# The fifth fatal flaw (tool chaos) is an architecture-level cause that
# manifests as wrong-tool / wrong-API selection (Ch1 line 14 + line 110).
# It is not in the four agent-level modes but is a distinct classifiable
# symptom, so we carry it as its own bucket.
TOOL_CHAOS = {
    "definition": "Without understanding tool relationships, the agent guesses "
                  "which API to call instead of orchestrating intelligently.",
    "root_flaw": "tool_chaos",
    "cure": "tool_orchestration",
    "signals": [
        r"\bwrong (?:tool|api|retailer|endpoint)", r"\bguess\w* which",
        r"\bambiguous .*tool", r"\bbloated tool", r"\btoo many tools",
        r"\bwhich tool to (?:call|use)", r"\bcalled the wrong",
    ],
}

# Combined registry for classification.
ALL_MODES: Dict[str, Dict[str, Any]] = dict(AGENT_FAILURE_MODES)
ALL_MODES["tool_chaos"] = TOOL_CHAOS

# Five fatal flaws (root-cause layer) — for reverse lookup / reporting.
FIVE_FATAL_FLAWS: Dict[str, str] = {
    "context_amnesia": "Conversations start from scratch; no cross-interaction memory.",
    "relationship_blindness": "Entities seen but not how they connect.",
    "temporal_ignorance": "Static embeddings treat outdated config as current.",
    "reasoning_paralysis": "Finds similar text, not logical/causal connections.",
    "tool_chaos": "No understanding of tool relationships; guesses which API.",
}


def _count_signals(text: str, signals: List[str]) -> Tuple[int, List[str]]:
    hits = []
    for pat in signals:
        if re.search(pat, text, flags=re.IGNORECASE):
            hits.append(pat)
    return len(hits), hits


def classify(symptom: str) -> Dict[str, Any]:
    """Classify one symptom sentence into the Ch1 failure taxonomy.

    Returns the best-matching failure mode with its root fatal flaw and the
    curing graph capability, plus all scored candidates (for transparency
    and to expose the 'cascade' — Ch1's point that modes reinforce).
    """
    scored = []
    for mode, spec in ALL_MODES.items():
        n, hits = _count_signals(symptom, spec["signals"])
        if n > 0:
            scored.append({
                "failure_mode": mode,
                "match_count": n,
                "matched_signals": hits,
                "root_flaw": spec["root_flaw"],
                "cure": spec["cure"],
                "definition": spec["definition"],
            })
    scored.sort(key=lambda x: x["match_count"], reverse=True)

    if not scored:
        return {
            "symptom": symptom,
            "classified": False,
            "primary": None,
            "candidates": [],
            "note": "No taxonomy signal matched. Either not a retrieval/context "
                    "failure, or describe the symptom in terms of behavior "
                    "(what the agent did wrong), not infrastructure.",
        }

    primary = scored[0]
    # Cascade: Ch1 says each failure mode reinforces the others. Surface the
    # secondary modes that also matched so the operator sees the cascade.
    cascade = [s["failure_mode"] for s in scored[1:]]
    return {
        "symptom": symptom,
        "classified": True,
        "primary": {
            "failure_mode": primary["failure_mode"],
            "root_flaw": primary["root_flaw"],
            "root_flaw_description": FIVE_FATAL_FLAWS[primary["root_flaw"]],
            "cure": primary["cure"],
            "definition": primary["definition"],
        },
        "cascade_modes": cascade,
        "candidates": scored,
    }


def classify_batch(symptoms: List[str]) -> Dict[str, Any]:
    """Classify a list of symptoms (e.g. one incident's post-mortem bullets).

    Returns per-symptom classification plus an aggregate: which fatal flaws
    appear, and the union of curing capabilities to prioritize.
    """
    results = [classify(s) for s in symptoms]
    flaw_counts: Dict[str, int] = {}
    cures: Dict[str, int] = {}
    unclassified = 0
    for r in results:
        if not r["classified"]:
            unclassified += 1
            continue
        flaw = r["primary"]["root_flaw"]
        flaw_counts[flaw] = flaw_counts.get(flaw, 0) + 1
        cure = r["primary"]["cure"]
        cures[cure] = cures.get(cure, 0) + 1
    prioritized = sorted(cures.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "results": results,
        "fatal_flaws_present": flaw_counts,
        "prioritized_cures": [c for c, _ in prioritized],
        "unclassified": unclassified,
        "summary": (
            "Cures ordered by how many symptoms each resolves. "
            "Per Ch1, the flaws cascade — closing the top cure often "
            "relieves several symptoms at once."
        ),
    }


# TODO: production — replace the regex signal matcher with an LLM classifier
# (or a fine-tuned small model) that maps free-text symptoms to the taxonomy.
# The classify() signature is the seam; keep the same return shape.
