"""
Intervention selector primitive (Ch7).

Maps a diagnostic report to exactly one intervention: RETRIEVAL_FIX,
STRUCTURAL_CONSTRAINT, PROMPT_REFINEMENT, or FINE_TUNE. The routing is a
straightforward deterministic function of the report's failure_type,
sufficiency flag, low-InfoGain step count, and knowledge index. Per the Ch7
Tip, intervention selection should be deterministic and auditable, not a
judgment call made differently by each on-call engineer.

A second axis, the self-modification intensity hierarchy, ranks intervention
types by cost and risk: prompt tuning is the lightest (fast, reversible, low
risk), weight adaptation sits in the middle (slower, semi-reversible, moderate
risk), and code modification is the heaviest (slowest, requires explicit
rollback, highest risk).

Production seam: the report consumed here is produced upstream by the Ch7
Layer 0/1/2 diagnostic pipeline (context sufficiency, cognitive failure
typing, Reasoning Shape Analysis). This module is the routing function that
sits on top of that pipeline. The report shape is the stable contract; the
diagnostic substrate that fills it is the seam.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


# The four interventions select_intervention can emit, plus CODE_MODIFICATION
# from the intensity hierarchy (the heaviest tier, selected only by explicit
# code-level self-modification loops such as SICA, never by this router).
INTERVENTION_TYPES = (
    "RETRIEVAL_FIX",
    "STRUCTURAL_CONSTRAINT",
    "PROMPT_REFINEMENT",
    "FINE_TUNE",
    "CODE_MODIFICATION",
)

# Intensity hierarchy (Ch7): each type carries a tier, speed, reversibility,
# risk descriptor, and a plain-language description grounded in the chapter.
# TODO(production): if you add weight-adaptation variants (LoRA vs full
# fine-tune) split FINE_TUNE into sub-tiers with their own risk ranks.
INTENSITY: Dict[str, Dict[str, str]] = {
    "PROMPT_REFINEMENT": {
        "tier": "lightest",
        "speed": "fast",
        "reversibility": "reversible",
        "risk": "low",
        "description": (
            "Prompt tuning nudges the agent to apply its existing capabilities "
            "more effectively at one node. Fast, reversible, low risk. The right "
            "first resort for a localized reasoning failure."
        ),
    },
    "FINE_TUNE": {
        "tier": "middle",
        "speed": "slower",
        "reversibility": "semi-reversible",
        "risk": "moderate",
        "description": (
            "Weight adaptation changes the model's underlying behavior rather "
            "than steering it at inference time. More expensive, slower to "
            "validate, semi-reversible, moderate risk."
        ),
    },
    "STRUCTURAL_CONSTRAINT": {
        "tier": "architectural",
        "speed": "one-time",
        "reversibility": "permanent-fix",
        "risk": "low-once-applied",
        "description": (
            "Attach an output schema to the node so the format error is "
            "impossible rather than less likely. An architectural change, not a "
            "model change. Produces a permanent fix for that component."
        ),
    },
    "CODE_MODIFICATION": {
        "tier": "heaviest",
        "speed": "slowest",
        "reversibility": "requires-rollback",
        "risk": "highest",
        "description": (
            "Code-level self-modification is the most powerful and most "
            "dangerous form of self-evolution. Slowest, requires explicit "
            "rollback, highest risk. Sandbox with full rollback capability only."
        ),
    },
    "RETRIEVAL_FIX": {
        "tier": "pipeline",
        "speed": "varies",
        "reversibility": "reversible",
        "risk": "low",
        "description": (
            "Flag a Knowledge Graph or retrieval pipeline gap. Targets the "
            "retrieval substrate, not the model: the context was insufficient, "
            "so no amount of model change closes the gap."
        ),
    },
}

# Ordering the intensity hierarchy by risk. prompt < fine-tune < code-mod.
# STRUCTURAL_CONSTRAINT and RETRIEVAL_FIX are low-risk once applied and share
# the base rank; they act on a different axis than the model itself.
RISK_RANK: Dict[str, int] = {
    "low": 1,
    "low-once-applied": 1,
    "moderate": 2,
    "highest": 3,
}


@dataclass
class Intervention:
    """One routed intervention with the condition that produced it.

    ``rationale`` names which branch of the router fired and why, so the
    decision is auditable after the fact rather than opaque.
    """

    type: str
    action: str
    target: Any
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Intervention":
        return cls(
            type=d["type"],
            action=d["action"],
            target=d.get("target"),
            rationale=d.get("rationale", ""),
        )


def select_intervention(
    report: Dict[str, Any],
    low_step_max: int = 2,
    ki_floor: float = 0.8,
) -> Intervention:
    """Route a diagnostic report to exactly one intervention (Ch7 the chapter's select_intervention routing example).

    The four branches, in order:

    1. Insufficient context  -> RETRIEVAL_FIX (fix is upstream of the model).
    2. FORMAT_VIOLATION      -> STRUCTURAL_CONSTRAINT (attach output schema).
    3. Localized REASONING failure (few low-InfoGain steps, high KI)
                             -> PROMPT_REFINEMENT (steer, do not retrain).
    4. Everything else       -> FINE_TUNE (systemic / recurring failure).

    Thresholds ``low_step_max`` and ``ki_floor`` are starting points; tune
    against historical diagnostic data (Ch7 Tip). Raises KeyError if the report
    is missing a required field (layer_1_context.sufficient, layer_2_cognitive,
    failure_type, target_nodes).
    """
    # TODO(production): tune low_step_max / ki_floor against your own historical
    # diagnostic data (Ch7 Tip). The defaults 2 and 0.8 are the chapter's.
    cognitive = report["layer_2_cognitive"]
    failure = cognitive["failure_type"]

    # Branch 1: context gap. Fix the retrieval pipeline, not the model.
    if not report["layer_1_context"]["sufficient"]:
        return Intervention(
            type="RETRIEVAL_FIX",
            action="Flag Knowledge Graph or retrieval pipeline gap",
            target="retrieval_pipeline",
            rationale=(
                "Condition 1 fired: layer_1_context.sufficient is False. The "
                "context was insufficient, so the fix is upstream of the model "
                "in the retrieval pipeline, not an intervention on the model."
            ),
        )

    # Branch 2: format failure. Make the error impossible, not less likely.
    # TODO(production): STRUCTURAL_CONSTRAINT attaches an Outlines-style output
    # schema to the node (Ch6 constrained generation); swap the action string
    # for the real constraint-attachment call in your workflow graph.
    if failure == "FORMAT_VIOLATION":
        return Intervention(
            type="STRUCTURAL_CONSTRAINT",
            action="Attach output schema to node",
            target=report["target_nodes"],
            rationale=(
                "Condition 2 fired: failure_type is FORMAT_VIOLATION. Knowledge "
                "and reasoning were correct but the output was not "
                "machine-readable. Attach a schema constraint so the format "
                "error is impossible rather than merely less likely."
            ),
        )

    # TODO(production): failure_type / low_infogain_steps / knowledge_index are
    # emitted by the Layer 2 cognitive diagnostic (Reasoning Shape Analysis).
    # Defensive .get keeps the router robust to a partially populated report.
    low_steps = cognitive.get("low_infogain_steps", [])
    ki = cognitive.get("knowledge_index", 1.0)

    # Branch 3: localized reasoning failure with intact knowledge. Steer it.
    if failure == "REASONING" and len(low_steps) <= low_step_max and ki > ki_floor:
        return Intervention(
            type="PROMPT_REFINEMENT",
            action="Update prompt for target node",
            target=report["target_nodes"],
            rationale=(
                "Condition 3 fired: failure_type is REASONING, "
                f"low_infogain_steps={low_steps} (count {len(low_steps)} <= "
                f"{low_step_max}), knowledge_index={ki} (> {ki_floor}). A "
                "localized reasoning failure with intact knowledge: steer the "
                "existing capability with a prompt update, do not retrain."
            ),
        )

    # Branch 4: systemic or recurring failure. Retrain.
    # TODO(production): FINE_TUNE routes to SEAL/TPT curriculum generation and a
    # retraining job; swap the action string for the real training trigger.
    return Intervention(
        type="FINE_TUNE",
        action="Generate curriculum via SEAL/TPT and retrain",
        target=report["target_nodes"],
        rationale=(
            "Condition 4 (fallthrough) fired: "
            f"failure_type={failure}, low_infogain_steps={low_steps} "
            f"(count {len(low_steps)}), knowledge_index={ki}. Not a localized "
            "reasoning failure (a knowledge gap, too many low-InfoGain steps, "
            "or a non-reasoning cognitive fault). Requires retraining, not "
            "inference-time steering."
        ),
    )


def intervention_intensity(intervention_type: str) -> Dict[str, str]:
    """Return the intensity profile for an intervention type.

    Keys: tier, speed, reversibility, risk, description. Raises ValueError on
    an unknown type.
    """
    if intervention_type not in INTENSITY:
        raise ValueError(
            f"unknown intervention_type {intervention_type!r}; "
            f"expected one of {tuple(INTENSITY)}"
        )
    return dict(INTENSITY[intervention_type])


def risk_rank(intervention_type: str) -> int:
    """Ordinal risk rank for an intervention type (higher = riskier).

    prompt(1) < fine-tune(2) < code-modification(3). Used to enforce the
    intensity-hierarchy ordering deterministically.
    """
    risk = intervention_intensity(intervention_type)["risk"]
    return RISK_RANK[risk]


def explain(report: Dict[str, Any]) -> str:
    """Human-readable audit line: which condition fired and why.

    Deterministic and auditable (Ch7 Tip): the same report always yields the
    same line, naming the chosen intervention, its intensity tier and risk, the
    fired condition, and the concrete action and target.
    """
    itv = select_intervention(report)
    intensity = intervention_intensity(itv.type)
    exec_id = report.get("execution_id", "<no-execution_id>")
    return (
        f"[{exec_id}] -> {itv.type} "
        f"({intensity['tier']} tier, {intensity['risk']} risk). "
        f"{itv.rationale} "
        f"Action: {itv.action}; target: {itv.target}."
    )
