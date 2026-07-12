"""
Memory consistency model selection for multi-agent systems, distilled from
Ch4 "Memory consistency models for agent coordination" + "Cache sharing in
multi-agent systems".

The chapter's central claim: when Agent A writes a fact to shared memory, WHEN
does Agent B see it? Getting this wrong produces agents that contradict each
other, overwrite each other's conclusions, or act on stale information. This is
CAP (consistency vs availability) applied PER agent-coordination operation, not
once globally. The chapter's rule: default to causal, escalate to strong only
for decision points that trigger irreversible actions.

Four consistency models, chosen per operation:

  strong            linearizable; every agent sees the latest write before any
                    proceeds. A sync barrier after every write. Needed when
                    agents act on shared AUTHORITATIVE state (locks, budgets,
                    inventory) or make safety-critical irreversible decisions.
  causal            causally-related writes ordered; unrelated updates may
                    arrive out of sequence. The practical default for
                    collaborating agents that build on each other's findings.
  read_your_writes  an agent always sees its OWN writes; other agents' writes
                    may lag. Session memory for a single agent's continuity.
  eventual          cheapest; all agents converge eventually, but not when.
                    Fine when staleness is tolerable (background enrichment,
                    literature accumulation reconciled at a final synthesis).

Cache sharing across agents is the concrete failure surface: a stale cache ->
divergent decisions. detect_cache_divergence flags agents acting on a cached
read older than a committed write it depends on.

Pure Python, stdlib only. No datastore required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


MODELS = ("strong", "causal", "read_your_writes", "eventual")

# The operation requirement axes the caller weights (0..3). These ARE the
# scoring features: recommend/score take a weighted dot-product of these
# weights with each model's fitness on the same axes.
REQS = ("shared_authoritative_state", "conflict_intolerance",
        "staleness_budget", "collaboration", "self_session_only")

# How well each model serves each requirement axis, 0..3 (higher == better
# fit). Distilled from the chapter:
#   - strong best when agents act on shared authoritative state / cannot
#     tolerate conflict (the medical drug-interaction barrier example).
#   - causal best when agents build on each other's causally-linked writes.
#   - read_your_writes best when an agent needs its own session continuity.
#   - eventual best when staleness is acceptable (knowledge accumulation).
REQ_MODEL_FIT: Dict[str, Dict[str, int]] = {
    "strong": {
        "shared_authoritative_state": 3, "conflict_intolerance": 3,
        "staleness_budget": 0, "collaboration": 2, "self_session_only": 1,
    },
    "causal": {
        "shared_authoritative_state": 1, "conflict_intolerance": 1,
        "staleness_budget": 1, "collaboration": 3, "self_session_only": 2,
    },
    "read_your_writes": {
        "shared_authoritative_state": 1, "conflict_intolerance": 1,
        "staleness_budget": 2, "collaboration": 1, "self_session_only": 3,
    },
    "eventual": {
        "shared_authoritative_state": 0, "conflict_intolerance": 0,
        "staleness_budget": 3, "collaboration": 1, "self_session_only": 1,
    },
}

# Descriptive profile across four consistency axes, 0..3. Not the scoring
# table -- this is the human-readable characterization surfaced by `score`.
#   freshness_guarantee: how current a read is guaranteed to be.
#   coordination_cost:   synchronization overhead paid per write (higher costs more).
#   availability:        can an agent proceed during a partition / lag.
#   staleness_tolerance: how much stale-read tolerance the model assumes.
MODEL_PROFILE: Dict[str, Dict[str, int]] = {
    "strong":           {"freshness_guarantee": 3, "coordination_cost": 3,
                         "availability": 1, "staleness_tolerance": 0},
    "causal":           {"freshness_guarantee": 2, "coordination_cost": 2,
                         "availability": 2, "staleness_tolerance": 2},
    "read_your_writes": {"freshness_guarantee": 2, "coordination_cost": 1,
                         "availability": 3, "staleness_tolerance": 2},
    "eventual":         {"freshness_guarantee": 1, "coordination_cost": 0,
                         "availability": 3, "staleness_tolerance": 3},
}

PROFILE_AXES = ("freshness_guarantee", "coordination_cost",
                "availability", "staleness_tolerance")


@dataclass
class Operation:
    """One agent-coordination operation and its consistency requirements.

    Each weight is 0..3. Consistency is chosen PER operation (Ch4), so this
    describes a single coordination point, not a whole system.

    shared_authoritative_state: agents act on a shared authoritative value --
        a lock, a budget, an inventory count -- where two agents reading
        different versions is a correctness bug.
    conflict_intolerance: concurrent conflicting decisions are unacceptable
        (the drug-interaction barrier: every agent must see the interaction
        before any recommends treatment).
    staleness_budget: how much stale-read tolerance the operation has
        (0 = none, 3 = high). High budget favors cheap eventual consistency.
    collaboration: agents build on each other's causally-related writes; if
        A's conclusion depends on B's finding, readers of A must also see B.
    self_session_only: a single agent needs continuity over its own writes;
        other agents' writes are not on this operation's critical path.
    """
    shared_authoritative_state: int = 0
    conflict_intolerance: int = 0
    staleness_budget: int = 0
    collaboration: int = 0
    self_session_only: int = 0

    def as_weights(self) -> Dict[str, int]:
        return {r: int(getattr(self, r)) for r in REQS}


def score_models(op: Operation) -> List[Tuple[str, float]]:
    """Weighted dot-product of operation requirement weights and per-model
    fitness. Returns [(model, score), ...] sorted descending.
    """
    weights = op.as_weights()
    scored: List[Tuple[str, float]] = []
    for model in MODELS:
        fit = REQ_MODEL_FIT[model]
        total = float(sum(weights[r] * fit[r] for r in REQS))
        scored.append((model, total))
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return scored


def recommend_model(op: Operation) -> Dict[str, Any]:
    """Pick a consistency model for one operation and explain it.

    Surfaces `escalate_to_strong` when the default recommendation is not strong
    but the operation touches shared authoritative state or is conflict-
    intolerant -- the chapter's rule: default to causal, escalate individual
    irreversible decision points to strong.
    """
    scored = score_models(op)
    top_model, top_score = scored[0]
    escalate = (
        top_model != "strong"
        and max(op.shared_authoritative_state, op.conflict_intolerance) >= 1
    )
    rec: Dict[str, Any] = {
        "recommended": top_model,
        "scores": dict(scored),
        "rationale": _RATIONALE[top_model],
        "profile": MODEL_PROFILE[top_model],
        "escalate_to_strong": escalate,
    }
    if escalate:
        rec["escalation_note"] = (
            f"Default is {top_model}, but this operation touches shared "
            "authoritative state / conflict-intolerant decisions. Per Ch4, "
            "escalate the irreversible decision points to strong consistency "
            "even though the workflow default stays cheaper."
        )
    return rec


_RATIONALE = {
    "strong": ("Linearizable: every agent sees the latest write before any "
               "proceeds. Required for shared authoritative state (locks, "
               "budgets, inventory) and safety-critical irreversible actions. "
               "Pays a synchronization barrier after every write."),
    "causal": ("The practical default: causally-related writes are ordered, so "
               "an agent reading A's conclusion also sees the B finding it "
               "depended on. Unrelated updates may lag. Escalate to strong for "
               "irreversible decision points."),
    "read_your_writes": ("Session memory: a single agent always sees its own "
                         "writes; other agents' writes may arrive later. Use "
                         "for per-agent continuity, not cross-agent authority."),
    "eventual": ("Cheapest: all agents converge eventually, but not when. "
                 "Tolerable when no single fact is safety-critical and a final "
                 "synthesis step reconciles disagreement (background "
                 "enrichment, literature accumulation)."),
}


# ---------------------------------------------------------------------------
# Cache-sharing divergence. Ch4 "Cache sharing in multi-agent systems": without
# a cache-sharing protocol, an agent acts on a cached read that a newer
# committed write has already superseded -- divergent, sometimes contradictory
# decisions. This detector flags exactly that: a cached read older than the
# latest committed write on the same key.
# ---------------------------------------------------------------------------

def detect_cache_divergence(
    agent_writes: List[Dict[str, Any]],
    cache_snapshots: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Flag agents acting on stale cache.

    agent_writes:    committed writes, each {key, timestamp, [value], [agent]}.
    cache_snapshots: per-agent cached reads, each {agent, key, cached_at} --
                     the timestamp of the version the agent currently holds.

    Returns a list of divergence warnings, one per stale snapshot:
        {agent, key, cached_at, latest_write_at, staleness_gap}
    A snapshot is stale when it cached a version older than the latest
    committed write on that key.
    """
    latest_write: Dict[Any, float] = {}
    for w in agent_writes:
        key = w["key"]
        ts = float(w["timestamp"])
        if key not in latest_write or ts > latest_write[key]:
            latest_write[key] = ts

    warnings: List[Dict[str, Any]] = []
    for snap in cache_snapshots:
        key = snap["key"]
        if key not in latest_write:
            continue
        cached_at = float(snap["cached_at"])
        newest = latest_write[key]
        if cached_at < newest:
            warnings.append({
                "agent": snap.get("agent", "unknown"),
                "key": key,
                "cached_at": cached_at,
                "latest_write_at": newest,
                "staleness_gap": newest - cached_at,
            })
    warnings.sort(key=lambda w: (-w["staleness_gap"], str(w["agent"])))
    return warnings
