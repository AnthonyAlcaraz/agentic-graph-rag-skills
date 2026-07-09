"""
Model routing / selective intelligence — pick the cheapest model that meets a
node's quality bar, distilled from Agentic Graph RAG (O'Reilly), Chapter 8 —
Optimization, "Selective Intelligence".

The chapter's central claim: match model capability to task complexity. Instead
of routing every node of the horizontal workflow graph through one frontier
model, deploy a federation of specialists — small fine-tuned SLMs for routine
classification/extraction, mid-tier models for structured reasoning, frontier
models only for open-ended synthesis. Running a 3B SLM can be 10-30x cheaper
per token than its 405B sibling; at production volume that difference decides
whether the project survives its first budget review.

Three routing strategies (Ch8 "Routing Strategies"), each suited to a stage of
system maturity:
  static      — fixed model per node type, decided at design time (start here)
  cascade     — try cheapest first, escalate on low confidence (FrugalGPT)
  learned     — a trained router picks per query (RouteLLM / MixLLM)

Cost multipliers here are the book's figures (Example 8-13 DEVOPS_MODEL_CONFIG:
1/30th, 1/10th, ~1/5th blended, 1x). The per-model *capability* scores are an
illustrative ordinal scale distilled from the chapter's tiering, NOT book
figures — the same convention graph-model-selector uses for its feature scores.

Pure Python, stdlib only. No model API required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# --- Model catalog ----------------------------------------------------------
# cost_vs_frontier: fraction of the frontier per-token cost (book figures).
# base_capability: illustrative ordinal 0..1 for OPEN-ended tasks (distilled
#   from the chapter tiering; not a book number). A fine-tuned specialist beats
#   this ceiling on its narrow task (Triplex 3.8B outperforms GPT-4o at KG
#   construction; a fine-tuned 3B meets the 0.99 alert-classification bar).
SPECIALIST_CEILING = 0.99  # narrow fine-tuned SLM ceiling (Ch8 Example 8-4)

MODELS: dict[str, dict[str, Any]] = {
    "llama-3.1-3b": {"cost_vs_frontier": 1 / 30, "base_capability": 0.55, "tier": "slm"},
    "llama-3.1-8b": {"cost_vs_frontier": 1 / 10, "base_capability": 0.82, "tier": "mid"},
    "claude-sonnet": {"cost_vs_frontier": 1.0, "base_capability": 0.95, "tier": "frontier"},
}

# Task classes that a small model can be fine-tuned into a specialist for. On
# these classes the SLM reaches SPECIALIST_CEILING; on everything else it only
# has its base_capability. (Ch8 "The Case for Model Specialization".)
SPECIALIST_TASK_CLASSES = frozenset({"classification", "extraction"})


@dataclass
class Node:
    """A node in the horizontal workflow graph and the bar it must clear.

    task_class: classification | extraction | multi_hop | causal | synthesis
    required_quality: minimum acceptable quality (book figures for
        AlertClassifier=0.99 and QueryAnalyst=0.90 per Example 8-4; other bars
        are distilled ordinals labelled below).
    variable_difficulty: True when per-query difficulty varies enough that a
        cascade is warranted (Ch8: cascade "works well for nodes where task
        difficulty varies").
    """
    name: str
    task_class: str
    required_quality: float
    variable_difficulty: bool = False


# The DevOps agent's horizontal workflow graph (Ch8 Example 8-13) plus the
# QueryAnalyst from Example 8-4. chapter_model / chapter_cost are the book's
# assignments; the router below re-derives them from first principles so the
# benchmark can prove the derivation matches the book.
NODES: dict[str, Node] = {
    "AlertClassifier": Node("AlertClassifier", "classification", 0.99),
    "QueryAnalyst": Node("QueryAnalyst", "classification", 0.90),
    "LogParser": Node("LogParser", "extraction", 0.90),
    "DependencyAnalyzer": Node("DependencyAnalyzer", "multi_hop", 0.80),
    "CausalAttributionNode": Node("CausalAttributionNode", "causal", 0.90, variable_difficulty=True),
    "PredictionSynthesis": Node("PredictionSynthesis", "synthesis", 0.92),
}

# Book's design-time assignment (Example 8-13) — used as the static-route table
# and as the benchmark's ground truth.
CHAPTER_ASSIGNMENT: dict[str, dict[str, Any]] = {
    "AlertClassifier": {"model": "llama-3.1-3b", "cost_vs_frontier": "1/30th"},
    "QueryAnalyst": {"model": "llama-3.1-3b", "cost_vs_frontier": "1/30th"},
    "LogParser": {"model": "llama-3.1-3b", "cost_vs_frontier": "1/30th"},
    "DependencyAnalyzer": {"model": "llama-3.1-8b", "cost_vs_frontier": "1/10th"},
    "CausalAttributionNode": {"model": "cascade:llama-3.1-8b->claude-sonnet",
                              "cost_vs_frontier": "~1/5th (blended)"},
    "PredictionSynthesis": {"model": "claude-sonnet", "cost_vs_frontier": "1x"},
}

# Cascade thresholds (Ch8 Example 8-1 synthesis cascade + Example 8-13
# CausalAttributionNode escalates when 8B confidence < 0.7).
CASCADE_CHEAP_THRESHOLD = 0.85
CASCADE_MID_THRESHOLD = 0.75
CAUSAL_ESCALATE_BELOW = 0.7


def effective_quality(model_id: str, node: Node) -> float:
    """Quality a model actually delivers ON THIS NODE.

    A fine-tuned SLM reaches SPECIALIST_CEILING on a specialist task class;
    otherwise the model only offers its base_capability. This is the mechanism
    behind the chapter's counter-intuitive result: a 3B model meets a 0.99 bar
    on narrow classification while a frontier model is needed for open-ended
    synthesis.
    """
    m = MODELS[model_id]
    if m["tier"] in ("slm", "mid") and node.task_class in SPECIALIST_TASK_CLASSES:
        return SPECIALIST_CEILING
    return float(m["base_capability"])


def _models_by_cost() -> list[str]:
    return sorted(MODELS, key=lambda mid: MODELS[mid]["cost_vs_frontier"])


def static_route(node_name: str) -> dict[str, Any]:
    """Strategy 1 — static routing by node type (Ch8). Fixed assignment decided
    at design time; no runtime decision. Returns the book's assignment."""
    node = NODES[node_name]
    assign = CHAPTER_ASSIGNMENT[node_name]
    return {
        "node": node_name,
        "strategy": "static",
        "model": assign["model"],
        "cost_vs_frontier": assign["cost_vs_frontier"],
        "rationale": "Fixed model per node type, chosen at design time. Start here.",
    }


def cheapest_meeting_bar(node_name: str) -> dict[str, Any]:
    """Core deliverable — pick the cheapest model whose effective quality on
    this node clears its required_quality bar.

    When the only model that clears the bar is the frontier model AND the node
    has variable per-query difficulty, recommend a cascade instead of paying
    frontier cost on every invocation (Ch8 threshold-based cascading).
    """
    node = NODES[node_name]
    chosen = None
    for mid in _models_by_cost():
        if effective_quality(mid, node) >= node.required_quality:
            chosen = mid
            break
    if chosen is None:
        # Nothing meets the bar; return the strongest available and flag it.
        chosen = "claude-sonnet"
        return {
            "node": node_name, "strategy": "static", "model": chosen,
            "meets_bar": effective_quality(chosen, node) >= node.required_quality,
            "warning": "No available model meets the required quality bar.",
        }

    result = {
        "node": node_name,
        "model": chosen,
        "effective_quality": round(effective_quality(chosen, node), 3),
        "required_quality": node.required_quality,
        "cost_vs_frontier": round(MODELS[chosen]["cost_vs_frontier"], 4),
        "strategy": "static",
    }
    if MODELS[chosen]["tier"] == "frontier" and node.variable_difficulty:
        result["strategy"] = "cascade"
        result["model"] = "cascade:llama-3.1-8b->claude-sonnet"
        result["rationale"] = (
            "Frontier is the only model that clears the bar, but per-query "
            "difficulty varies. Cascade: let the 8B model try first, escalate "
            f"to frontier when confidence < {CAUSAL_ESCALATE_BELOW}."
        )
    return result


def cascade_route(node_name: str, confidence: float,
                  cheap_threshold: float = CASCADE_CHEAP_THRESHOLD,
                  mid_threshold: float = CASCADE_MID_THRESHOLD) -> dict[str, Any]:
    """Strategy 2 — threshold-based cascading (FrugalGPT, Ch8 Example 8-1).

    Given the cheapest model's self-reported confidence, decide whether to
    return it or escalate. Three-tier ladder: cheap -> mid -> frontier.
    """
    if confidence >= cheap_threshold:
        served, tier = "llama-3.1-3b", "cheap"
    elif confidence >= mid_threshold:
        served, tier = "llama-3.1-8b", "mid"
    else:
        served, tier = "claude-sonnet", "frontier"
    return {
        "node": node_name,
        "strategy": "cascade",
        "confidence": confidence,
        "served_by": served,
        "tier": tier,
        "cost_vs_frontier": round(MODELS[served]["cost_vs_frontier"], 4),
        "thresholds": {"cheap": cheap_threshold, "mid": mid_threshold},
    }


def learned_route(node_name: str, cost_threshold: float = 0.7) -> dict[str, Any]:
    """Strategy 3 — learned routing (RouteLLM / MixLLM, Ch8).

    A trained router picks strong vs weak per query. RouteLLM reports >2x cost
    reduction retaining 95% of GPT-4 quality on MT-Bench; MixLLM reaches 97% of
    GPT-4 quality at 24% of the cost. The router-mf-0.7 model string encodes the
    matrix-factorization strategy and the 0.7 cost-quality threshold.
    """
    # TODO(production): call routellm.controller.Controller(routers=["mf"], ...).
    # The contract (a node + a cost threshold -> a model id) is the seam; the
    # heuristic below stands in for the trained router in the spike.
    route_strong = cost_threshold >= 0.7
    served = "claude-sonnet" if route_strong else "llama-3.1-8b"
    return {
        "node": node_name,
        "strategy": "learned",
        "router": f"router-mf-{cost_threshold}",
        "served_by": served,
        "cost_vs_frontier": round(MODELS[served]["cost_vs_frontier"], 4),
        "note": "Lower threshold -> more traffic to the weak model. Calibrate "
                "against the per-node evaluation set (see cost-performance-scorer).",
    }


def pipeline_cost(escalation_rate: float = 0.30) -> dict[str, Any]:
    """Blended cost per prediction: frontier-everywhere vs selective intelligence.

    The DevOps pipeline runs AlertClassifier, LogParser, DependencyAnalyzer,
    CausalAttributionNode, PredictionSynthesis. Under selective intelligence
    only PredictionSynthesis always uses the frontier model, and
    CausalAttributionNode uses it only `escalation_rate` of the time (the book
    calibrates ~30%). The book reports the blended cost per prediction drops by
    roughly 80%.
    """
    pipeline = ["AlertClassifier", "LogParser", "DependencyAnalyzer",
                "CausalAttributionNode", "PredictionSynthesis"]
    frontier_everywhere = float(len(pipeline))  # every node at 1x frontier cost

    selective = 0.0
    breakdown = []
    for name in pipeline:
        if name == "CausalAttributionNode":
            # blended: 8B most of the time, frontier `escalation_rate` of the time
            c = ((1 - escalation_rate) * MODELS["llama-3.1-8b"]["cost_vs_frontier"]
                 + escalation_rate * MODELS["claude-sonnet"]["cost_vs_frontier"])
        else:
            mid = cheapest_meeting_bar(name)["model"]
            base = mid.split(":")[0].split("->")[0]
            base = base if base in MODELS else "claude-sonnet"
            c = MODELS[base]["cost_vs_frontier"]
        selective += c
        breakdown.append({"node": name, "cost_vs_frontier": round(c, 4)})

    reduction = 1.0 - selective / frontier_everywhere
    return {
        "frontier_everywhere_units": round(frontier_everywhere, 3),
        "selective_units": round(selective, 3),
        "reduction_pct": round(100.0 * reduction, 1),
        "escalation_rate": escalation_rate,
        "breakdown": breakdown,
        "note": "Equal per-node token weighting. The book reports ~80% under "
                "its own token weighting, where the frontier synthesis node "
                "dominates the baseline; equal weights here land near 70%. "
                "Pass real per-node token counts to reproduce the book's figure.",
    }
