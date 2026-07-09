"""
Eight-pillar readiness map (Ch2 — "The Eight Pillars of Agentic Graph
Architecture" + Table 2-1 "Mapping the five flaws to the eight pillars").

The dual-graph architecture is the structural framework; the eight pillars are
the implementation roadmap. This module maps a system's declared capabilities
across the eight pillars, respects the chapter's LAYERING (each pillar depends
on the ones before it), flags dependency violations (a higher pillar claimed
present while a lower one it requires is missing), reports which of the five
Chapter-1 flaws remain unsolved, and recommends the next pillar to build.

The eight pillars and their chapter/layer order:

  1. knowledge_representation (Ch3) — foundational; everything depends on it
  2. memory                   (Ch4) — builds on the knowledge graph
  3. reasoning                (Ch5) — requires knowledge + memory
  4. planning                 (Ch5) — requires knowledge + memory
  5. tool_orchestration       (Ch6) — requires all of the above
  6. structured_output        (Ch5/Ch6) — enforces node + tool-boundary contracts
  7. self_evolution           (Ch7) — requires the complete architecture
  8. optimization             (Ch8) — requires the complete architecture

The five flaws (Ch1) map to pillars per Table 2-1 / the Ch2 summary:
  relationship_blindness -> knowledge_representation (explicit edges)
  context_amnesia        -> memory
  temporal_ignorance     -> memory (bitemporal / `since` modeling)
  reasoning_paralysis    -> reasoning + planning (decomposed workflow graphs)
  tool_chaos             -> tool_orchestration (+ structured_output at boundaries)

self_evolution and optimization do NOT map to a flaw; they map to production
viability ("making the system viable in production").

Pure Python, stdlib only.

Production swap: capability status here is caller-declared (present/partial/
missing). In production a readiness scan probes the running system (does a KG
exist? is memory temporal? are tool calls schema-validated?) and derives status
from evidence. The mapping/layering CONTRACT is the stable seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

STATUSES = ("present", "partial", "missing")
_STATUS_WEIGHT = {"present": 1.0, "partial": 0.5, "missing": 0.0}


@dataclass(frozen=True)
class Pillar:
    key: str
    name: str
    chapter: str
    order: int                       # layer order (1 = foundational)
    depends_on: tuple                # keys of lower pillars this one requires
    production_only: bool = False    # True => maps to viability, not a flaw


# Layer order + dependencies exactly per Ch2 "The pillars are not independent
# modules ... They are layered."
PILLARS: Dict[str, Pillar] = {
    "knowledge_representation": Pillar(
        "knowledge_representation", "Knowledge Representation", "Ch3", 1,
        depends_on=()),
    "memory": Pillar(
        "memory", "Memory Systems", "Ch4", 2,
        depends_on=("knowledge_representation",)),
    "reasoning": Pillar(
        "reasoning", "Reasoning with Graphs", "Ch5", 3,
        depends_on=("knowledge_representation", "memory")),
    "planning": Pillar(
        "planning", "Planning Systems", "Ch5", 4,
        depends_on=("knowledge_representation", "memory")),
    "tool_orchestration": Pillar(
        "tool_orchestration", "Tool Orchestration", "Ch6", 5,
        depends_on=("knowledge_representation", "memory", "reasoning", "planning")),
    "structured_output": Pillar(
        "structured_output", "Structured Output Engineering", "Ch5/Ch6", 6,
        depends_on=("reasoning", "planning", "tool_orchestration")),
    "self_evolution": Pillar(
        "self_evolution", "Self-Evolution", "Ch7", 7,
        depends_on=("knowledge_representation", "memory", "reasoning", "planning",
                    "tool_orchestration", "structured_output"),
        production_only=True),
    "optimization": Pillar(
        "optimization", "Optimization", "Ch8", 8,
        depends_on=("knowledge_representation", "memory", "reasoning", "planning",
                    "tool_orchestration", "structured_output"),
        production_only=True),
}

PILLAR_ORDER = tuple(sorted(PILLARS, key=lambda k: PILLARS[k].order))

# Table 2-1: five Ch1 flaws -> the pillar(s) that solve them.
FLAW_TO_PILLARS: Dict[str, tuple] = {
    "relationship_blindness": ("knowledge_representation",),
    "context_amnesia": ("memory",),
    "temporal_ignorance": ("memory",),
    "reasoning_paralysis": ("reasoning", "planning"),
    "tool_chaos": ("tool_orchestration", "structured_output"),
}


@dataclass
class ReadinessReport:
    statuses: Dict[str, str]
    readiness_pct: float
    per_pillar: List[dict]
    dependency_violations: List[dict]
    unresolved_flaws: List[dict]
    next_pillar: str | None
    roadmap: List[str] = field(default_factory=list)


def _normalize(capabilities: Dict[str, str]) -> Dict[str, str]:
    """Default any unstated pillar to 'missing'; validate status values."""
    out: Dict[str, str] = {}
    for key in PILLAR_ORDER:
        status = capabilities.get(key, "missing")
        if status not in STATUSES:
            raise ValueError(
                f"pillar {key!r} has invalid status {status!r}; "
                f"expected one of {STATUSES}"
            )
        out[key] = status
    unknown = set(capabilities) - set(PILLAR_ORDER)
    if unknown:
        raise ValueError(f"unknown pillar keys: {sorted(unknown)}")
    return out


def dependency_violations(statuses: Dict[str, str]) -> List[dict]:
    """
    A pillar is a violation when it is present/partial but a lower pillar it
    requires is missing. The chapter is explicit that this is structurally
    impossible to do well: "Knowledge representation must come first because
    every other pillar depends on the knowledge graph."
    """
    out: List[dict] = []
    for key in PILLAR_ORDER:
        if statuses[key] == "missing":
            continue
        missing_deps = [d for d in PILLARS[key].depends_on if statuses[d] == "missing"]
        if missing_deps:
            out.append({
                "pillar": key,
                "status": statuses[key],
                "missing_dependencies": missing_deps,
                "note": (
                    f"{PILLARS[key].name} is claimed {statuses[key]} but requires "
                    f"{', '.join(PILLARS[d].name for d in missing_deps)}, which "
                    "is missing. A higher pillar cannot be sound while a lower "
                    "one it depends on is absent."
                ),
            })
    return out


def unresolved_flaws(statuses: Dict[str, str]) -> List[dict]:
    """
    A flaw is unresolved when NONE of the pillars that solve it is fully
    present. If any solving pillar is present the flaw is solved; if the best is
    partial the flaw is partially addressed; if all are missing it is unsolved.
    """
    out: List[dict] = []
    for flaw, pillars in FLAW_TO_PILLARS.items():
        best = max((_STATUS_WEIGHT[statuses[p]] for p in pillars), default=0.0)
        if best >= 1.0:
            continue  # solved
        out.append({
            "flaw": flaw,
            "solving_pillars": list(pillars),
            "state": "partial" if best > 0.0 else "unsolved",
            "best_pillar_status": {p: statuses[p] for p in pillars},
        })
    return out


def next_pillar(statuses: Dict[str, str]) -> str | None:
    """
    The lowest-order pillar that is not fully present. Because the pillars are
    layered, the next thing to build is always the earliest incomplete layer —
    building a higher pillar first would create a dependency violation.
    """
    for key in PILLAR_ORDER:
        if statuses[key] != "present":
            return key
    return None


def assess(capabilities: Dict[str, str]) -> ReadinessReport:
    """Full readiness map: score, per-pillar detail, violations, unresolved
    flaws, and the recommended next pillar with a roadmap."""
    statuses = _normalize(capabilities)
    weight_sum = sum(_STATUS_WEIGHT[statuses[k]] for k in PILLAR_ORDER)
    readiness = round(100.0 * weight_sum / len(PILLAR_ORDER), 1)

    per_pillar = []
    for key in PILLAR_ORDER:
        p = PILLARS[key]
        per_pillar.append({
            "pillar": key,
            "name": p.name,
            "chapter": p.chapter,
            "order": p.order,
            "status": statuses[key],
            "depends_on": list(p.depends_on),
            "solves_flaws": [f for f, ps in FLAW_TO_PILLARS.items() if key in ps]
                            or (["production_viability"] if p.production_only else []),
        })

    nxt = next_pillar(statuses)
    roadmap = [k for k in PILLAR_ORDER if statuses[k] != "present"]

    return ReadinessReport(
        statuses=statuses,
        readiness_pct=readiness,
        per_pillar=per_pillar,
        dependency_violations=dependency_violations(statuses),
        unresolved_flaws=unresolved_flaws(statuses),
        next_pillar=nxt,
        roadmap=roadmap,
    )


def initial_state() -> Dict[str, str]:
    """
    The DevOps agent's Chapter-2 initial state: fragmented tools, no graph.
    Knowledge representation is at best PARTIAL (the data exists in logs/metrics/
    configs but is not structured into a graph); every other pillar is missing.
    This is the "representation problem, not a technology problem" starting point.
    """
    return {
        "knowledge_representation": "partial",
        "memory": "missing",
        "reasoning": "missing",
        "planning": "missing",
        "tool_orchestration": "missing",
        "structured_output": "missing",
        "self_evolution": "missing",
        "optimization": "missing",
    }
