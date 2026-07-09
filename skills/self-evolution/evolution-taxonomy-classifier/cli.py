#!/usr/bin/env python3
"""evolution-taxonomy-classifier CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    WHAT_EVOLVES,
    WHEN_FIRES,
    HOW_LEARNS,
    WHERE_APPLIES,
    EvolutionClassification,
    classify,
    classify_from_signals,
    route_failure,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "evolution-taxonomy-classifier (Ch7)"
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
    return " ".join(d for d in desc if d) or "evolution-taxonomy-classifier (Ch7)"


def cmd_axes(args):
    axes = [
        ("WHAT evolves", WHAT_EVOLVES),
        ("WHEN evolution fires", WHEN_FIRES),
        ("HOW the agent learns", HOW_LEARNS),
        ("WHERE evolution applies", WHERE_APPLIES),
    ]
    for title, d in axes:
        print("=" * 70)
        print(title)
        print("=" * 70)
        for value, rationale in d.items():
            print(f"  {value}")
            print(f"    {rationale}")
        print()


def cmd_classify(args):
    if args.path:
        with open(args.path, encoding="utf-8") as f:
            proposal = json.load(f)
        cls = classify(proposal)
    else:
        missing = [k for k in ("what", "when", "how", "where") if getattr(args, k) is None]
        if missing:
            print(
                f"provide --path OR all of --what --when --how --where "
                f"(missing: {missing})",
                file=sys.stderr,
            )
            sys.exit(1)
        cls = classify_from_signals(
            args.what, args.when, args.how, args.where, notes=args.notes or ""
        )
    print(json.dumps(cls.to_dict(), indent=2))


def cmd_route(args):
    result = route_failure(
        args.failure_type, recurring=args.recurring, is_format=args.format
    )
    print(json.dumps(result, indent=2))


def cmd_scenario(args):
    if args.name != "devops":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps prompt-refinement evolution - four-axis classification")
    print("=" * 70)
    notes = (
        "DevOps agent refines its prompt after a stripe-python 3.2.1->3.3.0 "
        "upgrade tightened a client timeout from 30s to 10s, causing cascade "
        "failures along checkout-service->order-service->fulfillment-service "
        "(fictional AWS account 123456789012). Reward: fewer cascade "
        "mispredictions on this microservice topology. The prompt is a model "
        "artifact, so this is model evolution; it runs overnight between "
        "requests; the reward is scalar; the target is one vertical."
    )
    cls = classify_from_signals(
        what="model",
        when="inter_test_time",
        how="reward_based",
        where="domain_specialized",
        notes=notes,
    )
    print(json.dumps(cls.to_dict(), indent=2))
    print("\nFailure routing for the diagnosed cascade-misprediction pattern:")
    print(json.dumps(route_failure("REASONING", recurring=True), indent=2))


def cmd_benchmark(args):
    failures = []

    # Test 1: every WHAT value validates
    for v in WHAT_EVOLVES:
        try:
            classify_from_signals(v, "inter_test_time", "reward_based", "general_purpose")
        except ValueError:
            failures.append(f"valid what value {v} rejected")

    # Test 2: every WHEN value validates
    for v in WHEN_FIRES:
        try:
            classify_from_signals("model", v, "reward_based", "general_purpose")
        except ValueError:
            failures.append(f"valid when value {v} rejected")

    # Test 3: every HOW value validates
    for v in HOW_LEARNS:
        try:
            classify_from_signals("model", "inter_test_time", v, "general_purpose")
        except ValueError:
            failures.append(f"valid how value {v} rejected")

    # Test 4: every WHERE value validates
    for v in WHERE_APPLIES:
        try:
            classify_from_signals("model", "inter_test_time", "reward_based", v)
        except ValueError:
            failures.append(f"valid where value {v} rejected")

    # Test 5: unknown value raises ValueError (each axis)
    for axis_kwargs in (
        {"what": "genes"},
        {"when": "whenever"},
        {"how": "vibes"},
        {"where": "everywhere"},
    ):
        base = {
            "what": "model",
            "when": "inter_test_time",
            "how": "reward_based",
            "where": "general_purpose",
        }
        base.update(axis_kwargs)
        try:
            classify_from_signals(**base)
            failures.append(f"unknown value {axis_kwargs} should raise ValueError")
        except ValueError:
            pass

    # Test 6: classify() maps a "fine-tune adapter" proposal to what=model
    c1 = classify({"description": "fine-tune adapter on domain failures"})
    if c1.what != "model":
        failures.append(f"'fine-tune adapter' should map to model, got {c1.what}")

    # Test 7: classify() maps a "rerank KG subgraph" proposal to what=context
    c2 = classify({"description": "rerank KG subgraph and prune stale nodes"})
    if c2.what != "context":
        failures.append(f"'rerank KG subgraph' should map to context, got {c2.what}")

    # Test 8: classify() maps a tool endpoint proposal to what=tool
    c3 = classify({"description": "register a new API endpoint for the agent"})
    if c3.what != "tool":
        failures.append(f"'API endpoint' should map to tool, got {c3.what}")

    # Test 9: route_failure(FORMAT) -> architecture / structural-constraint
    r = route_failure("FORMAT")
    if r["evolution_axis"] != "architecture" or r["mechanism"] != "structural-constraint":
        failures.append(f"FORMAT routing wrong: {r['evolution_axis']}/{r['mechanism']}")

    # Test 10: route_failure REASONING single-node -> model/prompt/intra;
    #          recurring -> model/fine-tune/inter
    r_single = route_failure("REASONING")
    if (r_single["evolution_axis"], r_single["mechanism"], r_single["timing"]) != (
        "model",
        "prompt",
        "intra_test_time",
    ):
        failures.append(f"REASONING single-node routing wrong: {r_single}")
    r_rec = route_failure("REASONING", recurring=True)
    if (r_rec["evolution_axis"], r_rec["mechanism"], r_rec["timing"]) != (
        "model",
        "fine-tune",
        "inter_test_time",
    ):
        failures.append(f"recurring REASONING routing wrong: {r_rec}")

    # Test 11: route_failure KNOWLEDGE -> context; recurring -> model/fine-tune
    r_k = route_failure("KNOWLEDGE")
    if r_k["evolution_axis"] != "context":
        failures.append(f"KNOWLEDGE routing should be context, got {r_k['evolution_axis']}")
    r_ks = route_failure("KNOWLEDGE", recurring=True)
    if r_ks["evolution_axis"] != "model" or r_ks["mechanism"] != "fine-tune":
        failures.append(f"systemic KNOWLEDGE routing wrong: {r_ks}")

    # Test 12: unknown failure_type raises ValueError
    try:
        route_failure("APOCALYPSE")
        failures.append("unknown failure_type should raise ValueError")
    except ValueError:
        pass

    # Test 13: graph_rationale populated for all four chosen axis values
    cls = classify_from_signals("model", "inter_test_time", "reward_based", "domain_specialized")
    gr = cls.graph_rationale
    if set(gr.keys()) != {"what", "when", "how", "where"}:
        failures.append(f"graph_rationale keys wrong: {sorted(gr.keys())}")
    if not all(isinstance(v, str) and v for v in gr.values()):
        failures.append("graph_rationale has empty or non-string values")

    # Test 14: to_dict round-trips through JSON
    try:
        json.dumps(cls.to_dict())
    except TypeError:
        failures.append("to_dict is not JSON-serializable")

    # Test 15: is_format flag forces FORMAT routing regardless of failure_type
    r_forced = route_failure("REASONING", is_format=True)
    if r_forced["evolution_axis"] != "architecture":
        failures.append("is_format=True should force architecture routing")

    total = 15
    print("=" * 70)
    print(f"evolution-taxonomy-classifier benchmark - {total - len(failures)}/{total} passed")
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

    p_axes = sub.add_parser("axes", help="Print the four axes and allowed values")
    p_axes.set_defaults(func=cmd_axes)

    p_cls = sub.add_parser("classify", help="Classify a proposed evolution")
    p_cls.add_argument("--what")
    p_cls.add_argument("--when")
    p_cls.add_argument("--how")
    p_cls.add_argument("--where")
    p_cls.add_argument("--notes")
    p_cls.add_argument("--path", help="proposal.json (free-form) for heuristic mapping")
    p_cls.set_defaults(func=cmd_classify)

    p_route = sub.add_parser("route", help="Table 7-1 failure-to-evolution routing")
    p_route.add_argument("--failure-type", required=True, dest="failure_type")
    p_route.add_argument("--recurring", action="store_true")
    p_route.add_argument("--format", action="store_true")
    p_route.set_defaults(func=cmd_route)

    p_scen = sub.add_parser("scenario", help="DevOps prompt-refinement scenario")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
