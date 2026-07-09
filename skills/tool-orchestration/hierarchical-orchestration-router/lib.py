"""
Hierarchical orchestration router — one entry point, domain routing, functional
clustering for failover.

Distilled from Agentic Graph RAG (O'Reilly), Chapter 6 — Tool Orchestration
("Orchestration at Scale": The Intelligent Orchestrator / Hierarchical
Orchestration / Functional Clustering: Resilience Through Redundancy).

Three composed ideas:

1. INVERSION — instead of exposing thousands of tools to the agent, expose
   exactly one: an orchestrator that handles all the complexity. The agent asks
   for an outcome; the orchestrator decides how.

2. HIERARCHICAL ROUTING — as organizations grow they have multiple MCP servers
   across departments (Sales, Finance, Operations), each managing hundreds of
   tools. The orchestrator classifies a query into a domain by semantics; if
   confidence is high (>0.8) it routes to that domain's orchestrator, otherwise
   the query spans domains and it invokes cross-domain orchestration (chapter
   Example 6-11). This gives fault isolation, scalable governance, and
   progressive disclosure.

3. FUNCTIONAL CLUSTERING — within a domain, tools with similar FUNCTION are
   clustered for intelligent failover. Baidu's AI Search Paradigm embeds tools
   by what they DO (DRAFT-refined docs + usage patterns), then K-means++ groups
   them into functional toolkits. When the primary tool is overloaded, the
   orchestrator fails over to a functionally-equivalent alternative from the
   same cluster (a "Search Toolkit": Baidu AI Search / ArXiv MCP / Perplexity /
   OpenAI WebSearch), adapting parameters as needed. No single point of failure.

STDLIB ONLY. Domain classification uses word overlap and functional clustering
uses shared-topic connected components; production swaps both for embeddings.
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
    "which who whom whose how can could should would do does did why".split()
)

DEFAULT_CONFIDENCE_THRESHOLD = 0.8  # chapter Example 6-11


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text) if t.lower() not in _STOPWORDS}


def load_config(path: str | Path) -> dict:
    """Load domains (hierarchy) and tools (for functional clustering)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------
# Hierarchical domain routing
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class DomainMatch:
    domain: str
    confidence: float
    scores: dict


def identify_domain(query: str, domains: list[dict]) -> DomainMatch:
    """
    Classify the query into a domain by semantic overlap with each domain's
    keywords. Confidence is a MARGIN: top_score / (top_score + second_score),
    so a query that clearly belongs to one domain scores near 1.0, while a query
    spanning two domains scores near 0.5 — which is what triggers cross-domain
    routing below the 0.8 threshold.

    # TODO(production): replace word-overlap keyword matching with an embedding
    # classifier trained on real query->domain routing history. The contract
    # (returns a domain + a [0,1] confidence) is the seam.
    """
    q = _tokenize(query)
    raw: dict[str, float] = {}
    for d in domains:
        kw = _tokenize(" ".join(d.get("keywords", [])))
        overlap = len(q & kw)
        raw[d["name"]] = float(overlap)
    ranked = sorted(raw.items(), key=lambda kv: kv[1], reverse=True)
    top_name, top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if top == 0.0:
        confidence = 0.0
    else:
        confidence = top / (top + second)
    return DomainMatch(domain=top_name, confidence=round(confidence, 3), scores=raw)


def route_request(
    query: str, domains: list[dict], threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
) -> dict:
    """
    The hierarchical router (chapter Example 6-11). High confidence -> route to
    one domain orchestrator. Low confidence -> the query spans domains, so
    orchestrate cross-domain.
    """
    match = identify_domain(query, domains)
    if match.confidence < threshold:
        # Which domains does it span? Any domain with a non-zero score.
        spanning = [name for name, s in
                    sorted(match.scores.items(), key=lambda kv: kv[1], reverse=True)
                    if s > 0]
        return {
            "routing": "cross_domain",
            "confidence": match.confidence,
            "domains": spanning[:2] if spanning else [match.domain],
            "reason": f"confidence {match.confidence} < threshold {threshold}",
        }
    return {
        "routing": "domain",
        "domain": match.domain,
        "confidence": match.confidence,
        "reason": f"confidence {match.confidence} >= threshold {threshold}",
    }


