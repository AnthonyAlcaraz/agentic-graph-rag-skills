#!/usr/bin/env python3
"""semantic-backprop-attributor CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    NodeIO,
    SemanticFeedback,
    attribute,
    backprop,
    generate_feedback,
    neighbor_context_for,
    predecessors_of,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "semantic-backprop-attributor primitive (Ch7)"
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
    return " ".join(d for d in desc if d) or "semantic-backprop-attributor (Ch7)"


# -- scenario builders ----------------------------------------------------


def _currency_graph():
    edges = [
        ("Extractor", "CurrencyConverter"),
        ("CurrencyConverter", "Validator"),
        ("DateChecker", "Validator"),
    ]
    node_outputs = {
        "Extractor": "Revenue: $10M",
        "CurrencyConverter": "EUR 9.5M",
        "DateChecker": "Date: 2022",
        "Validator": "2022 exchange rate was 0.9 not 0.95",
    }
    predicted = "EUR 9.5M"
    actual = "EUR 9.0M; 2022 exchange rate was 0.9 not 0.95"
    return edges, node_outputs, "Validator", predicted, actual


def _devops_graph():
    edges = [
        ("ChangelogRetrieval", "CausalAttributionNode"),
        ("KnowledgeGraphQuery", "CausalAttributionNode"),
    ]
    node_outputs = {
        "ChangelogRetrieval": (
            "Changelog contained: (1) deprecated batch_charge, (2) new async "
            "methods, (3) default connection_timeout reduced from 30s to 10s"
        ),
        "KnowledgeGraphQuery": (
            "checkout-service uses payments.charge() and payments.retrieve(); "
            "no batch_charge usage found"
        ),
        "CausalAttributionNode": "API contract violation",
    }
    predicted = "API contract violation"
    actual = "Connection pool exhaustion from timeout reduction (30s->10s)"
    feedback_text = (
        "When classifying changelog changes, treat connection configuration "
        "defaults (timeouts, pool sizes, retry policies) as a separate hypothesis "
        "category with equal priority to API contract changes. The timeout change "
        "(30s->10s) was present in your input but not explored as a failure "
        "pathway. For services with high throughput, configuration defaults often "
        "have higher failure probability than API deprecations."
    )
    return edges, node_outputs, "CausalAttributionNode", predicted, actual, feedback_text


# -- commands -------------------------------------------------------------


def cmd_feedback(args):
    with open(args.path, encoding="utf-8") as f:
        data = json.load(f)
    edges = [tuple(e) for e in data["edges"]]
    fb = backprop(
        edges=edges,
        node_outputs=data["node_outputs"],
        failure_node=data["failure_node"],
        predicted=data["predicted"],
        actual=data["actual"],
        feedback_text=data.get("feedback_text", ""),
    )
    print(json.dumps(fb.to_dict(), indent=2))


def cmd_attribute(args):
    with open(args.path, encoding="utf-8") as f:
        data = json.load(f)
    edges = [tuple(e) for e in data["edges"]]
    responsible = attribute(
        edges=edges,
        node_outputs=data["node_outputs"],
        failure_node=data["failure_node"],
        predicted=data["predicted"],
        actual=data["actual"],
    )
    print(json.dumps({
        "failure_node": data["failure_node"],
        "responsible_node": responsible,
        "surfaced_but_not_responsible": responsible != data["failure_node"],
    }, indent=2))


def cmd_scenario(args):
    if args.name == "currency":
        edges, node_outputs, failure_node, predicted, actual = _currency_graph()
        print("=" * 70)
        print("Currency conversion - neighbor-aware credit assignment")
        print("=" * 70)
        print("Graph: Extractor -> CurrencyConverter -> Validator; DateChecker -> Validator")
        for n, o in node_outputs.items():
            print(f"  {n}: {o}")
        responsible = attribute(edges, node_outputs, failure_node, predicted, actual)
        print(f"\nError surfaced at : {failure_node}")
        print(f"Attributed to     : {responsible}")
        print(f"Extractor changed : {'YES' if responsible == 'Extractor' else 'no (left unchanged)'}")
        fb = backprop(edges, node_outputs, failure_node, predicted, actual)
        print("\nNeighbor-aware feedback:")
        print(json.dumps(fb.to_dict(), indent=2))
        return
    if args.name == "devops-prediction":
        edges, node_outputs, failure_node, predicted, actual, feedback_text = _devops_graph()
        print("=" * 70)
        print("DevOps prediction - neighbor-aware feedback (Ch7 Example 7-19)")
        print("=" * 70)
        print("Running example context:")
        print("  AWS account 123456789012")
        print("  stripe-python 3.2.1 -> 3.3.0 (default connection_timeout 30s -> 10s)")
        print("  service chain: checkout-service -> order-service -> fulfillment-service")
        print("Graph: ChangelogRetrieval + KnowledgeGraphQuery -> CausalAttributionNode")
        responsible = attribute(edges, node_outputs, failure_node, predicted, actual)
        print(f"\nAttributed to: {responsible}")
        fb = backprop(edges, node_outputs, failure_node, predicted, actual, feedback_text)
        print("\nExample 7-19 neighbor-aware semantic feedback:")
        print(json.dumps(fb.to_dict(), indent=2))
        return
    print(f"unknown scenario: {args.name}", file=sys.stderr)
    sys.exit(1)


def cmd_benchmark(args):
    failures = []

    cur_edges, cur_outputs, cur_fail, cur_pred, cur_act = _currency_graph()
    dev_edges, dev_outputs, dev_fail, dev_pred, dev_act, dev_text = _devops_graph()

    # Test 1: predecessors_of returns correct parents
    preds = predecessors_of(cur_edges, "Validator")
    if preds != ["CurrencyConverter", "DateChecker"]:
        failures.append(f"predecessors_of(Validator) wrong: {preds}")
    if predecessors_of(cur_edges, "CurrencyConverter") != ["Extractor"]:
        failures.append("predecessors_of(CurrencyConverter) should be [Extractor]")

    # Test 2: neighbor_context_for excludes target, includes sibling predecessor
    ctx = neighbor_context_for(cur_edges, cur_outputs, target_node="CurrencyConverter", successor="Validator")
    if "CurrencyConverter_output" in ctx:
        failures.append("neighbor_context_for should exclude the target node")
    if ctx.get("DateChecker_output") != "Date: 2022":
        failures.append(f"neighbor_context_for should include sibling DateChecker: {ctx}")

    # Test 3: currency scenario attributes to CurrencyConverter (NOT Extractor)
    responsible = attribute(cur_edges, cur_outputs, cur_fail, cur_pred, cur_act)
    if responsible != "CurrencyConverter":
        failures.append(f"currency attribution should be CurrencyConverter, got {responsible}")
    if responsible == "Extractor":
        failures.append("Extractor must be left unchanged")

    # Test 4: devops generated feedback contains the neighbor evidence (30s->10s in input)
    dev_fb = backprop(dev_edges, dev_outputs, dev_fail, dev_pred, dev_act)  # synthesize (empty text)
    if dev_fb.target_node != "CausalAttributionNode":
        failures.append(f"devops feedback target should be CausalAttributionNode, got {dev_fb.target_node}")
    if "30s" not in dev_fb.feedback:
        failures.append("synthesized devops feedback must name the 30s timeout neighbor evidence")
    if "ChangelogRetrieval_output" not in dev_fb.neighbor_context:
        failures.append("devops neighbor_context must include ChangelogRetrieval_output")

    # Test 5: SemanticFeedback.to_dict round-trips
    rt = SemanticFeedback.from_dict(dev_fb.to_dict())
    if rt.to_dict() != dev_fb.to_dict():
        failures.append("SemanticFeedback.to_dict did not round-trip")

    # Test 6: currency backprop routes feedback to CurrencyConverter with DateChecker neighbor
    cur_fb = backprop(cur_edges, cur_outputs, cur_fail, cur_pred, cur_act)
    if cur_fb.target_node != "CurrencyConverter":
        failures.append(f"currency backprop target should be CurrencyConverter, got {cur_fb.target_node}")
    if cur_fb.neighbor_context.get("DateChecker_output") != "Date: 2022":
        failures.append("currency feedback should carry DateChecker neighbor context")

    total = 6
    print("=" * 70)
    print(f"semantic-backprop-attributor benchmark - {total - len(failures)}/{total} passed")
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

    p_fb = sub.add_parser("feedback", help="Attribute then generate neighbor-aware feedback from a JSON graph")
    p_fb.add_argument("--path", required=True)
    p_fb.set_defaults(func=cmd_feedback)

    p_at = sub.add_parser("attribute", help="Return the responsible node for a failure from a JSON graph")
    p_at.add_argument("--path", required=True)
    p_at.set_defaults(func=cmd_attribute)

    p_sc = sub.add_parser("scenario", help="Run a worked scenario (currency | devops-prediction)")
    p_sc.add_argument("name")
    p_sc.set_defaults(func=cmd_scenario)

    p_bn = sub.add_parser("benchmark", help="Verification gate battery")
    p_bn.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
