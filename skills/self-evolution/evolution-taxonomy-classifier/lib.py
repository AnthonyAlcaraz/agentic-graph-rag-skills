"""
Evolution taxonomy classifier (Ch7).

Classifies a proposed self-evolution across the four axes Gao et al. (2025)
formalize: WHAT evolves, WHEN evolution fires, HOW the agent learns, WHERE it
applies. Each axis value carries the graph-dependency rationale the chapter
gives: model evolution needs execution graphs for causal tracing, context
evolution IS graph evolution, tool evolution rewires the tool subgraph, and
architecture evolution restructures the workflow graph itself. Alshikh's
production research reinforces the graph-first principle: "each adaptation
becomes a traceable node." This classifier is the routing front end that turns
a diagnosis into the correct evolution lever instead of pulling the wrong one.

Production swap: the `classify` heuristic keyword mapping is a dev-time
stand-in. The public axis constants, the `EvolutionClassification` dataclass,
and `route_failure` are the stable contract; the free-text-to-axis inference is
the seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict


# -- Axis vocabularies. Each value: one-line description including its graph
#    rationale (the "Connecting the axes" claim from Ch7). -------------------

WHAT_EVOLVES: Dict[str, str] = {
    "model": (
        "Changes the weights or prompts that drive reasoning (adapter "
        "fine-tune, gradient-free prompt search). Needs execution graphs for "
        "causal tracing: which prompt version produced which outcome across "
        "hundreds of runs."
    ),
    "context": (
        "Restructures what the agent retrieves (rerank subgraphs, consolidate "
        "memory nodes, adjust thresholds). IS graph evolution: rewire edges, "
        "merge redundant nodes, prune stale subgraphs. No equivalent in flat "
        "document stores."
    ),
    "tool": (
        "Modifies how the agent interacts with external systems (register "
        "endpoints, deprecate unreliable tools, rewrite descriptions). Rewires "
        "the tool subgraph by reweighting task-type-to-tool edges on observed "
        "success rates."
    ),
    "architecture": (
        "Reorganizes the agent's own topology (add a verification node, split "
        "a planner into subagents, restructure the schema). Graph surgery in "
        "the literal sense: adding and removing nodes from the workflow graph "
        "itself."
    ),
}

WHEN_FIRES: Dict[str, str] = {
    "intra_test_time": (
        "Within a single request. Must be fast (sub-second decisions). The "
        "Reflect-Retry-Reward loop is the canonical instance: the agent "
        "traverses its live execution graph and corrects before responding."
    ),
    "inter_test_time": (
        "Between requests. Can afford expensive operations like fine-tuning or "
        "graph restructuring: the SEAL curriculum generates training data "
        "overnight and semantic backpropagation updates neighbor prompts, so "
        "the next morning's agent is measurably different."
    ),
}

HOW_LEARNS: Dict[str, str] = {
    "reward_based": (
        "Uses scalar signals (InfoGain, user-satisfaction scores, composite "
        "reward functions). The reward is computed over graph-derived metrics "
        "of the run."
    ),
    "imitation_based": (
        "Copies successful trajectories from demonstrations or from the "
        "agent's own best past performances. The trajectory is a path through "
        "the execution graph."
    ),
    "population_based": (
        "Maintains multiple agent variants and selects the fittest. Useful "
        "when you cannot define a clean reward signal but can compare graph "
        "outcomes across variants."
    ),
}

WHERE_APPLIES: Dict[str, str] = {
    "general_purpose": (
        "Improves the agent across all tasks. The evolution target is the "
        "whole workflow graph rather than any one region."
    ),
    "domain_specialized": (
        "Targets a specific vertical. The DevOps agent need not improve at "
        "poetry but must get better at predicting cascade failures in "
        "microservice topologies: evolution focused on one subgraph region."
    ),
}

_AXIS_SETS = {
    "what": WHAT_EVOLVES,
    "when": WHEN_FIRES,
    "how": HOW_LEARNS,
    "where": WHERE_APPLIES,
}


@dataclass
class EvolutionClassification:
    """A proposed self-evolution located on all four Gao et al. axes.

    `graph_rationale` carries, per axis, the graph-dependency reason the
    chapter gives for the chosen value. `notes` is free-form provenance.
    """

    what: str
    when: str
    how: str
    where: str
    graph_rationale: Dict[str, str] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_from_signals(
    what: str,
    when: str,
    how: str,
    where: str,
    notes: str = "",
) -> EvolutionClassification:
    """Validate each axis value against its allowed set and attach rationale.

    Raises ValueError on any unknown axis value. Fills `graph_rationale` from
    the chapter's axis vocabularies for the four chosen values.
    """
    chosen = {"what": what, "when": when, "how": how, "where": where}
    for axis, value in chosen.items():
        allowed = _AXIS_SETS[axis]
        if value not in allowed:
            raise ValueError(
                f"unknown {axis} value {value!r}; allowed: {sorted(allowed)}"
            )
    graph_rationale = {axis: _AXIS_SETS[axis][value] for axis, value in chosen.items()}
    return EvolutionClassification(
        what=what,
        when=when,
        how=how,
        where=where,
        graph_rationale=graph_rationale,
        notes=notes,
    )


def _match(blob: str, keywords) -> bool:
    return any(k in blob for k in keywords)


def classify(proposal: Dict[str, Any]) -> EvolutionClassification:
    """Heuristically map a free-form proposal to the four axes, then delegate.

    Proposal shape: {description, target, timing, mechanism, scope} (all
    optional). Keyword matching is deliberately simple; this is the seam a
    production system swaps for an NLI classifier.
    """
    parts = []
    for key in ("description", "target", "timing", "mechanism", "scope"):
        val = proposal.get(key)
        if val:
            parts.append(str(val))
    blob = " ".join(parts).lower()

    # WHAT evolves
    if _match(blob, ("prompt", "weights", "fine-tune", "fine tune", "finetune", "adapter")):
        what = "model"
    elif _match(blob, ("rerank", "retrieval", "subgraph", "memory node", "threshold")):
        what = "context"
    elif _match(blob, ("tool", "api", "endpoint")):
        what = "tool"
    elif _match(blob, ("node", "topology", "schema", "subagent")):
        what = "architecture"
    else:
        what = "model"

    # WHEN fires
    if _match(blob, ("within a request", "within one request", "real-time", "real time", "intra")):
        when = "intra_test_time"
    else:
        when = "inter_test_time"

    # HOW learns
    if _match(blob, ("reward", "score", "infogain", "satisfaction")):
        how = "reward_based"
    elif _match(blob, ("demonstrat", "copy", "imitat", "trajector")):
        how = "imitation_based"
    elif _match(blob, ("variant", "population", "fittest")):
        how = "population_based"
    else:
        how = "reward_based"

    # WHERE applies
    if _match(blob, ("all tasks", "general")):
        where = "general_purpose"
    else:
        where = "domain_specialized"

    notes = proposal.get("description", "") or ""
    return classify_from_signals(what, when, how, where, notes=notes)


# -- Table 7-1: failure-to-evolution routing --------------------------------

_KNOWN_FAILURES = {"FORMAT", "FORMAT_VIOLATION", "REASONING", "KNOWLEDGE"}


def route_failure(
    failure_type: str,
    recurring: bool = False,
    is_format: bool = False,
) -> Dict[str, str]:
    """Route a diagnosed failure to its primary evolution axis, timing, and
    mechanism per Ch7 Table 7-1 and the three-way intervention strategy.

    FORMAT / FormatViolation -> architecture (structural constraint), inter.
    REASONING at a single node -> model (prompt refinement), intra; a recurring
    reasoning pattern escalates to model (fine-tune), inter.
    KNOWLEDGE gap -> context (retrieval fix), inter; a systemic recurring gap
    escalates to model (fine-tune), inter.
    """
    key = failure_type.strip().upper()
    if is_format:
        key = "FORMAT"
    if key not in _KNOWN_FAILURES:
        raise ValueError(
            f"unknown failure_type {failure_type!r}; allowed: {sorted(_KNOWN_FAILURES)}"
        )

    if key in ("FORMAT", "FORMAT_VIOLATION"):
        return {
            "evolution_axis": "architecture",
            "timing": "inter_test_time",
            "mechanism": "structural-constraint",
            "rationale": (
                "The agent had the right knowledge and reasoning but failed to "
                "produce machine-readable output. Attach an output schema "
                "constraint to that node in the workflow graph, making the "
                "format error impossible rather than less likely. This is an "
                "architectural change, not a model change, and is a permanent "
                "fix for that component."
            ),
        }

    if key == "REASONING":
        if recurring:
            return {
                "evolution_axis": "model",
                "timing": "inter_test_time",
                "mechanism": "fine-tune",
                "rationale": (
                    "A recurring pattern of the same reasoning failure is a "
                    "systemic signal. Fine-tuning changes the model's "
                    "underlying behavior rather than steering it at inference "
                    "time. Heavyweight and slower to validate, so it runs "
                    "between requests."
                ),
            }
        return {
            "evolution_axis": "model",
            "timing": "intra_test_time",
            "mechanism": "prompt",
            "rationale": (
                "A localized reasoning failure (low InfoGain on one or two "
                "steps) with correct information. Prompt refinement nudges the "
                "agent to apply its existing capabilities at that node. Fast, "
                "reversible, the right first resort."
            ),
        }

    # KNOWLEDGE
    if recurring:
        return {
            "evolution_axis": "model",
            "timing": "inter_test_time",
            "mechanism": "fine-tune",
            "rationale": (
                "A systemic knowledge gap (consistently low KI across "
                "executions) calls for fine-tuning. It changes the model's "
                "underlying behavior; expensive, so it runs between requests."
            ),
        }
    return {
        "evolution_axis": "context",
        "timing": "inter_test_time",
        "mechanism": "retrieval-fix",
        "rationale": (
            "A non-systemic knowledge gap means retrieval context was "
            "insufficient. Flag the Knowledge Graph or retrieval pipeline gap "
            "and evolve context (rewire edges, add subgraph coverage) rather "
            "than touch the weights."
        ),
    }
