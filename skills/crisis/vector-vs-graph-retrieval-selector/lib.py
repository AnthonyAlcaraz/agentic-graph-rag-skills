"""
Vector-vs-graph retrieval selector (Agentic Graph RAG, Ch1 — The Limitations
of Vector-Based Retrieval + GraphRAG).

Ch1 quantifies exactly where vector RAG succeeds and where it collapses, using
Microsoft's BenchmarkQED (which builds on the "From Local to Global: A GraphRAG
Approach to Query-Focused Summarization" paper). Queries are classified on two
axes:

  * SCOPE: local (specific facts in a small number of regions) vs
    global / sensemaking (reasoning over large portions of the dataset).
  * TYPE:  data (direct retrieval of facts) vs activity (interpretive /
    strategic).

The chapter's numeric anchors:

  * Vector RAG: ~90% accuracy on simple lookups (DataLocal); 20-30% on complex
    reasoning (ActivityGlobal). "The very mechanism that makes vector search
    efficient becomes its fundamental limitation."
  * LazyGraphRAG outperforms vector RAG by 50-60% on multi-hop reasoning.
  * EyeLevel.ai: vector accuracy drops up to 12% at 100,000 pages; graph drops
    only ~2% at the same scale.
  * The larger-context-window rebuttal: BenchmarkQED tested LazyGraphRAG vs
    vector RAG with a ~1-million-token window (essentially the whole dataset);
    vector RAG still lost on every query type except the most basic factual
    questions. Bigger windows also worsen the "lost in the middle" problem.

Ch1's own recommendation is a HYBRID architecture (parallel vector + graph:
vector search -> graph traversal -> context synthesis), because agentic
behavior "requires constantly moving between local and global understanding."

GraphRAG is not free — Ch1 names its struggles: heavy upfront graph
construction (best for structured/known domains), query latency that grows
with graph size, contextual nuance lost when condensing to triples, and
schema-evolution cost.

This module maps a query-workload description to VECTOR / GRAPH / HYBRID with
the chapter's rationale and numbers. Pure Python, stdlib only.
"""

from __future__ import annotations

from typing import Any, Dict, List

# BenchmarkQED quadrants (scope x type) with the chapter's vector-RAG behavior.
BENCHMARKQED_QUADRANTS: Dict[str, Dict[str, str]] = {
    "data_local": {
        "description": "Direct retrieval of specific facts in a small number of regions.",
        "vector_accuracy": "~90%",
        "verdict": "vector RAG excels — semantic similarity finds the source directly",
    },
    "activity_local": {
        "description": "Interpretive queries about local processes.",
        "vector_accuracy": "moderate (granularity trade-off: doc-level lacks precision, sentence-level fragments context)",
        "verdict": "mixed — coherent multi-step context is needed; hybrid helps",
    },
    "activity_global": {
        "description": "Holistic analysis and strategic insight across the dataset.",
        "vector_accuracy": "~20-30%",
        "verdict": "vector RAG catastrophically fails — returns similar-word chunks, misses the big picture",
    },
    "data_global": {
        "description": "Data patterns and synthesis across large portions of the dataset.",
        "vector_accuracy": "low — requires synthesis vector similarity cannot perform",
        "verdict": "graph / hybrid — sensemaking over the whole corpus",
    },
}

# Numeric anchors from the chapter, surfaced verbatim in the rationale.
ANCHORS = {
    "vector_local": "Vector RAG handles simple lookups (DataLocal) at ~90% accuracy.",
    "vector_global": "Vector RAG handles complex reasoning (ActivityGlobal) at just 20-30% accuracy.",
    "lazygraphrag_multihop": "LazyGraphRAG outperforms vector RAG by 50-60% on multi-hop reasoning.",
    "eyelevel_scale": "At 100,000 pages, vector accuracy drops up to 12%; graph drops only ~2%.",
    "linkedin": "LinkedIn's KG-augmented RAG cut median per-issue resolution time by 28.6% over six months.",
}


def larger_context_window_rebuttal() -> str:
    """Ch1's direct rebuttal to 'won't a larger context window solve this?'"""
    return (
        "No. BenchmarkQED tested this directly: LazyGraphRAG vs vector RAG with "
        "a ~1-million-token context window (essentially the entire dataset). "
        "Even with nearly all information in context, vector RAG still lost on "
        "every query type except the most basic factual questions. Dumping more "
        "information into a context window does not create understanding of "
        "relationships, temporal evolution, or systematic patterns — it makes "
        "retrieval slower and worsens the 'lost in the middle' problem. "
        "EyeLevel.ai quantifies the scale effect: vector accuracy drops up to "
        "12% at 100,000 pages while graph-based approaches drop only ~2%."
    )


def _quadrant(scope: str, qtype: str) -> str:
    return f"{qtype}_{scope}"


