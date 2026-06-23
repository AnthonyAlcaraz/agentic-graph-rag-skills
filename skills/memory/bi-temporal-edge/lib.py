"""
Bi-temporal edge primitive for agentic graph memory.

Implements the Ch4 Example 4-2 TemporalEdge with the HINDSIGHT (Latimer et al.,
2025) typed-link + traversal-weight extension. Pure Python, no external deps,
deterministic for testing.

Production swap notes:
    - The in-memory edge store is a list. Production should use a graph
      database with bi-temporal indexes (Graphiti / Neo4j with temporal
      plugin / FalkorDB). The query primitives (`as_of`, `history`,
      `weighted_traverse`) are stable; the storage layer is the seam.
    - `weighted_traverse` here implements one-hop scoring for clarity. The
      chapter's full HINDSIGHT spreading-activation does multi-hop with
      decay. Replace the body of `weighted_traverse` without changing the
      signature.
    - The `now()` function is injected for testability. Production uses
      `datetime.now(timezone.utc)`; tests inject fixed clocks.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, Dict, Any


# ---------------------------------------------------------------------------
# Link types and default traversal weights (HINDSIGHT, Latimer et al. 2025)
# ---------------------------------------------------------------------------

LINK_TYPES = ("entity", "causal", "semantic", "temporal")

DEFAULT_WEIGHTS: Dict[str, float] = {
    "entity": 1.2,    # μ > 1: prefer entity links during traversal
    "causal": 1.5,    # μ > 1: prefer causal links most strongly
    "semantic": 0.9,  # μ ≤ 1: weak semantic links de-prioritized
    "temporal": 0.7,  # μ ≤ 1: long-range temporal links de-prioritized further
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# TemporalEdge — Ch4 Example 4-2 + HINDSIGHT typed-link extension
# ---------------------------------------------------------------------------

@dataclass
class TemporalEdge:
    source: str
    target: str
    relationship: str
    value: Any = None                            # the fact the edge encodes (e.g. "m5.xlarge")
    valid_from: datetime = field(default_factory=_utc_now)
    valid_until: Optional[datetime] = None       # None = currently valid
    ingested_at: datetime = field(default_factory=_utc_now)
    invalidation_reason: Optional[str] = None
    link_type: str = "entity"                    # HINDSIGHT
    weight: float = 1.0                          # HINDSIGHT (overrides DEFAULT_WEIGHTS if set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def was_valid_at(self, timestamp: datetime) -> bool:
        """Check if relationship was valid at a specific time (Ch4 Example 4-2)."""
        if timestamp < self.valid_from:
            return False
        if self.valid_until is None:
            return True
        return timestamp < self.valid_until

    def is_currently_valid(self) -> bool:
        return self.valid_until is None

    def ingestion_lag(self) -> timedelta:
        """Time between when the fact became valid and when the system learned it.

        Non-negative. Positive lag means the agent learned about it after the
        fact — surface this in the agent's reasoning context (Ch4 worked
        example: "If the agent made a decision on Wednesday based on stale
        data, ingested_at will tell you...").
        """
        return self.ingested_at - self.valid_from

    def effective_weight(self) -> float:
        """Combine explicit weight with link-type default."""
        return self.weight * DEFAULT_WEIGHTS.get(self.link_type, 1.0)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in ("valid_from", "valid_until", "ingested_at"):
            if d[k] is not None:
                d[k] = d[k].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TemporalEdge":
        d = dict(d)
        for k in ("valid_from", "valid_until", "ingested_at"):
            if d.get(k):
                d[k] = datetime.fromisoformat(d[k])
        return cls(**d)


# ---------------------------------------------------------------------------
# Mutation primitives — create / invalidate / supersede
# ---------------------------------------------------------------------------

def create_edge(
    source: str,
    target: str,
    relationship: str,
    value: Any = None,
    valid_from: Optional[datetime] = None,
    ingested_at: Optional[datetime] = None,
    link_type: str = "entity",
    weight: float = 1.0,
    metadata: Optional[Dict[str, Any]] = None,
    now_fn: Callable[[], datetime] = _utc_now,
) -> TemporalEdge:
    """Create a new bi-temporal edge.

    Defaults: valid_from = ingested_at = now(); valid_until = None (currently valid).
    Pass valid_from / ingested_at explicitly to backfill history.
    """
    if link_type not in LINK_TYPES:
        raise ValueError(f"link_type must be one of {LINK_TYPES}, got {link_type}")
    now = now_fn()
    return TemporalEdge(
        source=source,
        target=target,
        relationship=relationship,
        value=value,
        valid_from=valid_from or now,
        ingested_at=ingested_at or now,
        link_type=link_type,
        weight=weight,
        metadata=metadata or {},
    )


def invalidate(edge: TemporalEdge, reason: str, now_fn: Callable[[], datetime] = _utc_now) -> TemporalEdge:
    """Mark edge as no longer valid (Ch4 Example 4-2).

    `reason` is required and must be non-empty — the audit trail is the whole
    point. If the edge is already invalidated, raises ValueError.
    """
    if not reason or not reason.strip():
        raise ValueError("invalidation reason must be non-empty (audit trail discipline)")
    if edge.valid_until is not None:
        raise ValueError(f"edge {edge.id} is already invalidated at {edge.valid_until}")
    edge.valid_until = now_fn()
    edge.invalidation_reason = reason.strip()
    return edge


def supersede(
    old_edge: TemporalEdge,
    new_value: Any,
    reason: str = "superseded by new value",
    edges: Optional[List[TemporalEdge]] = None,
    now_fn: Callable[[], datetime] = _utc_now,
) -> TemporalEdge:
    """Invalidate the old edge AND create a new edge with the new value.

    Atomic semantically (both operations succeed or the supersede is rejected).
    If `edges` is passed (the edge store), the new edge is appended to it.
    """
    invalidate(old_edge, reason, now_fn=now_fn)
    new_edge = create_edge(
        source=old_edge.source,
        target=old_edge.target,
        relationship=old_edge.relationship,
        value=new_value,
        link_type=old_edge.link_type,
        weight=old_edge.weight,
        metadata={**old_edge.metadata, "supersedes": old_edge.id},
        now_fn=now_fn,
    )
    if edges is not None:
        edges.append(new_edge)
    return new_edge


# ---------------------------------------------------------------------------
# Query primitives — as_of / history / ingestion_lag / weighted_traverse
# ---------------------------------------------------------------------------

def as_of(
    source: str,
    relationship: str,
    timestamp: datetime,
    edges: List[TemporalEdge],
) -> Optional[TemporalEdge]:
    """Return the edge that was valid at `timestamp` for (source, relationship).

    At most one edge can be valid at any timestamp for a given (source, rel)
    pair — if more are returned, the invariant is broken (data corruption).
    """
    matches = [
        e for e in edges
        if e.source == source
        and e.relationship == relationship
        and e.was_valid_at(timestamp)
    ]
    if len(matches) > 1:
        raise ValueError(
            f"data corruption: {len(matches)} edges valid at {timestamp.isoformat()} "
            f"for ({source}, {relationship}). Invariant: at most one valid edge per "
            f"(source, rel) at any timestamp. Run consistency check."
        )
    return matches[0] if matches else None


def history(
    node: str,
    edges: List[TemporalEdge],
    relationship: Optional[str] = None,
) -> List[TemporalEdge]:
    """Return all edges sourced from `node`, sorted by valid_from ascending.

    Optionally filter by relationship type. Returns the full evolution —
    each historical state appears once.
    """
    result = [e for e in edges if e.source == node]
    if relationship is not None:
        result = [e for e in result if e.relationship == relationship]
    result.sort(key=lambda e: e.valid_from)
    return result


def ingestion_lag(edge: TemporalEdge) -> timedelta:
    """Convenience for `edge.ingestion_lag()`. Non-negative timedelta."""
    return edge.ingestion_lag()


def weighted_traverse(
    start: str,
    edges: List[TemporalEdge],
    depth: int = 1,
    at_time: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """One-hop weighted neighbor scoring (HINDSIGHT spreading-activation, depth=1).

    Returns neighbors of `start` reachable via valid edges (at `at_time` if
    given, else currently valid), scored by `effective_weight()`.

    Multi-hop is a stub: depth > 1 would compose weights along the path with
    a decay factor. The full HINDSIGHT spreading-activation is a follow-on.
    """
    if at_time is None:
        at_time = _utc_now()
    if depth != 1:
        raise NotImplementedError("multi-hop traversal is a follow-on; depth=1 ships here")
    neighbors = []
    for e in edges:
        if e.source != start:
            continue
        if not e.was_valid_at(at_time):
            continue
        neighbors.append({
            "edge_id": e.id,
            "target": e.target,
            "relationship": e.relationship,
            "link_type": e.link_type,
            "score": e.effective_weight(),
            "value": e.value,
        })
    neighbors.sort(key=lambda n: n["score"], reverse=True)
    return neighbors


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def save_edges(edges: List[TemporalEdge], path: str) -> None:
    with open(path, "w") as f:
        json.dump([e.to_dict() for e in edges], f, indent=2)


def load_edges(path: str) -> List[TemporalEdge]:
    with open(path) as f:
        return [TemporalEdge.from_dict(d) for d in json.load(f)]
