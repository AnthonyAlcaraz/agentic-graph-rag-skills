"""
Three-tier hierarchical memory (Letta / MemGPT pattern).

Implements Ch4 Example 4-6 + the CPU-architecture three-layer framing.
Pure Python, no external deps. Production swaps documented at seams.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple, Any


# ---------------------------------------------------------------------------
# Eviction scoring — combined access frequency × recency, durability-aware
# ---------------------------------------------------------------------------

DURABILITY_DURABLE = "durable"
DURABILITY_SHORT_LIVED = "short-lived"
DURABILITY_TYPES = (DURABILITY_DURABLE, DURABILITY_SHORT_LIVED)

# Multiplier on the eviction score for durable facts.
# Lower = harder to evict. Set to 0 to make durable un-evictable.
DURABILITY_PROTECTION_FACTOR = 0.1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Fact — what lives in core / archival
# ---------------------------------------------------------------------------

@dataclass
class Fact:
    content: str
    durability: str = DURABILITY_SHORT_LIVED
    created_at: datetime = field(default_factory=_utc_now)
    last_accessed_at: datetime = field(default_factory=_utc_now)
    access_count: int = 0
    # Bookkeeping when moved between tiers
    was_in_core: bool = False
    evicted_at: Optional[datetime] = None
    eviction_reason: Optional[str] = None

    def touch(self, now_fn: Callable[[], datetime] = _utc_now) -> None:
        self.access_count += 1
        self.last_accessed_at = now_fn()

    def eviction_score(self, now_fn: Callable[[], datetime] = _utc_now) -> float:
        """Lower score = better candidate for eviction.

        Formula:
            base = (access_count + 1) / (age_seconds + 1)
            durability_factor: 1.0 short-lived, DURABILITY_PROTECTION_FACTOR durable
            score = base * durability_factor

        High frequency + recent = high score = stays.
        Low frequency + old = low score = first to evict.
        Durable facts get score multiplied by a small factor to protect them.

        BUT: we want LOW score = evict first. So durable facts should have
        HIGHER scores (harder to evict). Inversion fix below.
        """
        now = now_fn()
        age = max(1.0, (now - self.created_at).total_seconds())
        base = (self.access_count + 1) / age
        # Durable facts get a multiplier that PROTECTS them (raises score)
        protection = 1.0 / DURABILITY_PROTECTION_FACTOR if self.durability == DURABILITY_DURABLE else 1.0
        return base * protection

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in ("created_at", "last_accessed_at", "evicted_at"):
            if d.get(k):
                d[k] = d[k].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Fact":
        d = dict(d)
        for k in ("created_at", "last_accessed_at", "evicted_at"):
            if d.get(k):
                d[k] = datetime.fromisoformat(d[k])
        return cls(**d)


# ---------------------------------------------------------------------------
# Interaction — what lives in recall
# ---------------------------------------------------------------------------

@dataclass
class Interaction:
    user_input: str
    agent_response: str
    timestamp: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = d["timestamp"].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Interaction":
        d = dict(d)
        d["timestamp"] = datetime.fromisoformat(d["timestamp"])
        return cls(**d)


# ---------------------------------------------------------------------------
# HierarchicalMemory — the three-tier orchestrator
# ---------------------------------------------------------------------------

class HierarchicalMemory:
    """Letta / MemGPT pattern: core (fast bounded cache) + recall (raw history)
    + archival (overflow, searchable).

    `core_limit` is a forcing function. When full, eviction picks the
    least-used fact (frequency × recency × durability) and moves it to
    archival. Archival is searchable, never deleted by default.

    Production seams:
        - `core` is a dict; production should use a min-heap for O(log n)
          eviction. The signature of `_evict_least_used` is stable.
        - `archival.search` is substring-match here; production swaps in
          BM25 / vector / hybrid retrieval. Stable contract: query in,
          list of Fact out.
        - `recall` is a deque with optional maxlen; production may
          summarize-and-replace older interactions instead of dropping.
    """

    def __init__(
        self,
        core_limit: int = 50,
        recall_maxlen: Optional[int] = None,
        now_fn: Callable[[], datetime] = _utc_now,
    ):
        if core_limit < 1:
            raise ValueError(f"core_limit must be >= 1, got {core_limit}")
        self.core_limit = core_limit
        self.now_fn = now_fn
        self.core: Dict[str, Fact] = {}
        self.recall: deque = deque(maxlen=recall_maxlen)
        self.archival: List[Fact] = []

    # -- mutation ---------------------------------------------------------

    def process_interaction(
        self,
        user_input: str,
        agent_response: str,
        extract_fn: Optional[Callable[[str, str], List[Tuple[str, str]]]] = None,
    ) -> List[Fact]:
        """Record interaction in recall, extract facts, promote to core.

        `extract_fn` returns [(fact_content, durability), ...]. If None, no
        facts are extracted from this interaction.
        """
        self.recall.append(Interaction(user_input, agent_response, self.now_fn()))
        added = []
        if extract_fn is not None:
            for content, durability in extract_fn(user_input, agent_response):
                f = self.add_fact(content, durability)
                if f is not None:
                    added.append(f)
        return added

    def add_fact(self, content: str, durability: str = DURABILITY_SHORT_LIVED) -> Optional[Fact]:
        """Add a fact to core; evict if necessary."""
        if durability not in DURABILITY_TYPES:
            raise ValueError(f"durability must be one of {DURABILITY_TYPES}, got {durability}")
        # Deduplicate: if fact already in core, just touch it
        if content in self.core:
            self.core[content].touch(now_fn=self.now_fn)
            return self.core[content]
        # If at limit, evict
        if len(self.core) >= self.core_limit:
            self._evict_least_used(reason=f"core full at {self.core_limit}, making room for new fact")
        fact = Fact(content=content, durability=durability)
        fact.touch(now_fn=self.now_fn)
        self.core[content] = fact
        return fact

    def _evict_least_used(self, reason: str = "core full") -> Fact:
        """Move the LFU/LRU fact from core to archival."""
        if not self.core:
            raise RuntimeError("cannot evict from empty core")
        victim_key = min(self.core.keys(), key=lambda k: self.core[k].eviction_score(now_fn=self.now_fn))
        victim = self.core.pop(victim_key)
        victim.was_in_core = True
        victim.evicted_at = self.now_fn()
        victim.eviction_reason = reason
        self.archival.append(victim)
        return victim

    # -- query ------------------------------------------------------------

    def query(self, q: str, top_k_per_tier: int = 3) -> Dict[str, List[Dict[str, Any]]]:
        """Search across all three tiers. Returns dict keyed by tier name.

        Default impl uses substring match — production should swap in
        BM25 or vector retrieval at this seam.
        """
        q_lower = q.lower()
        # Core: rank by eviction_score descending (most-important first)
        core_hits = []
        for f in self.core.values():
            if q_lower in f.content.lower():
                core_hits.append(f)
        core_hits.sort(key=lambda f: f.eviction_score(now_fn=self.now_fn), reverse=True)
        for f in core_hits[:top_k_per_tier]:
            f.touch(now_fn=self.now_fn)
        # Recall: most recent first
        recall_hits = [i for i in self.recall if q_lower in i.user_input.lower() or q_lower in i.agent_response.lower()]
        recall_hits = list(reversed(recall_hits))[:top_k_per_tier]
        # Archival: most recently evicted first
        archival_hits = [f for f in self.archival if q_lower in f.content.lower()]
        archival_hits.sort(key=lambda f: f.evicted_at or _utc_now(), reverse=True)
        archival_hits = archival_hits[:top_k_per_tier]
        return {
            "core": [
                {"content": f.content, "durability": f.durability, "access_count": f.access_count}
                for f in core_hits[:top_k_per_tier]
            ],
            "recall": [
                {"user": i.user_input, "agent": i.agent_response, "timestamp": i.timestamp.isoformat()}
                for i in recall_hits
            ],
            "archival": [
                {"content": f.content, "durability": f.durability,
                 "evicted_at": f.evicted_at.isoformat() if f.evicted_at else None,
                 "eviction_reason": f.eviction_reason}
                for f in archival_hits
            ],
        }

    # -- diagnostics ------------------------------------------------------

    def diagnostics(self) -> Dict[str, Any]:
        """Health check — flag pathological patterns."""
        core_durable = sum(1 for f in self.core.values() if f.durability == DURABILITY_DURABLE)
        core_short = len(self.core) - core_durable
        warnings = []
        # >50% short-lived facts in core after the memory has been used
        if len(self.core) >= 5 and core_short / max(1, len(self.core)) > 0.5:
            warnings.append(
                f"core composition: {core_short}/{len(self.core)} short-lived facts "
                f"(>50%). Promotion logic may be too permissive."
            )
        # Archival has more durable than core (potential regression — important
        # facts being kicked out)
        archival_durable = sum(1 for f in self.archival if f.durability == DURABILITY_DURABLE)
        if archival_durable > core_durable and core_durable < self.core_limit / 2:
            warnings.append(
                f"archival has {archival_durable} durable facts vs core's {core_durable}. "
                f"Durable facts may be evicting prematurely."
            )
        # Empty core but core_limit > 0
        if len(self.core) == 0 and len(self.archival) + len(self.recall) > 0:
            warnings.append("core is empty despite recall/archival being non-empty. extract_fn not wired up?")
        return {
            "core_size": len(self.core),
            "core_limit": self.core_limit,
            "core_durable_count": core_durable,
            "core_short_lived_count": core_short,
            "recall_size": len(self.recall),
            "archival_size": len(self.archival),
            "archival_durable_count": archival_durable,
            "warnings": warnings,
        }

    # -- serialization ----------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        return {
            "core_limit": self.core_limit,
            "recall_maxlen": self.recall.maxlen,
            "core": [f.to_dict() for f in self.core.values()],
            "recall": [i.to_dict() for i in self.recall],
            "archival": [f.to_dict() for f in self.archival],
        }

    @classmethod
    def from_snapshot(cls, snap: Dict[str, Any]) -> "HierarchicalMemory":
        mem = cls(core_limit=snap["core_limit"], recall_maxlen=snap.get("recall_maxlen"))
        for fd in snap["core"]:
            f = Fact.from_dict(fd)
            mem.core[f.content] = f
        for id_ in snap["recall"]:
            mem.recall.append(Interaction.from_dict(id_))
        for fd in snap["archival"]:
            mem.archival.append(Fact.from_dict(fd))
        return mem


# ---------------------------------------------------------------------------
# Default extract_fn — simple heuristic-based fact extractor
# ---------------------------------------------------------------------------

DURABLE_TRIGGERS = [
    "always", "never", "I am", "I'm", "my name is", "my role is",
    "production", "primary", "default", "allergic", "preference",
]
SHORT_LIVED_TRIGGERS = [
    "right now", "currently", "today", "this minute", "just",
    "having coffee", "in my shell",
]


def default_extract_fn(user_input: str, agent_response: str) -> List[Tuple[str, str]]:
    """Heuristic fact extractor — production should swap in an LLM extractor."""
    facts = []
    combined = user_input
    text_lower = combined.lower()
    if any(t in text_lower for t in DURABLE_TRIGGERS):
        facts.append((combined.strip(), DURABILITY_DURABLE))
    elif any(t in text_lower for t in SHORT_LIVED_TRIGGERS):
        facts.append((combined.strip(), DURABILITY_SHORT_LIVED))
    return facts


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def save_memory(mem: HierarchicalMemory, path: str) -> None:
    with open(path, "w") as f:
        json.dump(mem.snapshot(), f, indent=2)


def load_memory(path: str) -> HierarchicalMemory:
    with open(path) as f:
        return HierarchicalMemory.from_snapshot(json.load(f))