def recommend(
    query_scope: str = "local",
    query_type: str = "data",
    multi_hop: bool = False,
    temporal: bool = False,
    structured_domain: bool = True,
    dataset_scale_pages: int = 0,
    latency_critical: bool = False,
    agentic: bool = False,
    larger_context_window: bool = False,
    name: str = "workload",
) -> Dict[str, Any]:
    """Recommend VECTOR / GRAPH / HYBRID for a query workload.

    Args map to the chapter's decision factors:
      query_scope           'local' | 'global' | 'mixed'
      query_type            'data' | 'activity'
      multi_hop             requires traversing relationships across documents
      temporal              requires awareness of how things changed over time
      structured_domain     is the knowledge schema-known / structured? (GraphRAG feasibility)
      dataset_scale_pages   corpus size (EyeLevel degradation anchor)
      latency_critical      high-query-rate / low-latency requirement (GraphRAG struggle)
      agentic               an agent workload (needs to move local<->global) -> biases HYBRID
      larger_context_window caller is considering 'just use a bigger window' -> attach rebuttal
    """
    scope = query_scope.lower()
    qtype = query_type.lower()

    graph_signals: List[str] = []
    if scope == "global":
        graph_signals.append("global/sensemaking scope (vector RAG 20-30%)")
    if multi_hop:
        graph_signals.append("multi-hop reasoning (LazyGraphRAG +50-60%)")
    if temporal:
        graph_signals.append("temporal awareness (static embeddings freeze the world)")
    if scope == "global" and qtype == "activity":
        graph_signals.append("ActivityGlobal quadrant — vector RAG catastrophic failure")

    vector_signals: List[str] = []
    if scope == "local" and qtype == "data":
        vector_signals.append("DataLocal quadrant (vector RAG ~90%)")
    if latency_critical:
        vector_signals.append("latency-critical (graph traversal is slower than ANN lookup)")
    if not structured_domain:
        vector_signals.append("unstructured/open-domain (graph construction impractical)")

    # Decision.
    reasons: List[str] = []
    if scope == "mixed" or agentic:
        recommendation = "HYBRID"
        reasons.append(
            "Agentic / mixed workloads must move constantly between local and "
            "global understanding; Ch1 recommends the parallel vector + graph "
            "hybrid (vector search -> graph traversal -> context synthesis)."
        )
        if graph_signals:
            reasons.append("Graph-favoring signals present: " + "; ".join(graph_signals) + ".")
        if vector_signals:
            reasons.append("Vector-favoring signals present: " + "; ".join(vector_signals) + ".")
    elif graph_signals and structured_domain and not latency_critical:
        recommendation = "GRAPH"
        reasons.append("Graph-favoring signals dominate: " + "; ".join(graph_signals) + ".")
        reasons.append(
            "The domain is structured and latency is not critical, so the "
            "upfront graph-construction cost is worth paying."
        )
    elif graph_signals and (not structured_domain or latency_critical):
        recommendation = "HYBRID"
        reasons.append("Graph-favoring signals present: " + "; ".join(graph_signals) + ".")
        blocker = "unstructured domain" if not structured_domain else "latency-critical path"
        reasons.append(
            f"but a {blocker} makes pure GraphRAG costly — run vector first, "
            "traverse the graph selectively, synthesize (Ch1 hybrid)."
        )
    elif not graph_signals and vector_signals:
        recommendation = "VECTOR"
        reasons.append("Vector-favoring signals, no graph-favoring signals: " + "; ".join(vector_signals) + ".")
        reasons.append(
            "Ch1: vector RAG is a great fit for local, fact-based lookups "
            "(customer support, FAQ, recommendation)."
        )
    else:
        recommendation = "HYBRID"
        reasons.append(
            "No dominant signal either way — default to the hybrid architecture "
            "Ch1 recommends so you gain multi-hop and temporal capability without "
            "losing vector's local-lookup strength."
        )

    quadrant_key = _quadrant(scope if scope in ("local", "global") else "global", qtype)
    quadrant = BENCHMARKQED_QUADRANTS.get(quadrant_key)

    out: Dict[str, Any] = {
        "name": name,
        "recommendation": recommendation,
        "reasons": reasons,
        "graph_signals": graph_signals,
        "vector_signals": vector_signals,
        "benchmarkqed_quadrant": {"key": quadrant_key, **quadrant} if quadrant else None,
        "anchors": [
            ANCHORS["vector_local"],
            ANCHORS["vector_global"],
            ANCHORS["lazygraphrag_multihop"],
        ],
    }
    if dataset_scale_pages >= 100000:
        out["scale_note"] = ANCHORS["eyelevel_scale"]
    if larger_context_window:
        out["larger_context_window_rebuttal"] = larger_context_window_rebuttal()
    if recommendation in ("GRAPH", "HYBRID"):
        out["graphrag_costs"] = [
            "Upfront graph construction — data must be structured or extracted (best for known domains).",
            "Query latency grows with graph size and hop count (slower than ANN lookup).",
            "Condensing to triples can lose contextual nuance/qualifiers from source text.",
            "Schema evolution requires reconciliation with the existing ontology.",
        ]
    return out


def recommend_batch(workloads: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Recommend for several workloads and tally the recommendations."""
    results = [recommend(**{k: v for k, v in w.items() if k != "note"}) for w in workloads]
    tally: Dict[str, int] = {}
    for r in results:
        tally[r["recommendation"]] = tally.get(r["recommendation"], 0) + 1
    return {"results": results, "tally": tally}
