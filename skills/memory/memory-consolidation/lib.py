"""
Memory consolidation — from raw experience to durable knowledge.

Implements the Ch4 consolidation pipeline (Example 4-5 + Example 4-13):
cluster related episodes -> summarize each cluster into a consolidated fact
-> create the consolidated node -> maintain a provenance chain back to the
source episodes. Adds the "sleep-time compute" discipline: consolidation
runs during idle periods, not on the synchronous response path, and may
pre-compute inferences that anticipate likely queries.

Pure Python, no external deps, deterministic for testing.

Production swap notes:
    - `cluster_by_topic` here uses a token-overlap (Jaccard) similarity with
      single-linkage agglomeration. Production should swap in semantic
      similarity over embeddings (the chapter's "measuring how conceptually
      close memories are"). The signature is the seam: replace the body of
      `_similarity` without changing `cluster_by_topic`.
    - `summarize_cluster` here is extractive (it lifts the most-connected
      sentence and folds in a confirmation count). Production swaps in an
      LLM summarizer that produces the narrative 2-5-fact form HINDSIGHT
      recommends. The seam is `summarize_cluster`.
    - The episode/knowledge store is in-memory lists. Production uses the
      graph database; the provenance chain is the DERIVED_FROM edge set.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple


MIN_CLUSTER_SIZE = 3  # Ch4 Example 4-13: "Need enough examples to generalize"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9][a-z0-9\-]*", text.lower()))


# ---------------------------------------------------------------------------
# Episode and consolidated-knowledge data
# ---------------------------------------------------------------------------

@dataclass
class Episode:
    """A raw, append-only operational event (Ch4 EPISODE_TYPES)."""
    id: str
    content: str
    episode_type: str = "Conversation"
    created_at: datetime = field(default_factory=_utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConsolidatedFact:
    """A durable, summarized knowledge node with a provenance chain (Ch4)."""
    id: str
    summary: str
    knowledge_type: str = "Pattern"   # Ch4 KNOWLEDGE_TYPES
    confirmations: int = 1
    derived_from: List[str] = field(default_factory=list)   # source episode ids (provenance)
    created_at: datetime = field(default_factory=_utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        return d


# ---------------------------------------------------------------------------
# Clustering — group related episodes (Ch4 cluster_by_topic)
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    """Token-overlap (Jaccard) similarity. SEAM: swap for embedding cosine."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def cluster_by_topic(
    episodes: List[Episode],
    threshold: float = 0.25,
    similarity_fn: Optional[Callable[[str, str], float]] = None,
) -> List[List[Episode]]:
    """Single-linkage agglomeration by content similarity.

    Returns a list of clusters (each a list of Episodes). Two episodes join
    the same cluster if their similarity >= threshold. Deterministic: input
    order is preserved within clusters.
    """
    sim = similarity_fn or _similarity
    parent: Dict[str, str] = {e.id: e.id for e in episodes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        parent[find(x)] = find(y)

    for i in range(len(episodes)):
        for j in range(i + 1, len(episodes)):
            if sim(episodes[i].content, episodes[j].content) >= threshold:
                union(episodes[i].id, episodes[j].id)

    groups: Dict[str, List[Episode]] = {}
    for e in episodes:
        groups.setdefault(find(e.id), []).append(e)
    # stable order by first-appearance
    ordered_roots = []
    seen = set()
    for e in episodes:
        r = find(e.id)
        if r not in seen:
            seen.add(r)
            ordered_roots.append(r)
    return [groups[r] for r in ordered_roots]


# ---------------------------------------------------------------------------
# Summarization — extract the durable fact (Ch4 summarize_cluster)
# ---------------------------------------------------------------------------

def summarize_cluster(
    cluster: List[Episode],
    summarizer_fn: Optional[Callable[[List[str]], str]] = None,
) -> str:
    """Reduce a cluster of episodes to one durable fact.

    SEAM: pass `summarizer_fn` to use an LLM producing the narrative 2-5-fact
    HINDSIGHT form. Default is extractive: the episode whose tokens best cover
    the cluster vocabulary, annotated with the confirmation count.
    """
    if summarizer_fn is not None:
        return summarizer_fn([e.content for e in cluster])
    if not cluster:
        return ""
    vocab: set = set()
    for e in cluster:
        vocab |= _tokens(e.content)
    best = max(cluster, key=lambda e: len(_tokens(e.content) & vocab))
    n = len(cluster)
    suffix = f" (confirmed {n} times)" if n > 1 else ""
    return best.content.strip().rstrip(".") + suffix


# ---------------------------------------------------------------------------
# Consolidation + provenance (Ch4 create_consolidated_memory + maintain_provenance_chain)
# ---------------------------------------------------------------------------

def consolidate(
    episodes: List[Episode],
    min_cluster_size: int = MIN_CLUSTER_SIZE,
    threshold: float = 0.25,
    knowledge_type: str = "Pattern",
    summarizer_fn: Optional[Callable[[List[str]], str]] = None,
    similarity_fn: Optional[Callable[[str, str], float]] = None,
    now_fn: Callable[[], datetime] = _utc_now,
) -> List[ConsolidatedFact]:
    """Full consolidation pass: cluster -> summarize -> consolidate -> provenance.

    Clusters smaller than `min_cluster_size` are skipped (not enough examples
    to generalize, per Ch4 Example 4-13). Every ConsolidatedFact keeps the
    `derived_from` provenance list so "how do you know X?" is answerable.
    """
    facts: List[ConsolidatedFact] = []
    for cluster in cluster_by_topic(episodes, threshold=threshold, similarity_fn=similarity_fn):
        if len(cluster) < min_cluster_size:
            continue
        summary = summarize_cluster(cluster, summarizer_fn=summarizer_fn)
        facts.append(ConsolidatedFact(
            id=str(uuid.uuid4()),
            summary=summary,
            knowledge_type=knowledge_type,
            confirmations=len(cluster),
            derived_from=[e.id for e in cluster],
            created_at=now_fn(),
        ))
    return facts


def provenance_of(fact: ConsolidatedFact, episodes: List[Episode]) -> List[Episode]:
    """Trace a consolidated fact back to its source episodes (Ch4 provenance chain).

    This is the "How do you know the deadline is Friday?" query. Returns the
    source episodes in stored order. If any provenance id is missing from the
    episode store, raises — a dangling provenance link is corruption.
    """
    by_id = {e.id: e for e in episodes}
    missing = [eid for eid in fact.derived_from if eid not in by_id]
    if missing:
        raise ValueError(
            f"dangling provenance: consolidated fact {fact.id} cites episodes "
            f"{missing} that no longer exist. Provenance chain is broken."
        )
    return [by_id[eid] for eid in fact.derived_from]


# ---------------------------------------------------------------------------
# Sleep-time compute — idle-period pre-computation (Ch4 sleep-time compute)
# ---------------------------------------------------------------------------

def precompute_inferences(
    facts: List[ConsolidatedFact],
    inference_fn: Callable[[ConsolidatedFact], List[str]],
) -> Dict[str, List[str]]:
    """Pre-compute likely-query inferences during idle time (Ch4 sleep-time compute).

    The chapter: "If the consolidated knowledge includes a project deadline
    and a list of dependencies, sleep-time processing can derive which tasks
    are at risk before anyone asks." Returns {fact_id: [inference, ...]}.

    `inference_fn` is the seam (an LLM in production). This must NOT run on the
    synchronous response path — call it from a background/idle worker.
    """
    return {f.id: inference_fn(f) for f in facts}


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def save_facts(facts: List[ConsolidatedFact], path: str) -> None:
    with open(path, "w") as f:
        json.dump([x.to_dict() for x in facts], f, indent=2)


def episodes_from_records(records: List[Dict[str, Any]]) -> List[Episode]:
    out = []
    for r in records:
        out.append(Episode(
            id=r.get("id") or str(uuid.uuid4()),
            content=r["content"],
            episode_type=r.get("episode_type", "Conversation"),
            metadata=r.get("metadata", {}),
        ))
    return out
