"""
Semantic backpropagation attributor primitive (Ch7).

Agents are graphs, not pipelines. A good update to one node can silently break
another ("action at a distance"). Semantic backpropagation prevents this: it
attributes a failure to the node that actually caused it and generates
NEIGHBOR-AWARE textual feedback that flows backward through the execution graph.

The load-bearing idea (Ch7, adapting TextGrad's textual-gradient insight): when
generating feedback for node v based on what successor w needed, include the
outputs of ALL OTHER predecessors of w. That neighbor context is what prevents
incorrect credit assignment. In the currency worked example the Validator
surfaces the error, but attribution correctly lands on the CurrencyConverter's
rate lookup and the Extractor is left unchanged, because the DateChecker's
output ("Date: 2022") is included as neighbor evidence.

Production swap: attribution here uses a deterministic numeric-evidence
heuristic and feedback synthesis is a template. In production the attribution
decision and the feedback text are produced by an LLM judge with the neighbor
context in-prompt. The neighbor-aware graph traversal (predecessors_of /
neighbor_context_for) is the stable contract; the attributor and the feedback
generator are the seams.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


Edge = Tuple[str, str]  # (parent, child)


@dataclass
class NodeIO:
    """One node's produced output (and error, if it surfaced one)."""

    node_id: str
    output: Any
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "NodeIO":
        return cls(node_id=d["node_id"], output=d.get("output"), error=d.get("error"))


@dataclass
class SemanticFeedback:
    """Neighbor-aware structured feedback (Ch7 Example 7-19 shape).

    failure_context carries the keys `predicted` and `actual`; neighbor_context
    maps "<node>_output" to that predecessor's output; feedback is the textual
    gradient sent backward to target_node.
    """

    target_node: str
    failure_context: Dict[str, Any]
    neighbor_context: Dict[str, str]
    feedback: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_node": self.target_node,
            "failure_context": dict(self.failure_context),
            "neighbor_context": dict(self.neighbor_context),
            "feedback": self.feedback,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SemanticFeedback":
        return cls(
            target_node=d["target_node"],
            failure_context=dict(d.get("failure_context", {})),
            neighbor_context=dict(d.get("neighbor_context", {})),
            feedback=d.get("feedback", ""),
        )


# -- graph traversal (the stable contract) --------------------------------


def predecessors_of(edges: List[Edge], node_id: str) -> List[str]:
    """Return the parents of node_id. Edges are (parent, child).

    Order follows edge insertion order so attribution is deterministic.
    """
    return [parent for (parent, child) in edges if child == node_id]


def neighbor_context_for(
    edges: List[Edge],
    node_outputs: Dict[str, str],
    target_node: str,
    successor: str,
) -> Dict[str, str]:
    """Collect the outputs of every OTHER predecessor of `successor`.

    Excludes target_node itself. Keyed as "<node>_output". This is the
    neighbor-awareness primitive: the feedback for target_node is grounded in
    what its sibling predecessors fed into the same successor.
    """
    ctx: Dict[str, str] = {}
    for pred in predecessors_of(edges, successor):
        if pred == target_node:
            continue
        ctx[f"{pred}_output"] = str(node_outputs.get(pred, ""))
    return ctx


# -- attribution (a production seam) --------------------------------------


def _numbers(text: Any) -> set:
    """Salient numeric tokens (integers and decimals) from a string."""
    return set(re.findall(r"\d+(?:\.\d+)?", str(text)))


def attribute(
    edges: List[Edge],
    node_outputs: Dict[str, str],
    failure_node: str,
    predicted: Any,
    actual: Any,
) -> str:
    """Decide which node the error ORIGINATES in.

    The failure_node is where the error surfaced; the responsible node may
    differ. A direct predecessor is IMPLICATED when its output carries a value
    that appears in the (wrong) prediction but is contradicted by the actual
    outcome. If a predecessor is implicated, attribution lands on it (currency
    example: the Validator surfaces, the CurrencyConverter is responsible). If
    no predecessor is implicated, the neighbor inputs were sound and the fault
    is the failure_node's own reasoning (devops example: attribution stays on
    the CausalAttributionNode).

    # TODO(production): swap this numeric-evidence heuristic for a J1/LLM judge
    # that reads the neighbor context and returns the responsible node_id.
    """
    preds = predecessors_of(edges, failure_node)
    if not preds:
        return failure_node
    predicted_nums = _numbers(predicted)
    actual_nums = _numbers(actual)
    for pred in preds:
        pred_nums = _numbers(node_outputs.get(pred, ""))
        implicated = bool(pred_nums & predicted_nums) and not bool(pred_nums & actual_nums)
        if implicated:
            return pred
    return failure_node


def _successor_of(edges: List[Edge], node_id: str, fallback: str) -> str:
    """First child of node_id, or fallback if it is a terminal node."""
    for (parent, child) in edges:
        if parent == node_id:
            return child
    return fallback


# -- feedback generation (a production seam) ------------------------------


def generate_feedback(
    target_node: str,
    successor: str,
    edges: List[Edge],
    node_outputs: Dict[str, str],
    predicted: Any,
    actual: Any,
    feedback_text: str,
) -> SemanticFeedback:
    """Assemble neighbor-aware SemanticFeedback for target_node.

    The neighbor context is the outputs of the sibling predecessors of
    `successor`. If feedback_text is empty, synthesize a neighbor-grounded
    default that names the neighbor evidence so the feedback is actionable
    rather than a vague "do better" signal.

    # TODO(production): swap the synthesized default for an LLM that writes the
    # textual gradient from failure_context + neighbor_context.
    """
    neighbor_context = neighbor_context_for(edges, node_outputs, target_node, successor)
    failure_context = {"predicted": predicted, "actual": actual}
    text = (feedback_text or "").strip()
    if not text:
        if neighbor_context:
            evidence = "; ".join(f"{k} = {v}" for k, v in neighbor_context.items())
            text = (
                f"{target_node} produced '{predicted}' but the correct outcome was "
                f"'{actual}'. Neighbor evidence: {evidence}. Re-evaluate {target_node} "
                f"in light of this neighbor context; leave unchanged any upstream node "
                f"whose output the evidence confirms."
            )
        else:
            text = (
                f"{target_node} produced '{predicted}' but the correct outcome was "
                f"'{actual}'. No neighbor evidence was available; inspect "
                f"{target_node}'s own reasoning."
            )
    return SemanticFeedback(
        target_node=target_node,
        failure_context=failure_context,
        neighbor_context=neighbor_context,
        feedback=text,
    )


def backprop(
    edges: List[Edge],
    node_outputs: Dict[str, str],
    failure_node: str,
    predicted: Any,
    actual: Any,
    feedback_text: str = "",
) -> SemanticFeedback:
    """Attribute the failure, then generate neighbor-aware feedback for the
    responsible node.

    Convenience over attribute + generate_feedback: the successor is the first
    child of the responsible node (the node it fed into on the path to the
    failure), or the failure_node itself when the responsible node is terminal.
    """
    responsible = attribute(edges, node_outputs, failure_node, predicted, actual)
    successor = _successor_of(edges, responsible, fallback=failure_node)
    return generate_feedback(
        target_node=responsible,
        successor=successor,
        edges=edges,
        node_outputs=node_outputs,
        predicted=predicted,
        actual=actual,
        feedback_text=feedback_text,
    )


def outputs_from(nodes: List[NodeIO]) -> Dict[str, str]:
    """Build a node_outputs mapping from a list of NodeIO records."""
    return {n.node_id: str(n.output) for n in nodes}
