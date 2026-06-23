"""
Graphiti / Zep incremental-update pattern for agentic graph memory.

Implements Ch4 Example 4-8 with explicit locality verification. Pure Python.

Production swaps (documented at seams):
    - `Graph` is a dict-of-dicts; production should use a graph database
      (Neo4j / FalkorDB / KuzuDB). Methods that touch the graph are stable
      contracts; the storage layer is the seam.
    - `extract_entities` is a regex/keyword extractor here for determinism;
      production should swap in an LLM extractor at this seam.
    - `_fuzzy_match` is a token-overlap ratio for testability; production
      should swap in embedding-similarity at this seam.
"""

from __future__ import annotations

import json
import uuid
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Node:
    id: str
    name: str
    type: str
    aliases: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["created_at"] = d["created_at"].isoformat()
        d["updated_at"] = d["updated_at"].isoformat()
        return d


@dataclass
class Edge:
    source_id: str
    target_id: str
    relationship: str
    episode_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["created_at"] = d["created_at"].isoformat()
        return d


@dataclass
class ExtractedEntity:
    name: str
    type: str
    aliases: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolvedEntity:
    extracted: ExtractedEntity
    existing_node_id: Optional[str]  # None means new
    resolution_method: str           # canonical | alias | fuzzy | new


# ---------------------------------------------------------------------------
# Graph store
# ---------------------------------------------------------------------------

