"""
Execution graph primitive (Ch7).

Foundation of Ch7 self-awareness. Immutable, queryable record of every
operation an agent performed for a specific query. Two-phase write captures
causal structure even on failure.

Production swap: this in-memory implementation is the dev-time stand-in for
an OpenTelemetry → Neo4j pipeline. The API contract is stable; the storage
substrate is the seam.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


NODE_TYPES = ("LLM_Call", "Tool_Invocation", "Retrieval", "Decision_Point")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ExecutionNode:
    id: str
    type: str                                    # one of NODE_TYPES
    started_at: datetime
    parent_id: Optional[str] = None              # None = root node
    input_payload: Optional[Any] = None
    output_payload: Optional[Any] = None
    completed_at: Optional[datetime] = None      # None = node never completed (failure / crash)
    latency_ms: Optional[float] = None
    token_count: Optional[int] = None
    cost_usd: Optional[float] = None
    error: Optional[str] = None                  # populated if node failed

    def is_completed(self) -> bool:
        return self.completed_at is not None and self.error is None

    def is_failed(self) -> bool:
        return self.error is not None or (self.completed_at is None and self.output_payload is None)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in ("started_at", "completed_at"):
            if d.get(k) is not None:
                d[k] = d[k].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ExecutionNode":
        d = dict(d)
        for k in ("started_at", "completed_at"):
            if d.get(k):
                d[k] = datetime.fromisoformat(d[k])
        return cls(**d)


class ExecutionGraph:
    """In-memory execution graph. Production: swap to Neo4j-backed store."""

    def __init__(self, execution_id: Optional[str] = None,
                 now_fn: Callable[[], datetime] = _utc_now):
        self.execution_id = execution_id or str(uuid.uuid4())
        self.now_fn = now_fn
        self.nodes: Dict[str, ExecutionNode] = {}

    # -- two-phase write --------------------------------------------------

    def begin_node(
        self,
        node_type: str,
        input_payload: Optional[Any] = None,
        parent_id: Optional[str] = None,
    ) -> str:
        """Phase 1: create node and link to parent.

        Captures structure even if the operation fails. Returns node_id;
        caller must pass this to `complete_node` (or `fail_node`) later.
        """
        if node_type not in NODE_TYPES:
            raise ValueError(f"node_type must be one of {NODE_TYPES}, got {node_type}")
        if parent_id is not None and parent_id not in self.nodes:
            raise ValueError(f"parent_id {parent_id} not in graph")
        node_id = str(uuid.uuid4())
        self.nodes[node_id] = ExecutionNode(
            id=node_id,
            type=node_type,
            started_at=self.now_fn(),
            parent_id=parent_id,
            input_payload=input_payload,
        )
        return node_id

    def complete_node(
        self,
        node_id: str,
        output_payload: Any,
        latency_ms: float,
        token_count: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Phase 2: fill in output + metrics."""
        if node_id not in self.nodes:
            raise KeyError(f"node {node_id} not found")
        n = self.nodes[node_id]
        if n.completed_at is not None:
            raise ValueError(f"node {node_id} already completed at {n.completed_at}")
        n.output_payload = output_payload
        n.completed_at = self.now_fn()
        n.latency_ms = latency_ms
        n.token_count = token_count
        n.cost_usd = cost_usd

    def fail_node(self, node_id: str, error: str) -> None:
        """Mark a node as failed. Preserves the partial record."""
        if node_id not in self.nodes:
            raise KeyError(f"node {node_id} not found")
        n = self.nodes[node_id]
        n.error = error
        n.completed_at = self.now_fn()

    # -- query ------------------------------------------------------------

    def query(self, predicate: Callable[[ExecutionNode], bool]) -> List[ExecutionNode]:
        """Cypher-like query: filter nodes by an arbitrary predicate.

        Example: `g.query(lambda n: n.type == "Tool_Invocation"
                          and n.latency_ms is not None and n.latency_ms > 3000)`
        """
        return [n for n in self.nodes.values() if predicate(n)]

    def causal_chain(self, node_id: str) -> List[ExecutionNode]:
        """Return ancestor chain from root to node_id (inclusive).

        Walks parent_id upward. Returns chain in root-first order.
        Raises KeyError if node_id missing.
        """
        if node_id not in self.nodes:
            raise KeyError(f"node {node_id} not found")
        chain = []
        current = self.nodes[node_id]
        chain.append(current)
        while current.parent_id is not None:
            if current.parent_id not in self.nodes:
                # Broken chain — surface, do not silently truncate
                raise ValueError(
                    f"causal chain broken: node {current.id} has parent "
                    f"{current.parent_id} which is not in graph"
                )
            current = self.nodes[current.parent_id]
            chain.append(current)
        chain.reverse()
        return chain

    def children(self, node_id: str) -> List[ExecutionNode]:
        return [n for n in self.nodes.values() if n.parent_id == node_id]

    def roots(self) -> List[ExecutionNode]:
        return [n for n in self.nodes.values() if n.parent_id is None]

    def failed(self) -> List[ExecutionNode]:
        return [n for n in self.nodes.values() if n.is_failed()]

    def incomplete(self) -> List[ExecutionNode]:
        return [n for n in self.nodes.values() if n.completed_at is None]

    # -- summary / diagnostics --------------------------------------------

    def summary(self) -> Dict[str, Any]:
        type_counts: Dict[str, int] = {}
        for n in self.nodes.values():
            type_counts[n.type] = type_counts.get(n.type, 0) + 1
        total_latency = sum(n.latency_ms or 0.0 for n in self.nodes.values())
        total_tokens = sum(n.token_count or 0 for n in self.nodes.values())
        total_cost = sum(n.cost_usd or 0.0 for n in self.nodes.values())
        return {
            "execution_id": self.execution_id,
            "node_count": len(self.nodes),
            "type_counts": type_counts,
            "total_latency_ms": total_latency,
            "total_token_count": total_tokens,
            "total_cost_usd": total_cost,
            "failed_node_count": len(self.failed()),
            "incomplete_node_count": len(self.incomplete()),
            "root_count": len(self.roots()),
        }

    # -- serialization ----------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "nodes": [n.to_dict() for n in self.nodes.values()],
        }

    @classmethod
    def from_snapshot(cls, snap: Dict[str, Any]) -> "ExecutionGraph":
        g = cls(execution_id=snap["execution_id"])
        for nd in snap["nodes"]:
            n = ExecutionNode.from_dict(nd)
            g.nodes[n.id] = n
        return g
