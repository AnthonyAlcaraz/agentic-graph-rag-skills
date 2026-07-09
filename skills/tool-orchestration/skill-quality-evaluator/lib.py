"""
Skill quality evaluator — SkillNet five-dimension rating + quality-gated retrieval.

Distilled from Agentic Graph RAG (O'Reilly), Chapter 6 — Tool Orchestration
("Skills: The Judgment Layer" / "Skill quality evaluation" / "Integrating
quality ratings into graph-based retrieval").

Routing (rag-mcp-tool-selection, mcp-gateway-two-meta-tools) answers "which
skill matches this task?". This module answers the second question the chapter
raises: "is this skill worth trusting once matched?".

SkillNet rates each skill across five dimensions in [0, 1]:
    safety, completeness, executability, maintainability, cost_awareness
The composite weights safety and executability at 2x (a skill that runs
unconstrained shell or hallucinates tool calls is dangerous regardless of how
well it documents). Retrieval ranks by relevance * quality, so a highly
relevant but low-quality skill ranks below a moderately relevant high-quality
one (chapter Example 6-3).

STDLIB ONLY. The relevance retriever is a deliberately simple word-overlap
scorer so the skill has zero ML dependencies.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have he in is it its of on or "
    "that the their to was were will with you your this these those what "
    "which who whom whose how can could should would do does did".split()
)

# The five SkillNet dimensions, in composite order, with their weights.
DIMENSIONS = (
    "safety",
    "completeness",
    "executability",
    "maintainability",
    "cost_awareness",
)
_WEIGHTS = (2.0, 1.0, 2.0, 1.0, 1.0)  # safety + executability weighted 2x


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens with stopwords removed."""
    return {t.lower() for t in _TOKEN_RE.findall(text) if t.lower() not in _STOPWORDS}


@dataclass(frozen=True)
class SkillQuality:
    """The five-dimensional SkillNet rating for one skill (Table 6-1)."""

    safety: float
    completeness: float
    executability: float
    maintainability: float
    cost_awareness: float

    @classmethod
    def from_skill(cls, skill: dict) -> "SkillQuality":
        return cls(
            safety=float(skill["eval_safety"]),
            completeness=float(skill["eval_completeness"]),
            executability=float(skill["eval_executability"]),
            maintainability=float(skill["eval_maintainability"]),
            cost_awareness=float(skill["eval_cost_awareness"]),
        )

    @property
    def composite(self) -> float:
        """Weighted mean; safety and executability weighted 2x (chapter Example 6-3)."""
        scores = (
            self.safety,
            self.completeness,
            self.executability,
            self.maintainability,
            self.cost_awareness,
        )
        return sum(w * s for w, s in zip(_WEIGHTS, scores)) / sum(_WEIGHTS)

    @property
    def hard_gate_ok(self) -> bool:
        """
        Hard exclusion: a zero on safety OR executability drops the skill
        entirely, regardless of composite (chapter Cypher:
        WHERE node.eval_safety > 0 AND node.eval_executability > 0).
        """
        return self.safety > 0 and self.executability > 0


@dataclass(frozen=True)
class ScoredSkill:
    skill: dict
    relevance: float
    quality: float

    @property
    def name(self) -> str:
        return self.skill["name"]

    @property
    def rank_score(self) -> float:
        """Multiplicative ranking: relevance * quality (chapter ORDER BY)."""
        return self.relevance * self.quality


