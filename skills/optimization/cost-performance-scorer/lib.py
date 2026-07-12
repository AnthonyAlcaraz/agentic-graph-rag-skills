"""
Cost-performance scoring for a multi-model routing policy, distilled from
Agentic GraphRAG (O'Reilly), Chapter 8 — Optimization, "Measuring
Cost-Performance Tradeoffs".

Routing strategies are only as good as the data that informs them. Selective
intelligence only works if you can measure it. Two metrics matter:

  cost per successful completion — total cost / tasks completed CORRECTLY, not
      cost per token. "A cheap model that fails 40% of the time is not cheaper
      than an expensive model that succeeds on the first attempt."
  quality parity threshold — the minimum acceptable quality per node type. The
      AlertClassifier may need 0.99 (a wrong validation is worse than none); the
      QueryAnalyst may tolerate 0.90 because downstream nodes recover.

The chapter's harness wraps every node, logs a NodeInvocation per call
(Example 8-3), and evaluates each candidate model against a PER-NODE evaluation
set drawn from production data with domain-specific failure weights (Example
8-4). A generic benchmark (MMLU) cannot capture that a P1 alert misclassified
as P3 is 10x worse than the reverse.

Pure Python, stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class NodeInvocation:
    """One logged model call (Ch8 Example 8-3)."""
    node_name: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    success: bool  # evaluated against gold labels or downstream acceptance


class CostTracker:
    """Wraps node invocations and computes cost per successful completion.

    In the book the tracker also wraps the async model call and evaluates
    success via a per-node evaluator callback; here we accept already-scored
    NodeInvocation records so the module has zero async / API dependencies.
    """

    def __init__(self) -> None:
        self.invocations: list[NodeInvocation] = []

    def log(self, inv: NodeInvocation) -> None:
        self.invocations.append(inv)

    def _for_node(self, node_name: str) -> list[NodeInvocation]:
        return [i for i in self.invocations if i.node_name == node_name]

    def cost_per_success(self, node_name: str) -> float:
        """Total cost / successes (Ch8 Example 8-3). The metric that exposes a
        cheap-but-unreliable model: wasted spend on failed calls is amortized
        over the successful ones."""
        calls = self._for_node(node_name)
        total_cost = sum(i.cost_usd for i in calls)
        successes = sum(1 for i in calls if i.success)
        return total_cost / max(successes, 1)

    def success_rate(self, node_name: str) -> float:
        calls = self._for_node(node_name)
        if not calls:
            return 0.0
        return sum(1 for i in calls if i.success) / len(calls)

    def p_latency(self, node_name: str, pct: float = 95.0) -> float:
        calls = sorted(i.latency_ms for i in self._for_node(node_name))
        if not calls:
            return 0.0
        k = min(len(calls) - 1, int(round((pct / 100.0) * (len(calls) - 1))))
        return calls[k]

    def node_report(self, node_name: str) -> dict[str, Any]:
        calls = self._for_node(node_name)
        return {
            "node": node_name,
            "n_calls": len(calls),
            "success_rate": round(self.success_rate(node_name), 4),
            "cost_per_success": round(self.cost_per_success(node_name), 6),
            "total_cost_usd": round(sum(i.cost_usd for i in calls), 6),
            "p95_latency_ms": round(self.p_latency(node_name, 95.0), 1),
        }


# --- Per-node evaluation sets (Ch8 Example 8-4) -----------------------------
# required_accuracy and failure_weight are book figures. failure_weight keys are
# "<gold>_as_<prediction>"; a P1 misclassified as P3 is 10x worse than the reverse.
EVAL_SETS: dict[str, dict[str, Any]] = {
    "AlertClassifier": {
        "source": "production_alerts_2024_q4",
        "n_samples": 2000,
        "labels": "human_annotated_severity",
        "required_accuracy": 0.99,
        "failure_weight": {"P1_as_P3": 10.0, "P3_as_P1": 1.0},
    },
    "QueryAnalyst": {
        "source": "production_queries_2024_q4",
        "n_samples": 500,
        "labels": "human_annotated_complexity",
        "required_accuracy": 0.90,
        "failure_weight": {"complex_as_simple": 2.0, "simple_as_complex": 0.5},
    },
}


def evaluate_candidate(predictions: list[tuple[str, str]], eval_set: dict[str, Any]) -> dict[str, Any]:
    """Run a candidate model's predictions against a node-specific eval set
    (Ch8 Example 8-4). `predictions` is a list of (gold_label, predicted_label).

    Returns accuracy, meets_threshold, and a weighted_error_rate that applies
    the domain-specific failure weights — the piece a generic accuracy metric
    cannot capture.
    """
    if not predictions:
        return {"accuracy": 0.0, "meets_threshold": False, "weighted_error_rate": 0.0}
    weights = eval_set["failure_weight"]
    correct = 0
    weighted_error = 0.0
    for gold, pred in predictions:
        if gold == pred:
            correct += 1
        else:
            weighted_error += weights.get(f"{gold}_as_{pred}", 1.0)
    n = len(predictions)
    accuracy = correct / n
    return {
        "source": eval_set.get("source"),
        "n": n,
        "accuracy": round(accuracy, 4),
        "required_accuracy": eval_set["required_accuracy"],
        "meets_threshold": accuracy >= eval_set["required_accuracy"],
        "weighted_error_rate": round(weighted_error / n, 4),
    }


def score_policy(tracker: CostTracker) -> dict[str, Any]:
    """Score a whole routing policy: per-node cost-per-success + a blended cost
    per completed task across the pipeline."""
    nodes = sorted({i.node_name for i in tracker.invocations})
    reports = [tracker.node_report(n) for n in nodes]
    total_cost = sum(r["total_cost_usd"] for r in reports)
    total_success = sum(1 for i in tracker.invocations if i.success)
    return {
        "nodes": reports,
        "pipeline_total_cost_usd": round(total_cost, 6),
        "pipeline_cost_per_success": round(total_cost / max(total_success, 1), 6),
    }


def compare_cost_per_success(
    cheap_cost: float, cheap_success_rate: float,
    reliable_cost: float, reliable_success_rate: float,
    n_calls: int = 1000,
) -> dict[str, Any]:
    """Demonstrate the book's claim: raw per-call price hides the true cost.

    A moderately cheaper model that fails often can cost MORE per successful
    completion than a slightly pricier reliable model, because the spend on
    failed calls is amortized over fewer successes.
    """
    def cps(cost: float, rate: float) -> float:
        successes = max(int(round(rate * n_calls)), 1)
        return (cost * n_calls) / successes

    cheap_cps = cps(cheap_cost, cheap_success_rate)
    reliable_cps = cps(reliable_cost, reliable_success_rate)
    return {
        "n_calls": n_calls,
        "cheap": {"per_call": cheap_cost, "success_rate": cheap_success_rate,
                  "cost_per_success": round(cheap_cps, 6)},
        "reliable": {"per_call": reliable_cost, "success_rate": reliable_success_rate,
                     "cost_per_success": round(reliable_cps, 6)},
        "cheaper_per_call": "cheap" if cheap_cost < reliable_cost else "reliable",
        "cheaper_per_success": "cheap" if cheap_cps < reliable_cps else "reliable",
        "lesson": "The model that is cheaper per call is not always cheaper per "
                  "successful completion (Ch8).",
    }
