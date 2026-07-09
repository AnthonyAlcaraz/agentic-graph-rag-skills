"""
Graduated Validation Protocol + entropy-collapse guard (Ch7).

The evolutionary loop generates candidate improvements continuously; not all of
them should reach production. The RPO spine (Recursion, Provenance, Optimization)
is the safety envelope. This module implements the Optimization property: the
Graduated Validation Protocol (GVP), a tiered gate that assigns each candidate a
risk tier and applies the matching scrutiny:

- Tier 1 canary release: 1% traffic, statistically significant target lift with
  no core-KPI degradation, automatic rollback.
- Tier 2 staging gauntlet: multi-objective utility U = w_accuracy*accuracy +
  w_cost*(1-cost) + w_safety*safety_score, passes only net-positive with no
  safety regression.
- Tier 3 airlock protocol: sandboxed, automated risk/reward report, escalated
  for HUMAN review (approve / reject / modify) before proceeding.

The second half is the entropy-collapse guard (Kepler dual-store, OpenAI 2026):
Knowledge is human-authored / version-controlled; Learnings are agent-generated
/ ephemeral. A daily garbage-collection graph traversal removes a Learning if
its issue was promoted to Knowledge, if a newer higher-confidence learning
contradicts it, or if it has not been retrieved in 30 days.

Production swap: this in-memory implementation is the dev-time stand-in. Each
gate's scoring seam is marked with a TODO(production) comment naming the real
component (staging benchmark harness, safety/alignment suite, sandbox executor,
graph-store garbage collector). The API contract is stable; the substrate is the
seam.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


TIERS = ("TIER1_CANARY", "TIER2_STAGING", "TIER3_AIRLOCK")

# Statistical-significance threshold for the canary target metric (Ch7 Tier 1).
CANARY_ALPHA = 0.05

# Kepler dual-store defaults (Ch7 Tip): 30-day TTL, daily GC pass.
DEFAULT_TTL_DAYS = 30

# Promotion-health threshold (Ch7 Tip): below this the criteria are too strict.
PROMOTION_MIN_RATE = 0.10


# ---------------------------------------------------------------------------
# GateResult
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    """Outcome of one validation gate.

    `requires_human` marks the Tier 3 airlock escalation. `passed` is False
    while a Tier 3 decision is still pending (human_decision is None).
    """

    passed: bool
    tier: str
    reasons: List[str] = field(default_factory=list)
    requires_human: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Tier assignment (RPO Optimization: route each candidate to its scrutiny)
# ---------------------------------------------------------------------------


def assign_tier(candidate: Dict[str, Any]) -> str:
    """Assign a risk tier to a candidate change.

    candidate carries {intervention_type, novel, touches_safety, new_tool}.

    Tier 3 overrides everything: a change that modifies safety protocols,
    integrates a brand-new tool, or is otherwise novel goes to the airlock
    regardless of its nominal intervention_type (Ch7 Tier 3 definition).
    Otherwise: prompt_refinement / hyperparameter -> Tier 1;
    fine_tune / tool_integration -> Tier 2.
    """
    if candidate.get("touches_safety") or candidate.get("new_tool") or candidate.get("novel"):
        return "TIER3_AIRLOCK"

    intervention = candidate.get("intervention_type")
    if intervention in ("prompt_refinement", "hyperparameter"):
        return "TIER1_CANARY"
    if intervention in ("fine_tune", "tool_integration"):
        return "TIER2_STAGING"

    raise ValueError(
        f"cannot assign tier: unknown intervention_type {intervention!r} "
        f"and no Tier 3 escalation flag set"
    )


# ---------------------------------------------------------------------------
# Tier 1: canary release
# ---------------------------------------------------------------------------


def canary_gate(
    metrics: Dict[str, Any],
    min_lift: float = 0.0,
    kpi_regression_tol: float = 0.0,
) -> GateResult:
    """Tier 1 canary gate.

    metrics carries {target_lift, target_pvalue, kpi_deltas}. Passes iff the
    target metric shows a statistically significant improvement (target_lift
    > min_lift AND target_pvalue < CANARY_ALPHA) with NO core-KPI degradation
    (no kpi_delta below -kpi_regression_tol). Any failure is an automatic
    rollback.

    kpi_deltas are normalized so that positive means improvement and negative
    means degradation (0.0 = unchanged). Express a lower-is-better KPI such as
    latency or cost in this normalized form before passing it.
    """
    reasons: List[str] = []

    target_lift = metrics.get("target_lift")
    target_pvalue = metrics.get("target_pvalue")
    kpi_deltas: Dict[str, float] = metrics.get("kpi_deltas", {}) or {}

    if target_lift is None or target_pvalue is None:
        raise ValueError("canary metrics require target_lift and target_pvalue")

    lift_ok = target_lift > min_lift
    sig_ok = target_pvalue < CANARY_ALPHA

    if not lift_ok:
        reasons.append(
            f"target_lift {target_lift} not above min_lift {min_lift}; auto-rollback"
        )
    if not sig_ok:
        reasons.append(
            f"target_pvalue {target_pvalue} not below alpha {CANARY_ALPHA}; "
            f"improvement not statistically significant; auto-rollback"
        )

    regressed = {
        name: delta
        for name, delta in kpi_deltas.items()
        if delta < -kpi_regression_tol
    }
    if regressed:
        reasons.append(
            f"core KPI degradation beyond tolerance {kpi_regression_tol}: "
            f"{regressed}; auto-rollback"
        )

    passed = lift_ok and sig_ok and not regressed
    if passed:
        reasons.append(
            f"significant lift {target_lift} (p={target_pvalue}) with no KPI regression"
        )
    return GateResult(passed=passed, tier="TIER1_CANARY", reasons=reasons)


# ---------------------------------------------------------------------------
# Tier 2: staging gauntlet
# ---------------------------------------------------------------------------


def staging_utility(scores: Dict[str, Any], weights: Dict[str, Any]) -> float:
    """Multi-objective utility U = w_accuracy*accuracy + w_cost*(1-cost) +
    w_safety*safety_score (Ch7 Tier 2).

    scores requires {accuracy, cost, safety_score}; weights requires
    {w_accuracy, w_cost, w_safety}.
    """
    for key in ("accuracy", "cost", "safety_score"):
        if key not in scores:
            raise ValueError(f"scores missing required field {key!r}")
    for key in ("w_accuracy", "w_cost", "w_safety"):
        if key not in weights:
            raise ValueError(f"weights missing required field {key!r}")

    return (
        weights["w_accuracy"] * scores["accuracy"]
        + weights["w_cost"] * (1.0 - scores["cost"])
        + weights["w_safety"] * scores["safety_score"]
    )


def staging_gate(
    scores: Dict[str, Any],
    weights: Dict[str, Any],
    min_utility: float = 0.0,
    baseline: Optional[Dict[str, Any]] = None,
) -> GateResult:
    """Tier 2 staging gate.

    A change passes only if it shows net-positive improvement in the
    multi-objective utility function AND has no safety regression. When a
    `baseline` scores dict is supplied the candidate utility must exceed the
    baseline utility (net-positive); otherwise it must exceed `min_utility`.

    A safety regression fails the gate even when utility is high (no safety
    regressions is a hard constraint in Ch7 Tier 2).
    """
    # TODO(production): scores come from the staging benchmark suite +
    # regression suite (catastrophic forgetting) + safety/alignment suite
    # (bias drift) + performance suite (latency/cost). Swap this dict for the
    # aggregated staging-run report.
    reasons: List[str] = []

    utility = staging_utility(scores, weights)

    if baseline is not None:
        threshold = staging_utility(baseline, weights)
        threshold_label = f"baseline utility {threshold:.4f}"
    else:
        threshold = min_utility
        threshold_label = f"min_utility {threshold:.4f}"

    utility_ok = utility > threshold
    safety_regression = bool(scores.get("safety_regression", False))

    if not utility_ok:
        reasons.append(
            f"utility {utility:.4f} not net-positive over {threshold_label}"
        )
    if safety_regression:
        reasons.append("safety regression present; hard fail regardless of utility")

    passed = utility_ok and not safety_regression
    if passed:
        reasons.append(
            f"utility {utility:.4f} net-positive over {threshold_label}, no safety regression"
        )
    return GateResult(passed=passed, tier="TIER2_STAGING", reasons=reasons)


# ---------------------------------------------------------------------------
# Tier 3: airlock protocol
# ---------------------------------------------------------------------------


def airlock_gate(
    risk_reward: Dict[str, Any],
    human_decision: Optional[str],
) -> GateResult:
    """Tier 3 airlock gate.

    The candidate is sandboxed, an automated risk/reward report is generated,
    and the change is escalated for human review. requires_human is always
    True. The change passes only on human_decision == "approve"; it is pending
    (passed False, requires_human True) while human_decision is None; a
    "reject" or "modify" decision does not pass.
    """
    # TODO(production): run the candidate in a sandboxed isolated environment
    # and generate the automated risk/reward report; this dict stands in for
    # that report.
    reasons: List[str] = []

    report = json.dumps(risk_reward, sort_keys=True)[:200]
    reasons.append(f"sandboxed; automated risk/reward report: {report}")

    if human_decision is None:
        reasons.append("awaiting human review (approve / reject / modify)")
        return GateResult(
            passed=False,
            tier="TIER3_AIRLOCK",
            reasons=reasons,
            requires_human=True,
        )

    decision = str(human_decision).lower()
    if decision == "approve":
        reasons.append("human expert approved")
        passed = True
    elif decision == "modify":
        reasons.append("human expert requested modification; does not proceed as-is")
        passed = False
    else:
        reasons.append(f"human expert decision {human_decision!r}; does not proceed")
        passed = False

    return GateResult(
        passed=passed,
        tier="TIER3_AIRLOCK",
        reasons=reasons,
        requires_human=True,
    )


# ---------------------------------------------------------------------------
# Orchestration: assign then run the matching gate
# ---------------------------------------------------------------------------


def graduated_validation(candidate: Dict[str, Any]) -> GateResult:
    """Assign the candidate a tier, then run the matching gate.

    Reads the gate inputs from fields on the candidate:
    - Tier 1: candidate["metrics"] (+ optional min_lift, kpi_regression_tol)
    - Tier 2: candidate["scores"], candidate["weights"] (+ optional baseline,
      min_utility)
    - Tier 3: candidate["risk_reward"], candidate.get("human_decision")
    """
    tier = assign_tier(candidate)

    if tier == "TIER1_CANARY":
        metrics = candidate.get("metrics")
        if metrics is None:
            raise ValueError("Tier 1 candidate requires a 'metrics' field")
        return canary_gate(
            metrics,
            min_lift=candidate.get("min_lift", 0.0),
            kpi_regression_tol=candidate.get("kpi_regression_tol", 0.0),
        )

    if tier == "TIER2_STAGING":
        scores = candidate.get("scores")
        weights = candidate.get("weights")
        if scores is None or weights is None:
            raise ValueError("Tier 2 candidate requires 'scores' and 'weights' fields")
        return staging_gate(
            scores,
            weights,
            min_utility=candidate.get("min_utility", 0.0),
            baseline=candidate.get("baseline"),
        )

    # TIER3_AIRLOCK
    risk_reward = candidate.get("risk_reward", {})
    return airlock_gate(risk_reward, candidate.get("human_decision"))


# ---------------------------------------------------------------------------
# RPO Provenance: source control for thought
# ---------------------------------------------------------------------------


def provenance_signature(candidate: Dict[str, Any]) -> str:
    """Deterministic content signature for the immutable ledger (RPO
    Provenance property: every change cryptographically signed).

    Production swap: replace this SHA-256 content hash with a real signing key
    and append the entry to an append-only ledger for instant rollback.
    """
    # TODO(production): swap for keyed signing + append to immutable ledger.
    payload = json.dumps(candidate, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Entropy-collapse guard: Kepler dual-store garbage collection
# ---------------------------------------------------------------------------


@dataclass
class Learning:
    """An agent-generated, ephemeral Learning node (Kepler dual-store).

    Distinguished from human-authored Knowledge by provenance. Subject to the
    daily garbage-collection traversal.
    """

    id: str
    confidence: float
    last_accessed_days: int
    resolved_promoted: bool = False
    contradicted_by_higher_conf: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Learning":
        return cls(
            id=d["id"],
            confidence=float(d["confidence"]),
            last_accessed_days=int(d["last_accessed_days"]),
            resolved_promoted=bool(d.get("resolved_promoted", False)),
            contradicted_by_higher_conf=bool(d.get("contradicted_by_higher_conf", False)),
        )


def garbage_collect(
    learnings: List[Learning],
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> Tuple[List[Learning], List[Learning]]:
    """Daily GC traversal of the Learnings subgraph (Kepler, OpenAI 2026).

    Removes a Learning node if ANY of the three conditions holds:
    1. the underlying issue was resolved and promoted (its resolution node is
       now connected to a Knowledge node),
    2. it contradicts a newer learning with higher confidence,
    3. it has not been retrieved in `ttl_days` (last_accessed decayed past
       threshold).

    Returns (kept, removed).
    """
    kept: List[Learning] = []
    removed: List[Learning] = []
    for lrn in learnings:
        if lrn.resolved_promoted:
            removed.append(lrn)
        elif lrn.contradicted_by_higher_conf:
            removed.append(lrn)
        elif lrn.last_accessed_days > ttl_days:
            removed.append(lrn)
        else:
            kept.append(lrn)
    return kept, removed


def promotion_rate(total_learnings: int, promoted: int) -> float:
    """Learnings-to-Knowledge promotion rate over the TTL window."""
    if total_learnings <= 0:
        return 0.0
    return promoted / total_learnings


def promotion_health(rate: float) -> str:
    """Flag the promotion rate (Ch7 Tip: below 10% the criteria are too strict
    and valuable patterns are being discarded).
    """
    if rate < PROMOTION_MIN_RATE:
        return "criteria too strict"
    return "healthy"
