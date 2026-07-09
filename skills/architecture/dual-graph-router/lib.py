"""
Dual-graph router (Ch2 — "The Dual-Graph Architecture" + "Where the Two Graphs
Meet").

The central architectural concept of the book is that an agentic system needs
two complementary kinds of structure:

  * the VERTICAL knowledge graph  — a representation of what the agent KNOWS
    (entities, relationships, constraints). "The vertical graph is the map."
    Queries against it are single traversals: "what depends on payments-db and
    was deployed in the last 24h" is one MATCH, not a workflow.

  * the HORIZONTAL workflow graph — a representation of how the agent ACTS
    (reasoning, execution, decision, validation nodes and their dependencies).
    "The horizontal graph is the route." It decomposes a task into inspectable
    steps.

This module routes an incoming request to one of those structures. The chapter's
"Where the Two Graphs Meet" section is the load-bearing case: a complex request
(diagnose, investigate, remediate) is a HORIZONTAL workflow whose nodes QUERY
the VERTICAL graph for context and write results back. The router names that
case explicitly as `both` (workflow drives, knowledge supplies and receives)
rather than collapsing it into one graph.

Pure Python, stdlib only. No graph database, no model call.

Production swap: the signal-keyword scoring in `_score` is a deliberately
transparent heuristic. In production a routing/reasoning node classifies the
request with an LLM (or a fine-tuned intent classifier). The routing CONTRACT
(vertical / horizontal / both / unroutable + a rationale) is the stable seam.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Set

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")

# VERTICAL signals — a request that asks WHAT IS TRUE about entities and their
# relationships: a lookup or traversal answerable by one graph query. Grounded
# in Ch2 "The Vertical Knowledge Graph" (nodes/edges/properties, DEPENDS_ON
# traversal, temporal `since` metadata, point-in-time queries).
VERTICAL_SIGNALS: Set[str] = frozenset(
    "depends dependency dependencies depend connected connection relationship "
    "relationships traverse traversal list lookup look-up which what who "
    "when since history historical deployed connects uses upstream downstream "
    "transitive node nodes edge edges property properties entity entities "
    "graph topology neighbors reachable path".split()
)

# HORIZONTAL signals — a request that asks the agent to CARRY OUT A PROCESS: a
# multi-step investigation, decision, or action. Grounded in Ch2 "The
# Horizontal Workflow Graph" (reasoning / execution / decision / validation
# nodes) and the DevOps latency investigation (Example 2-3).
HORIZONTAL_SIGNALS: Set[str] = frozenset(
    "diagnose investigate investigation why root-cause rootcause cause "
    "correlate remediate remediation rollback fix respond response resolve "
    "plan decide decision step steps workflow orchestrate classify analyze "
    "analysis figure determine handle triage mitigate recover prevent predict "
    "should how".split()
)

# Requests carrying no signal from either set are unroutable — neither graph
# fits without more information (the chapter's "ambiguous situation" the agent
# should resolve by asking, not guessing).
_TARGETS = ("vertical", "horizontal", "both", "unroutable")


@dataclass(frozen=True)
class RouteDecision:
    request: str
    target: str                      # one of _TARGETS
    vertical_score: int
    horizontal_score: int
    matched_vertical: List[str] = field(default_factory=list)
    matched_horizontal: List[str] = field(default_factory=list)
    rationale: str = ""
    node_hint: str = ""              # how the chosen structure handles it


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _score(tokens: List[str], signals: Set[str]) -> List[str]:
    """Return the (deduped, order-preserving) list of matched signal tokens."""
    seen: Set[str] = set()
    matched: List[str] = []
    for t in tokens:
        if t in signals and t not in seen:
            seen.add(t)
            matched.append(t)
    return matched


def route(request: str) -> RouteDecision:
    """
    Route a request to the vertical graph, the horizontal graph, both, or
    neither.

    Decision rule (Ch2):
      * horizontal AND vertical signal present -> `both`. This is the
        "Where the Two Graphs Meet" case: the workflow graph drives the process
        and its nodes query the vertical graph for grounding, then write results
        back. The architecture's value emerges at the intersection.
      * horizontal only -> `horizontal`. A process with no explicit knowledge
        lookup in the request (its nodes may still query the KG at run time).
      * vertical only -> `vertical`. A single-traversal knowledge question.
      * neither -> `unroutable`. Ask for clarification rather than guess.
    """
    tokens = _tokenize(request)
    mv = _score(tokens, VERTICAL_SIGNALS)
    mh = _score(tokens, HORIZONTAL_SIGNALS)
    vs, hs = len(mv), len(mh)

    if hs and vs:
        target = "both"
        rationale = (
            "The request names a process (horizontal signal) that also needs "
            "domain facts (vertical signal). Per 'Where the Two Graphs Meet', "
            "the workflow graph drives the investigation and its reasoning / "
            "retrieval nodes traverse the vertical knowledge graph for context, "
            "then write results (e.g. a CAUSED_BY edge) back."
        )
        node_hint = (
            "Build a horizontal workflow (reasoning/execution/decision/"
            "validation nodes); wire a retrieval node that traverses the "
            "vertical graph and feeds the reasoning node."
        )
    elif hs:
        target = "horizontal"
        rationale = (
            "The request asks the agent to carry out a multi-step process with "
            "no explicit knowledge lookup in the wording. Route to the "
            "horizontal workflow graph; decompose into focused nodes."
        )
        node_hint = (
            "Decompose into reasoning/execution/decision/validation nodes; the "
            "nodes may still query the vertical graph at run time."
        )
    elif vs:
        target = "vertical"
        rationale = (
            "The request is a knowledge question answerable by one graph "
            "traversal (relationship or temporal lookup). Route to the vertical "
            "knowledge graph; no workflow decomposition needed."
        )
        node_hint = (
            "Express as a single MATCH/traversal over typed edges "
            "(e.g. DEPENDS_ON) with optional temporal (`since`) filters."
        )
    else:
        target = "unroutable"
        rationale = (
            "No vertical or horizontal signal detected. Neither graph fits "
            "without clarification; ask the user rather than guessing "
            "(the chapter's ambiguous-situation discipline)."
        )
        node_hint = "Request clarification: is this a lookup or an action?"

    return RouteDecision(
        request=request,
        target=target,
        vertical_score=vs,
        horizontal_score=hs,
        matched_vertical=mv,
        matched_horizontal=mh,
        rationale=rationale,
        node_hint=node_hint,
    )


def explain_meeting_point(decision: RouteDecision) -> Dict[str, str]:
    """
    For a `both` decision, spell out the bidirectional interaction the chapter
    describes: the workflow graph supplies the process skeleton, the knowledge
    graph supplies (and receives) the facts. Returns an empty dict for other
    targets.
    """
    if decision.target != "both":
        return {}
    return {
        "workflow_role": (
            "process skeleton — coordinates the inquiry: which node runs, in "
            "what order, waiting on which inputs (the DAG)."
        ),
        "knowledge_role": (
            "information substrate — a retrieval node traverses DEPENDS_ON / "
            "temporal edges instead of searching text chunks."
        ),
        "forward_flow": (
            "workflow -> knowledge: reasoning/retrieval nodes query the vertical "
            "graph for context (affected services, dependency chain, history)."
        ),
        "backward_flow": (
            "knowledge <- workflow: when the process concludes, the result "
            "updates the vertical graph (e.g. a new CAUSED_BY edge, an updated "
            "service status). Each graph makes the other more useful."
        ),
    }


def route_batch(requests: List[str]) -> List[RouteDecision]:
    """Route a list of requests. Convenience wrapper for the CLI + notebook."""
    return [route(r) for r in requests]
