"""
Graph data model selection (property-graph vs RDF vs hypergraph) and the
n-ary -> hyperedge representation, distilled from Ch3 "Graph Data Models" /
"Evaluating Graph Models".

The chapter's central claim: start from REASONING REQUIREMENTS, not data.
Each model is scored across five implementation features:

  formal_reasoning      RDF >> hypergraph > property
  n_ary_relations       hypergraph >> property ~ RDF (RDF needs reification)
  performance           property >> hypergraph > RDF
  tool_ecosystem        property >> RDF > hypergraph
  constraint_expr       roughly equal (all push complex constraints to app layer)

Pure Python, stdlib only. No graph database required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


MODELS = ("property_graph", "rdf", "hypergraph")

# Per-model scores per feature, on a 0..3 ordinal scale distilled from the
# "Evaluating Graph Models" section. Higher == stronger on that axis.
# Sources: formal reasoning (RDF excels), n-ary (hypergraphs native),
# performance (property graphs high), tool ecosystem (property graphs robust),
# constraint expressiveness (all limited; RDF slightly ahead via SHACL/OWL).
MODEL_FEATURE_SCORES: Dict[str, Dict[str, int]] = {
    "property_graph": {
        "formal_reasoning": 1, "n_ary_relations": 2, "performance": 3,
        "tool_ecosystem": 3, "constraint_expr": 1,
    },
    "rdf": {
        "formal_reasoning": 3, "n_ary_relations": 1, "performance": 1,
        "tool_ecosystem": 2, "constraint_expr": 2,
    },
    "hypergraph": {
        "formal_reasoning": 2, "n_ary_relations": 3, "performance": 2,
        "tool_ecosystem": 1, "constraint_expr": 1,
    },
}

FEATURES = ("formal_reasoning", "n_ary_relations", "performance",
            "tool_ecosystem", "constraint_expr")


@dataclass
class Requirements:
    """Caller-supplied reasoning requirements, each a weight 0..3.

    formal_reasoning: need native inference / consistency checking (e.g.
        Disease1 causes Symptom1 + Patient has Symptom1 => infer diagnosis).
    n_ary_relations: relationships routinely involve >2 entities
        (prescription = doctor+patient+medication+dosage+date+condition).
    performance: traversal-intensive / real-time analytics matters more
        than inference.
    tool_ecosystem: team needs mature databases, viz, connectors out of box.
    constraint_expr: need to express complex integrity/business-rule
        constraints in the model itself.
    """
    formal_reasoning: int = 0
    n_ary_relations: int = 0
    performance: int = 0
    tool_ecosystem: int = 0
    constraint_expr: int = 0

    def as_weights(self) -> Dict[str, int]:
        return {f: int(getattr(self, f)) for f in FEATURES}


def score_models(reqs: Requirements) -> List[Tuple[str, float]]:
    """Weighted dot-product of requirement weights and per-model feature
    scores. Returns [(model, score), ...] sorted descending.
    """
    weights = reqs.as_weights()
    scored: List[Tuple[str, float]] = []
    for model in MODELS:
        feats = MODEL_FEATURE_SCORES[model]
        total = float(sum(weights[f] * feats[f] for f in FEATURES))
        scored.append((model, total))
    scored.sort(key=lambda kv: kv[1], reverse=True)
    return scored


def recommend_model(reqs: Requirements) -> Dict[str, Any]:
    """Pick a model and explain. Surfaces the hybrid recommendation when the
    top two scores are close (the chapter: "a hybrid approach ... might offer
    the most robust solution")."""
    scored = score_models(reqs)
    top_model, top_score = scored[0]
    second_model, second_score = scored[1]
    # Hybrid when the leader's margin over #2 is thin AND both non-trivial.
    margin = top_score - second_score
    hybrid = top_score > 0 and second_score > 0 and margin <= max(1.0, 0.25 * top_score)
    rationale = _RATIONALE[top_model]
    rec = {
        "recommended": top_model,
        "scores": dict(scored),
        "rationale": rationale,
        "hybrid_recommended": hybrid,
    }
    if hybrid:
        rec["hybrid"] = f"{top_model} + {second_model}"
        rec["hybrid_note"] = (
            f"Top two scores are within {margin:.1f}; consider a hybrid "
            f"(e.g. {top_model} for its strength, {second_model} layered for "
            "the other axis) per Ch3 'Putting it all together'."
        )
    return rec


_RATIONALE = {
    "property_graph": ("High-performance traversals, flexible modeling, mature "
                       "tool ecosystem (Neo4j/Neptune/ArangoDB). Reasoning is "
                       "application-level, not native."),
    "rdf": ("Formal logical semantics enable native inference, consistency "
            "checking, semantic interoperability. Slower; n-ary needs "
            "reification; pair with SHACL for constraint validation."),
    "hypergraph": ("Native n-ary relations via hyperedges (one edge connects "
                   "many entities, no auxiliary reification nodes). Underdeveloped "
                   "ecosystem; moderate performance."),
}


# ---------------------------------------------------------------------------
# N-ary relation representation. The chapter (Example 3-1) shows a prescription
# as a single hyperedge vs the binary-relation reification a property graph or
# RDF would force.
# ---------------------------------------------------------------------------

@dataclass
class HyperEdge:
    """A single relationship connecting any number of named participants.

    Mirrors Example 3-1: prescription connects doctor, patient, medication,
    dosage, date, condition in one structure -- semantic unity preserved.
    """
    type: str
    nodes: Dict[str, Any] = field(default_factory=dict)
    attributes: Dict[str, Any] = field(default_factory=dict)

    def arity(self) -> int:
        return len(self.nodes)

    def participants(self) -> List[str]:
        return list(self.nodes.keys())


def reify_as_property_graph(edge: HyperEdge) -> Dict[str, Any]:
    """Show the cost: representing an n-ary relation in a binary-edge model
    requires an intermediate "relation node" plus one edge per participant.

    Returns a node/edge listing. The arity-N hyperedge becomes 1 relation
    node + N edges (the "artificial complexity" the chapter warns about).
    """
    rel_node_id = f"{edge.type}__relation"
    nodes = [{"id": rel_node_id, "label": edge.type, "props": dict(edge.attributes)}]
    edges = []
    for role, participant in edge.nodes.items():
        pid = f"{role}:{participant}"
        nodes.append({"id": pid, "label": role, "value": participant})
        edges.append({"from": rel_node_id, "to": pid, "type": f"has_{role}"})
    return {
        "intermediate_nodes": 1,
        "auxiliary_edges": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


def representation_cost(edge: HyperEdge) -> Dict[str, int]:
    """Compare graph-structure cost of the same n-ary fact across models.

    hypergraph: 1 element (the hyperedge itself).
    property_graph / rdf-reification: 1 intermediate node + N edges.
    """
    n = edge.arity()
    return {
        "arity": n,
        "hypergraph_elements": 1,
        "property_graph_elements": 1 + n,   # 1 relation node + n edges
        "rdf_reified_triples": 1 + n,       # type triple + n property triples
    }
