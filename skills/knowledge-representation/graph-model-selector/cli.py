#!/usr/bin/env python3
"""graph-model-selector CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    Requirements, score_models, recommend_model, HyperEdge,
    reify_as_property_graph, representation_cost, FEATURES, MODELS,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "graph-model-selector (Ch3)"
    text = SKILL_MD.read_text(encoding="utf-8")
    desc = []
    in_desc = False
    fm_count = 0
    in_frontmatter = False
    for line in text.splitlines():
        if line.strip() == "---":
            fm_count += 1
            in_frontmatter = fm_count == 1
            if fm_count == 2:
                break
            continue
        if not in_frontmatter:
            continue
        if line.startswith("description:"):
            in_desc = True
            continue
        if in_desc:
            if line and not line[0].isspace():
                in_desc = False
                continue
            desc.append(line.strip())
    return " ".join(d for d in desc if d) or "graph-model-selector"


def _reqs_from_args(args) -> Requirements:
    return Requirements(
        formal_reasoning=args.formal_reasoning,
        n_ary_relations=args.n_ary,
        performance=args.performance,
        tool_ecosystem=args.tool_ecosystem,
        constraint_expr=args.constraint_expr,
    )


def cmd_recommend(args):
    reqs = _reqs_from_args(args)
    print(json.dumps(recommend_model(reqs), indent=2))


def cmd_score(args):
    reqs = _reqs_from_args(args)
    print(json.dumps(dict(score_models(reqs)), indent=2))


def cmd_nary_cost(args):
    if args.edge_path:
        with open(args.edge_path) as f:
            spec = json.load(f)
        edge = HyperEdge(type=spec["type"], nodes=spec.get("nodes", {}),
                         attributes=spec.get("attributes", {}))
    else:
        # Default: the prescription example (Example 3-1).
        edge = HyperEdge(
            type="Prescription",
            nodes={"doctor": "dr_smith", "patient": "patient_jones",
                   "medication": "med_x", "dosage": "50mg",
                   "date": "tuesday", "condition": "condition_y"},
            attributes={"status": "active"},
        )
    out = {
        "cost": representation_cost(edge),
        "property_graph_reification": reify_as_property_graph(edge),
    }
    print(json.dumps(out, indent=2))


def cmd_scenario(args):
    if args.name != "medical-diagnosis":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("Medical diagnosis agent - needs native inference + n-ary events")
    print("=" * 70)
    # Diagnosis needs inference (Disease1 causes Symptom1) AND n-ary
    # prescriptions. Weight formal_reasoning + n_ary highest.
    reqs = Requirements(formal_reasoning=3, n_ary_relations=3,
                        performance=1, tool_ecosystem=1, constraint_expr=2)
    rec = recommend_model(reqs)
    print(json.dumps(rec, indent=2))
    print("\nN-ary prescription representation cost:")
    edge = HyperEdge(
        type="Prescription",
        nodes={"doctor": "dr_smith", "patient": "patient_jones",
               "medication": "med_x", "dosage": "50mg",
               "date": "tuesday", "condition": "condition_y"},
        attributes={"status": "active"},
    )
    print(json.dumps(representation_cost(edge), indent=2))


def cmd_benchmark(args):
    failures = []

    # Test 1: RDF wins when formal reasoning dominates.
    reqs = Requirements(formal_reasoning=3)
    if recommend_model(reqs)["recommended"] != "rdf":
        failures.append("formal-reasoning-only should pick rdf")

    # Test 2: hypergraph wins when n-ary dominates.
    reqs = Requirements(n_ary_relations=3)
    if recommend_model(reqs)["recommended"] != "hypergraph":
        failures.append("n-ary-only should pick hypergraph")

    # Test 3: property graph wins when performance + tooling dominate.
    reqs = Requirements(performance=3, tool_ecosystem=3)
    if recommend_model(reqs)["recommended"] != "property_graph":
        failures.append("perf+tooling should pick property_graph")

    # Test 4: zero requirements -> all scores zero, no crash.
    scored = score_models(Requirements())
    if any(s != 0 for _, s in scored):
        failures.append("zero requirements should score all models 0")

    # Test 5: hyperedge arity and participants.
    edge = HyperEdge(type="Prescription",
                     nodes={"a": 1, "b": 2, "c": 3, "d": 4, "e": 5})
    if edge.arity() != 5:
        failures.append(f"arity should be 5, got {edge.arity()}")

    # Test 6: n-ary cost - property graph pays 1+N, hypergraph pays 1.
    cost = representation_cost(edge)
    if cost["hypergraph_elements"] != 1:
        failures.append("hypergraph should represent n-ary in 1 element")
    if cost["property_graph_elements"] != 1 + 5:
        failures.append(f"property graph should pay 1+arity, got {cost['property_graph_elements']}")

    # Test 7: reification produces exactly 1 intermediate node + N edges.
    reif = reify_as_property_graph(edge)
    if reif["intermediate_nodes"] != 1 or reif["auxiliary_edges"] != 5:
        failures.append(f"reification wrong: {reif['intermediate_nodes']} nodes, {reif['auxiliary_edges']} edges")

    # Test 8: hybrid surfaces when top two are close (balanced reqs).
    reqs = Requirements(formal_reasoning=3, n_ary_relations=3)
    rec = recommend_model(reqs)
    # rdf strong on formal, hypergraph strong on n-ary -> close race.
    if not rec["hybrid_recommended"]:
        failures.append("balanced formal+n-ary should flag a hybrid")

    # Test 9: every model scored, scores ordered descending.
    scored = score_models(Requirements(formal_reasoning=1, n_ary_relations=1,
                                        performance=1, tool_ecosystem=1,
                                        constraint_expr=1))
    if len(scored) != len(MODELS):
        failures.append("all models must be scored")
    if [s for _, s in scored] != sorted([s for _, s in scored], reverse=True):
        failures.append("scores must be sorted descending")

    # Test 10: feature set is exactly the 5 chapter features.
    if set(FEATURES) != {"formal_reasoning", "n_ary_relations", "performance",
                         "tool_ecosystem", "constraint_expr"}:
        failures.append("feature set drifted from the 5 chapter features")

    total = 10
    print("=" * 70)
    print(f"graph-model-selector benchmark - {total - len(failures)}/{total} passed")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for x in failures:
            print(f"  - {x}")
        sys.exit(1)
    print("All gates passed.")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description=_skill_description())
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_req_args(p):
        p.add_argument("--formal-reasoning", type=int, default=0)
        p.add_argument("--n-ary", type=int, default=0)
        p.add_argument("--performance", type=int, default=0)
        p.add_argument("--tool-ecosystem", type=int, default=0)
        p.add_argument("--constraint-expr", type=int, default=0)

    p_rec = sub.add_parser("recommend", help="Recommend a graph model from requirements")
    add_req_args(p_rec)
    p_rec.set_defaults(func=cmd_recommend)

    p_score = sub.add_parser("score", help="Score all three models from requirements")
    add_req_args(p_score)
    p_score.set_defaults(func=cmd_score)

    p_nary = sub.add_parser("nary-cost", help="Compare n-ary representation cost across models")
    p_nary.add_argument("--edge-path", default=None, help="JSON {type, nodes, attributes}")
    p_nary.set_defaults(func=cmd_nary_cost)

    p_scen = sub.add_parser("scenario", help="Worked scenario (medical-diagnosis)")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