# ----------------------------------------------------------------------------
# Functional clustering for resilience
# ----------------------------------------------------------------------------

def cluster_tools(tools: list[dict]) -> list[dict]:
    """
    Group tools into functional toolkits by shared function. Two tools join the
    same cluster if they share at least one key_topic (connected components over
    the shared-topic graph). This approximates the chapter's "embed tools based
    on what they do, then K-means++ into functional toolkits".

    # TODO(production): replace shared-topic connected-components with K-means++
    # over DRAFT-refined tool embeddings (chapter: Baidu's AI Search Paradigm).
    # The contract (returns a list of {cluster_id, members}) is the seam.
    """
    n = len(tools)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    topic_sets = [set(t.get("key_topics", [])) for t in tools]
    for i in range(n):
        for j in range(i + 1, n):
            if topic_sets[i] & topic_sets[j]:
                union(i, j)

    clusters: dict[int, list[dict]] = {}
    for i, tool in enumerate(tools):
        clusters.setdefault(find(i), []).append(tool)

    out = []
    for cid, members in enumerate(clusters.values()):
        shared = set.intersection(*[set(m.get("key_topics", [])) for m in members]) \
            if members else set()
        out.append({
            "cluster_id": cid,
            "shared_topics": sorted(shared),
            "members": [m["name"] for m in members],
        })
    return out


def failover(tools: list[dict], failed_tool: str) -> dict:
    """
    On overload/failure of `failed_tool`, return a functionally-equivalent
    alternative from the SAME functional cluster (chapter: seamlessly switch to
    a functionally equivalent alternative; the orchestrator adapts parameters).

    Preference order within the cluster: highest `reliability` first (a
    performance-based signal, as from draft-tool-trust-verifier), then name.
    """
    clusters = cluster_tools(tools)
    by_name = {t["name"]: t for t in tools}
    if failed_tool not in by_name:
        raise KeyError(f"Tool {failed_tool!r} not in the tool set.")
    home = next((c for c in clusters if failed_tool in c["members"]), None)
    if home is None:
        return {"failed": failed_tool, "alternative": None, "reason": "no cluster"}
    candidates = [m for m in home["members"] if m != failed_tool]
    if not candidates:
        return {
            "failed": failed_tool,
            "alternative": None,
            "cluster_id": home["cluster_id"],
            "reason": "single point of failure — no functionally-equivalent alternative",
        }
    candidates.sort(key=lambda name: (-by_name[name].get("reliability", 0.5), name))
    chosen = candidates[0]
    return {
        "failed": failed_tool,
        "alternative": chosen,
        "cluster_id": home["cluster_id"],
        "shared_topics": home["shared_topics"],
        "adapts_parameters": True,
        "reason": "functionally-equivalent alternative from same cluster",
    }


# ----------------------------------------------------------------------------
# Inversion — the single orchestrator entry point
# ----------------------------------------------------------------------------

def orchestrate(query: str, config: dict, threshold: float = DEFAULT_CONFIDENCE_THRESHOLD) -> dict:
    """
    The single tool the agent sees (INVERSION). It routes the query through the
    hierarchy and, for a resolved domain, names the functional clusters
    available for failover — all hidden behind one call.
    """
    domains = config.get("domains", [])
    tools = config.get("tools", [])
    routing = route_request(query, domains, threshold=threshold)
    result = {"query": query, "routing": routing}
    if routing["routing"] == "domain":
        domain = next((d for d in domains if d["name"] == routing["domain"]), None)
        domain_tool_names = set(domain.get("tools", [])) if domain else set()
        domain_tools = [t for t in tools if t["name"] in domain_tool_names]
        result["available_clusters"] = cluster_tools(domain_tools) if domain_tools else []
    return result
