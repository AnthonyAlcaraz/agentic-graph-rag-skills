"""
Self-improving skill objects (Ch7).

Two Ch7 primitives compose here into one pipeline:

1. XSkill dual-stream extraction (Jiang et al., 2026): from execution traces,
   distill EXPERIENCES (action-level: what worked/failed for one tool call)
   and SKILLS (task-level: multistep patterns that solve a category of task).
   Experiences alone cut tool errors 29.9% to 16.3% (a 45% reduction); with
   skills the average success rate rises 33.6% to 40.3%.

2. Cognee skill-as-graph-object: a skill is not a flat SKILL.md document but a
   graph node that observes its own executions, computes its success rate, and
   rewrites itself via amendify() when it degrades. Routing selects skills by
   DEMONSTRATED SUCCESS on the task pattern, not by description similarity.

Production seam: this in-memory implementation is the dev-time stand-in. In
production the lesson/amendment text comes from an LLM summarizer + judge, the
held-out validation is a real eval set, and the store is a graph database.
The API contract is stable; the substrate is the seam. Every swap point is
marked `# TODO(production): ...`.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# Outcome markers that mean a node's outcome diverged from expectation.
# A failure always diverges. A surprising (unexpected) success also diverges:
# both teach the agent something a routine success does not.
DIVERGENCE_MARKERS = ("diverged", "unexpected", "unexpected_success", "recovered", "surprise")

_STOPWORDS = {
    "the", "a", "an", "to", "for", "of", "on", "in", "and", "or", "with",
    "any", "new", "run", "this", "that", "is", "are", "be", "by",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: str) -> List[str]:
    out: List[str] = []
    word = []
    for ch in str(text).lower():
        if ch.isalnum():
            word.append(ch)
        else:
            if word:
                out.append("".join(word))
                word = []
    if word:
        out.append("".join(word))
    return [t for t in out if t not in _STOPWORDS and len(t) > 1]


def _compute_hash(definition: Dict[str, Any]) -> str:
    """Content hash for change detection (Cognee add stage)."""
    payload = json.dumps(definition, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# -- XSkill dual-stream extraction ----------------------------------------


@dataclass
class AgentExperience:
    """Action-level knowledge extracted from one execution node (XSkill)."""

    task_type: str
    action_taken: str
    context_summary: str
    outcome: str          # "success" | "failure"
    lesson: str
    source_node_id: str
    timestamp: str        # ISO-8601 string

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentSkill:
    """Task-level pattern extracted from a successful execution subgraph."""

    task_type: str
    steps: List[str]
    preconditions: List[str]
    success_rate: float
    source_execution_ids: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _summarize_context(context: Any) -> str:
    # TODO(production): swap for an LLM summarizer of the node's input conditions.
    text = str(context) if context is not None else ""
    return text if len(text) <= 160 else text[:157] + "..."


def _generate_lesson(node: Dict[str, Any]) -> str:
    # TODO(production): swap generate_lesson for an LLM summarizer that reads the
    # node plus its neighbors and writes an actionable insight.
    action = node.get("action", "")
    context = node.get("context", "") or "this context"
    neighbors = node.get("neighbors") or []
    near = f" (near {', '.join(str(n) for n in neighbors)})" if neighbors else ""
    if node.get("caused_task_failure"):
        return f"When {context} holds, '{action}' caused task failure; avoid or guard it{near}."
    return f"When {context} holds, '{action}' unexpectedly succeeded; prefer it here{near}."


def _diverged(node: Dict[str, Any]) -> bool:
    if node.get("caused_task_failure"):
        return True
    return node.get("outcome") in DIVERGENCE_MARKERS


def extract_experiences(execution_nodes: List[Dict[str, Any]]) -> List[AgentExperience]:
    """One experience per node whose outcome diverged from expectation.

    Node dict keys: id, task_type, action, context, outcome,
    caused_task_failure, neighbors. Routine successes teach nothing and are
    skipped; failures and surprising successes both become experience records.
    """
    experiences: List[AgentExperience] = []
    for node in execution_nodes:
        if not _diverged(node):
            continue
        outcome = "failure" if node.get("caused_task_failure") else "success"
        experiences.append(
            AgentExperience(
                task_type=node.get("task_type", "unknown"),
                action_taken=node.get("action", ""),
                context_summary=_summarize_context(node.get("context")),
                outcome=outcome,
                lesson=_generate_lesson(node),
                source_node_id=node.get("id", ""),
                timestamp=_now_iso(),
            )
        )
    return experiences


def extract_skills(
    successful_executions: List[Dict[str, Any]],
    min_support: int = 3,
) -> List[AgentSkill]:
    """Group successful executions by task_type; keep a skill only when
    >= min_support of them share a common successful path.

    Execution dict keys: id, task_type, path (list of action strings),
    preconditions (list of strings). `steps` is accepted as an alias for path.
    """
    if min_support < 1:
        raise ValueError("min_support must be >= 1")
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for ex in successful_executions:
        groups[ex.get("task_type", "unknown")].append(ex)

    skills: List[AgentSkill] = []
    for task_type, execs in groups.items():
        path_counts = Counter(
            tuple(ex.get("path") or ex.get("steps") or []) for ex in execs
        )
        common_path, support = path_counts.most_common(1)[0]
        if not common_path or support < min_support:
            continue
        supporters = [
            ex for ex in execs
            if tuple(ex.get("path") or ex.get("steps") or []) == common_path
        ]
        precond_sets = [set(ex.get("preconditions") or []) for ex in supporters]
        common_pre = set.intersection(*precond_sets) if precond_sets else set()
        skills.append(
            AgentSkill(
                task_type=task_type,
                steps=list(common_path),
                # TODO(production): divide by TRUE total attempts (incl. failed
                # executions) for the empirical success rate; here support/group
                # is the fraction of SUCCESSFUL runs following the canonical path.
                success_rate=support / len(execs),
                preconditions=sorted(common_pre),
                source_execution_ids=[ex.get("id") for ex in supporters],
            )
        )
    return skills


# -- Cognee skill-as-graph-object -----------------------------------------


@dataclass
class ExecutionRecord:
    """One observation of a skill being used (Cognee learn stage)."""

    task: Dict[str, Any]
    skill_id: str
    outcome: str          # "success" | "failure"
    error: Optional[str] = None
    version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _cluster_errors(failing_runs: List[ExecutionRecord]) -> List[Dict[str, Any]]:
    # TODO(production): swap for semantic error clustering (embeddings / LLM).
    counts = Counter(
        (r.error or "unspecified").strip().split("\n")[0][:80] for r in failing_runs
    )
    return [{"pattern": p, "count": c} for p, c in counts.most_common()]


def _generate_amendment(
    definition: Dict[str, Any],
    evidence: List[ExecutionRecord],
) -> Dict[str, Any]:
    # TODO(production): swap generate_amendment for an LLM that rewrites trigger
    # conditions / edge cases / step ordering grounded in the failure evidence.
    amended = dict(definition)
    history = list(amended.get("amendments", []))
    history.append(
        {
            "addressed_error_patterns": _cluster_errors(evidence),
            "evidence_count": len(evidence),
        }
    )
    amended["amendments"] = history
    return amended


def _validate_amendment(
    amended: Dict[str, Any],
    executions: List[ExecutionRecord],
    current: Dict[str, Any],
) -> bool:
    # TODO(production): swap for a real held-out eval: replay the amended skill
    # against a held-out set of execution records and accept only on improvement.
    if amended == current:
        return False
    return any(r.outcome == "failure" and r.error for r in executions)


class SkillNode:
    """A skill as a first-class graph object that rewrites itself."""

    def __init__(self, skill_id: str, definition: Dict[str, Any]):
        if not isinstance(definition, dict):
            raise TypeError("definition must be a dict")
        self.skill_id = skill_id
        self.definition = dict(definition)
        self.version = 1
        self.executions: List[ExecutionRecord] = []
        self.content_hash = _compute_hash(self.definition)

    @property
    def success_rate(self) -> float:
        if not self.executions:
            return 0.0
        successes = sum(1 for e in self.executions if e.outcome == "success")
        return successes / len(self.executions)

    def success_rate_for(self, pattern: Optional[str]) -> float:
        """Success rate over executions whose task pattern matches (route key)."""
        runs = [e for e in self.executions if (e.task or {}).get("pattern") == pattern]
        if not runs:
            return 0.0
        successes = sum(1 for e in runs if e.outcome == "success")
        return successes / len(runs)

    def observe(self, task: Dict[str, Any], outcome: str, error: Optional[str] = None) -> None:
        if outcome not in ("success", "failure"):
            raise ValueError("outcome must be 'success' or 'failure'")
        self.executions.append(
            ExecutionRecord(
                task=task,
                skill_id=self.skill_id,
                outcome=outcome,
                error=error,
                version=self.version,
            )
        )

    def amendify(self, failure_threshold: float = 0.6) -> bool:
        """Rewrite the skill when it degrades below the threshold.

        Fires only when success_rate < failure_threshold AND the amendment
        validates against held-out records. On success: bumps version,
        recomputes content_hash, returns True. Otherwise leaves the skill
        untouched (rollback) and returns False.
        """
        if self.success_rate >= failure_threshold:
            return False
        failing = [e for e in self.executions if e.outcome == "failure"]
        # Last 10 failures as evidence (Ch7 the chapter's SkillGraph example: failing_runs[-10:]).
        amended = _generate_amendment(self.definition, failing[-10:])
        if _validate_amendment(amended, self.executions, self.definition):
            self.definition = amended
            self.version += 1
            self.content_hash = _compute_hash(amended)
            return True
        return False


class SkillGraph:
    """Registry of SkillNodes with success-rate routing (Cognee)."""

    def __init__(self):
        self.skills: Dict[str, SkillNode] = {}

    def add(self, skill_id: str, definition: Dict[str, Any]) -> SkillNode:
        """Cognee add stage: register a skill and hash its definition."""
        node = SkillNode(skill_id, definition)
        self.skills[skill_id] = node
        return node

    def cognify(self, skill_id: str) -> Dict[str, Any]:
        """Cognee cognify stage: extract trigger phrases + complexity.

        Heuristic extraction from name / description / steps.
        # TODO(production): LLM extraction of trigger phrases, complexity, and
        # activation-pattern nodes.
        """
        if skill_id not in self.skills:
            raise KeyError(f"skill {skill_id} not found")
        node = self.skills[skill_id]
        d = node.definition
        text = " ".join(str(d.get(k, "")) for k in ("name", "description"))
        steps = d.get("steps", []) or []
        trigger_phrases = sorted(set(_tokens(text)))[:8]
        n = len(steps)
        complexity = "low" if n <= 2 else ("medium" if n <= 5 else "high")
        return {
            "skill_id": skill_id,
            "trigger_phrases": trigger_phrases,
            "complexity": complexity,
            "step_count": n,
            "content_hash": node.content_hash,
        }

    def _similarity(self, node: SkillNode, task_tokens: List[str]) -> int:
        d = node.definition
        text = " ".join(
            str(d.get(k, "")) for k in ("name", "description")
        ) + " " + " ".join(str(s) for s in (d.get("steps") or []))
        node_tokens = set(_tokens(text))
        return len(node_tokens.intersection(task_tokens))

    def route(self, task: Dict[str, Any]) -> Optional[SkillNode]:
        """Cognee search stage: route a task to the best skill.

        Candidates come from description similarity (semantic_search stand-in),
        but the RANKING is by demonstrated success_rate on the task pattern, NOT
        by similarity. This is the decisive choice: a specialized skill with
        a strong track record on the pattern outranks a general skill that merely
        looks similar by description.
        """
        task_tokens = set(_tokens(task.get("description", "")))
        pattern = task.get("pattern")
        candidates = [
            node for node in self.skills.values()
            if self._similarity(node, task_tokens) > 0
        ]
        if not candidates:
            return None
        ranked = sorted(
            candidates,
            key=lambda node: (-node.success_rate_for(pattern), node.skill_id),
        )
        return ranked[0]

    def learn(
        self,
        skill_id: str,
        task: Dict[str, Any],
        outcome: str,
        error: Optional[str] = None,
    ) -> None:
        """Cognee learn stage: log an observation against a skill."""
        if skill_id not in self.skills:
            raise KeyError(f"skill {skill_id} not found")
        self.skills[skill_id].observe(task, outcome, error)


# -- knowledge retirement --------------------------------------------------


def retire_experiences(
    experiences: List[AgentExperience],
    now_days: int,
    decay_days: int = 90,
) -> List[Dict[str, Any]]:
    """Temporal decay: experiences not revalidated within `decay_days` lose
    half their retrieval weight.

    `now_days` is "now" expressed as a day ordinal (datetime.toordinal()).
    Each experience's ISO timestamp is converted to a day ordinal; age is the
    difference. Age > decay_days halves the retrieval weight.
    """
    out: List[Dict[str, Any]] = []
    for exp in experiences:
        exp_day = datetime.fromisoformat(exp.timestamp).toordinal()
        age = now_days - exp_day
        half = age > decay_days
        out.append(
            {
                "source_node_id": exp.source_node_id,
                "age_days": age,
                "weight": 0.5 if half else 1.0,
                "half_weight": half,
            }
        )
    return out


def flag_stale_skills(
    skills: List[SkillNode],
    recent: int = 10,
    floor: float = 0.6,
) -> List[str]:
    """Flag skills whose success rate over the most recent `recent` executions
    drops below `floor` (Ch7: below 60% over the most recent 10 attempts)."""
    flagged: List[str] = []
    for node in skills:
        window = node.executions[-recent:]
        if not window:
            continue
        successes = sum(1 for e in window if e.outcome == "success")
        if successes / len(window) < floor:
            flagged.append(node.skill_id)
    return flagged