class Graph:
    """In-memory graph store. Production seam: replace with a real graph DB."""

    def __init__(self):
        self.nodes: Dict[str, Node] = {}                          # by id
        self.edges: List[Edge] = []
        # Indexes for O(1) entity resolution
        self._by_canonical: Dict[Tuple[str, str], str] = {}       # (name_lower, type) -> id
        self._by_alias: Dict[Tuple[str, str], str] = {}           # (alias_lower, type) -> id

    def add_node(self, name: str, type: str, aliases: Optional[List[str]] = None,
                 metadata: Optional[Dict[str, Any]] = None) -> Node:
        aliases = aliases or []
        node = Node(
            id=str(uuid.uuid4()),
            name=name,
            type=type,
            aliases=aliases,
            metadata=metadata or {},
        )
        self.nodes[node.id] = node
        self._by_canonical[(name.lower(), type)] = node.id
        for a in aliases:
            self._by_alias[(a.lower(), type)] = node.id
        return node

    def add_alias(self, node_id: str, alias: str) -> None:
        node = self.nodes[node_id]
        if alias not in node.aliases:
            node.aliases.append(alias)
            node.updated_at = _utc_now()
        self._by_alias[(alias.lower(), node.type)] = node_id

    def add_edge(self, source_id: str, target_id: str, relationship: str,
                 episode_id: Optional[str] = None,
                 metadata: Optional[Dict[str, Any]] = None) -> Edge:
        e = Edge(source_id=source_id, target_id=target_id, relationship=relationship,
                 episode_id=episode_id, metadata=metadata or {})
        self.edges.append(e)
        return e

    def neighbors(self, node_id: str) -> List[str]:
        """Adjacent node ids — for locality checks."""
        out = []
        for e in self.edges:
            if e.source_id == node_id:
                out.append(e.target_id)
            elif e.target_id == node_id:
                out.append(e.source_id)
        return out

    def snapshot(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_snapshot(cls, snap: Dict[str, Any]) -> "Graph":
        g = cls()
        for nd in snap["nodes"]:
            d = dict(nd)
            d["created_at"] = datetime.fromisoformat(d["created_at"])
            d["updated_at"] = datetime.fromisoformat(d["updated_at"])
            n = Node(**d)
            g.nodes[n.id] = n
            g._by_canonical[(n.name.lower(), n.type)] = n.id
            for a in n.aliases:
                g._by_alias[(a.lower(), n.type)] = n.id
        for ed in snap["edges"]:
            d = dict(ed)
            d["created_at"] = datetime.fromisoformat(d["created_at"])
            g.edges.append(Edge(**d))
        return g


# ---------------------------------------------------------------------------
# Pipeline — extract, resolve, incremental_update
# ---------------------------------------------------------------------------

# Simple regex-based extractor. Production swap: LLM-based extractor.
# Pattern: "<Type>:<Name>" or "<Type>:<Name>(<alias>)" or named entities
# from a registry.
ENTITY_PATTERN = re.compile(
    r"\b(?P<type>person|service|incident|deployment|region|team)"
    r":(?P<name>[A-Za-z0-9_\-.]+(?:\s+[A-Za-z0-9_\-.]+)*?)"
    r"(?:\((?P<alias>[A-Za-z0-9_\-., ]+?)\))?"
    r"(?=\s|$|[,!?;:]|$)", re.IGNORECASE,
)


def extract_entities(episode: str) -> List[ExtractedEntity]:
    """Pull entities from new episode text. Production: swap LLM extractor here."""
    found = []
    seen = set()
    for m in ENTITY_PATTERN.finditer(episode):
        type_ = m.group("type").lower()
        name = m.group("name").strip()
        if (type_, name.lower()) in seen:
            continue
        seen.add((type_, name.lower()))
        aliases = []
        if m.group("alias"):
            aliases = [a.strip() for a in m.group("alias").split(",")]
        found.append(ExtractedEntity(name=name, type=type_, aliases=aliases))
    return found


def _fuzzy_match(name: str, type_: str, graph: Graph, threshold: float = 0.6) -> Optional[str]:
    """Token-overlap fuzzy match. Production swap: embedding similarity."""
    name_tokens = set(name.lower().split())
    if not name_tokens:
        return None
    best_id = None
    best_score = 0.0
    for n in graph.nodes.values():
        if n.type != type_:
            continue
        cand_tokens = set(n.name.lower().split())
        if not cand_tokens:
            continue
        overlap = len(name_tokens & cand_tokens)
        union = len(name_tokens | cand_tokens)
        score = overlap / union if union else 0.0
        if score > best_score and score >= threshold:
            best_score = score
            best_id = n.id
    return best_id


def entity_resolution(extracted: List[ExtractedEntity], graph: Graph) -> List[ResolvedEntity]:
    """For each extracted entity, find existing node id (or None = new).

    Three-tier resolution order:
        1. canonical (exact name + type)  — O(1)
        2. alias (exact alias + type)     — O(1)
        3. fuzzy (token overlap >= 0.6)   — O(n_nodes_of_type) — production: ANN

    Resolution method is logged on the ResolvedEntity for diagnostics.
    """
    resolved = []
    for e in extracted:
        # 1. canonical
        cid = graph._by_canonical.get((e.name.lower(), e.type))
        if cid is not None:
            resolved.append(ResolvedEntity(extracted=e, existing_node_id=cid, resolution_method="canonical"))
            continue
        # 2. alias
        cid = graph._by_alias.get((e.name.lower(), e.type))
        if cid is not None:
            resolved.append(ResolvedEntity(extracted=e, existing_node_id=cid, resolution_method="alias"))
            continue
        # 3. fuzzy
        fid = _fuzzy_match(e.name, e.type, graph)
        if fid is not None:
            resolved.append(ResolvedEntity(extracted=e, existing_node_id=fid, resolution_method="fuzzy"))
            continue
        # new
        resolved.append(ResolvedEntity(extracted=e, existing_node_id=None, resolution_method="new"))
    return resolved


def incremental_update(
    resolved: List[ResolvedEntity],
    graph: Graph,
    episode_id: str,
    episode_text: Optional[str] = None,
) -> Set[str]:
    """Modify only the impacted neighborhood. Returns touched node ids.

    For each resolved entity:
        - if existing: add any new aliases (which previously failed canonical
          but are now associated to the existing node)
        - if new: create a node
    Then add edges between all entities mentioned in the same episode
    (co-occurrence within the episode) tagged with episode_id.
    """
    touched: Set[str] = set()
    nodes_for_episode = []
    for r in resolved:
        if r.existing_node_id is None:
            n = graph.add_node(
                name=r.extracted.name,
                type=r.extracted.type,
                aliases=r.extracted.aliases,
                metadata={"first_seen_episode": episode_id},
            )
            touched.add(n.id)
            nodes_for_episode.append(n.id)
        else:
            # Add any new aliases learned in this episode
            for a in r.extracted.aliases:
                if a.lower() != graph.nodes[r.existing_node_id].name.lower() \
                   and a not in graph.nodes[r.existing_node_id].aliases:
                    graph.add_alias(r.existing_node_id, a)
            touched.add(r.existing_node_id)
            nodes_for_episode.append(r.existing_node_id)
    # Add co-occurrence edges (one episode = one edge between each pair)
    for i in range(len(nodes_for_episode)):
        for j in range(i + 1, len(nodes_for_episode)):
            graph.add_edge(
                source_id=nodes_for_episode[i],
                target_id=nodes_for_episode[j],
                relationship="co_occurs_in",
                episode_id=episode_id,
                metadata={"context": (episode_text or "")[:200]},
            )
    return touched


def add_episode(episode: str, graph: Graph, episode_id: Optional[str] = None) -> Dict[str, Any]:
    """Full pipeline: extract -> resolve -> incremental_update.

    Returns dict with episode_id, touched_nodes (count + ids), resolution_log.
    """
    episode_id = episode_id or str(uuid.uuid4())
    extracted = extract_entities(episode)
    resolved = entity_resolution(extracted, graph)
    touched = incremental_update(resolved, graph, episode_id, episode)
    log = {
        "episode_id": episode_id,
        "entities_extracted": len(extracted),
        "touched_nodes": len(touched),
        "touched_ids": sorted(touched),
        "resolution_method_counts": _count_methods(resolved),
        "resolution_log": [
            {"name": r.extracted.name, "type": r.extracted.type,
             "method": r.resolution_method, "existing_id": r.existing_node_id}
            for r in resolved
        ],
    }
    return log


def _count_methods(resolved: List[ResolvedEntity]) -> Dict[str, int]:
    counts = {"canonical": 0, "alias": 0, "fuzzy": 0, "new": 0}
    for r in resolved:
        counts[r.resolution_method] += 1
    return counts


def verify_locality(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two graph snapshots; report % nodes changed.

    Used after an incremental update to confirm locality invariant.
    """
    before_nodes = {n["id"]: n for n in before["nodes"]}
    after_nodes = {n["id"]: n for n in after["nodes"]}
    added = set(after_nodes.keys()) - set(before_nodes.keys())
    modified = set()
    for nid in set(before_nodes.keys()) & set(after_nodes.keys()):
        if before_nodes[nid] != after_nodes[nid]:
            modified.add(nid)
    total_after = max(1, len(after_nodes))
    changed = len(added) + len(modified)
    return {
        "before_count": len(before_nodes),
        "after_count": len(after_nodes),
        "nodes_added": len(added),
        "nodes_modified": len(modified),
        "nodes_changed": changed,
        "percent_changed": 100.0 * changed / total_after,
        "edges_before": len(before["edges"]),
        "edges_after": len(after["edges"]),
        "edges_added": len(after["edges"]) - len(before["edges"]),
    }


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def save_graph(g: Graph, path: str) -> None:
    with open(path, "w") as f:
        json.dump(g.snapshot(), f, indent=2)


def load_graph(path: str) -> Graph:
    with open(path) as f:
        return Graph.from_snapshot(json.load(f))