def load_catalog(path: str | Path) -> list[dict]:
    """
    Load the skills catalog JSON. Returns the list of skill dicts.

    # TODO(production): the eval_* ratings must come from an INDEPENDENT
    # evaluator, never self-reported by the skill author (a malicious skill
    # would inflate its own scores). In production, join the catalog against a
    # separate ratings store keyed by skill hash, produced by SkillNet-style
    # evaluation runs.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["skills"]


def _enhanced_text(skill: dict) -> str:
    """Concatenate name + description + synthetic_queries + key_topics for matching."""
    parts = [
        skill["name"].replace("-", " ").replace("_", " "),
        skill.get("description", ""),
        " ".join(skill.get("synthetic_queries", [])),
        " ".join(skill.get("key_topics", [])),
    ]
    return " ".join(parts)


def score_relevance(skill: dict, query_tokens: set[str]) -> float:
    """
    Word-overlap relevance against the enhanced skill representation.

    # TODO(production): replace with the same embedding retriever used for
    # tool selection (sentence-transformer or hosted embedding API). The
    # contract (returns a float, higher = more relevant) is the seam.
    """
    skill_tokens = _tokenize(_enhanced_text(skill))
    if not skill_tokens or not query_tokens:
        return 0.0
    overlap = query_tokens & skill_tokens
    return len(overlap) / (len(query_tokens) ** 0.5 * len(skill_tokens) ** 0.5)


def retrieve_quality_gated(
    task_description: str,
    catalog: Iterable[dict],
    min_quality: float = 0.6,
    top_k: int = 3,
) -> list[ScoredSkill]:
    """
    Return the top-K skills that are BOTH relevant AND pass the quality gate.

    Two gates, matching the chapter's Cypher (Example 6-3):
      hard gate  -> eval_safety > 0 AND eval_executability > 0   (exclude)
      soft gate  -> composite >= min_quality                     (threshold)
    Ranking is relevance * quality, descending.

    min_quality is the deployment knob: research ~0.4 casts a wide net;
    production healthcare sets 0.8+.
    """
    q_tokens = _tokenize(task_description)
    scored: list[ScoredSkill] = []
    for skill in catalog:
        quality = SkillQuality.from_skill(skill)
        if not quality.hard_gate_ok:
            continue
        composite = quality.composite
        if composite < min_quality:
            continue
        relevance = score_relevance(skill, q_tokens)
        if relevance <= 0:
            continue
        scored.append(ScoredSkill(skill=skill, relevance=relevance, quality=composite))
    scored.sort(key=lambda s: s.rank_score, reverse=True)
    return scored[:top_k]


def monitor_gaps(
    catalog: Iterable[dict],
    queries: Iterable[str],
    min_quality: float = 0.6,
    top_k: int = 3,
) -> dict:
    """
    Monitor the two failure events the chapter's tip names:
      - no_relevant_skill:    a query matched nothing (repository too small)
      - low_quality_filtered: relevant candidates existed but the gate dropped
                              the best one (gate too permissive OR catalog junky)

    Returns per-event counts plus the per-query breakdown so the operator can
    tell "grow the curated set" from "the gate is doing its job".
    """
    catalog = list(catalog)
    rows = []
    no_relevant = 0
    low_quality_filtered = 0
    for query in queries:
        gated = retrieve_quality_gated(query, catalog, min_quality=min_quality, top_k=top_k)
        # What WOULD have been returned with relevance only, ignoring quality?
        q_tokens = _tokenize(query)
        relevant_any = [s for s in catalog if score_relevance(s, q_tokens) > 0]
        best_relevant = None
        if relevant_any:
            best_relevant = max(relevant_any, key=lambda s: score_relevance(s, q_tokens))
        event = "ok"
        if not relevant_any:
            no_relevant += 1
            event = "no_relevant_skill"
        elif not gated:
            low_quality_filtered += 1
            event = "low_quality_filtered"
        elif best_relevant is not None and best_relevant["name"] != gated[0].name:
            # the most-relevant skill was demoted or dropped by the gate
            low_quality_filtered += 1
            event = "low_quality_filtered"
        rows.append(
            {
                "query": query,
                "event": event,
                "gated_top": gated[0].name if gated else None,
                "relevant_top": best_relevant["name"] if best_relevant else None,
            }
        )
    return {
        "min_quality": min_quality,
        "no_relevant_skill": no_relevant,
        "low_quality_filtered": low_quality_filtered,
        "rows": rows,
        "interpretation": _interpret(no_relevant, low_quality_filtered, len(rows)),
    }


def _interpret(no_relevant: int, low_quality: int, total: int) -> str:
    """Map the two counts to the chapter's diagnosis."""
    if total == 0:
        return "no queries evaluated"
    if no_relevant > low_quality and no_relevant > 0:
        return "repository too small — grow the curated skill set"
    if low_quality > 0:
        return "quality gate is active — verify it is not too permissive and catalog quality is adequate"
    return "healthy — relevant, quality-passing skills found for the query battery"
