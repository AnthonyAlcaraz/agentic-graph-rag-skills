#!/usr/bin/env python3
"""pipeline-architecture-selector CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    assess_task_complexity,
    estimate_uncertainty,
    analyze_and_route,
    route_with_constraints,
    route_query,
    SIMPLE_THRESHOLD,
    LOW_UNCERTAINTY,
    HIGH_UNCERTAINTY,
    TREE_MEMORY_THRESHOLD,
    ITERATION_TIME_MINIMUM,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "pipeline-architecture-selector (Ch5)"
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
    return " ".join(d for d in desc if d) or "pipeline-architecture-selector"


def cmd_assess(args):
    print(json.dumps({
        "query": args.query,
        "complexity": assess_task_complexity(args.query),
        "uncertainty": estimate_uncertainty(args.query),
    }, indent=2))


def cmd_route(args):
    decision = route_query(
        args.query,
        available_memory_mb=args.memory,
        remaining_budget_s=args.budget,
    )
    print(json.dumps(decision.__dict__, indent=2))


def cmd_scenario(args):
    if args.name != "latency-investigation":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps latency investigation routing (account 123456789012)")
    print("=" * 70)
    cases = [
        ("What is the checkout service error rate right now?", float("inf"), float("inf")),
        ("Why did checkout latency spike from 200ms to 2.5s? Investigate root cause across services.", float("inf"), float("inf")),
        ("Why did checkout latency spike? Investigate the database and payment dependencies.", 128, float("inf")),
        ("Refine the remediation plan and re-validate it against the runbook.", float("inf"), 5.0),
    ]
    for q, mem, budget in cases:
        d = route_query(q, available_memory_mb=mem, remaining_budget_s=budget)
        flag = "  DEGRADED" if d.degraded else ""
        print(f"\nquery: {q}")
        print(f"  complexity={d.complexity}  uncertainty={d.uncertainty}")
        print(f"  ideal={d.architecture}  final={d.final}{flag}")
        print(f"  reason: {d.reason}")


def cmd_benchmark(args):
    failures = []

    # Test 1: simple + certain -> sequential
    if analyze_and_route(0.1, 0.1) != "sequential":
        failures.append("simple+certain should route sequential")

    # Test 2: high uncertainty -> tree
    if analyze_and_route(0.5, 0.9) != "tree":
        failures.append("high-uncertainty should route tree")

    # Test 3: middle -> loop
    if analyze_and_route(0.6, 0.5) != "loop":
        failures.append("complex+moderate-uncertainty should route loop")

    # Test 4: complex but certain (above complexity threshold, low uncertainty)
    #   -> not sequential (complexity gate fails) -> loop
    if analyze_and_route(0.9, 0.1) != "loop":
        failures.append("complex+certain should route loop, not sequential")

    # Test 5: tree under memory floor degrades
    d = route_with_constraints(0.5, 0.9, available_memory_mb=TREE_MEMORY_THRESHOLD - 1)
    if d.architecture != "tree" or d.final != "sequential_fallback" or not d.degraded:
        failures.append(f"tree under memory floor should degrade: {d}")

    # Test 6: loop under time floor degrades
    d = route_with_constraints(0.6, 0.5, remaining_budget_s=ITERATION_TIME_MINIMUM - 1)
    if d.architecture != "loop" or d.final != "single_pass_best_effort" or not d.degraded:
        failures.append(f"loop under time floor should degrade: {d}")

    # Test 7: unconstrained leaves final == ideal, not degraded
    d = route_with_constraints(0.5, 0.9)
    if d.final != d.architecture or d.degraded:
        failures.append(f"unconstrained should not degrade: {d}")

    # Test 8: tree with ample memory does NOT degrade
    d = route_with_constraints(0.5, 0.9, available_memory_mb=TREE_MEMORY_THRESHOLD + 1)
    if d.degraded or d.final != "tree":
        failures.append(f"tree with enough memory should not degrade: {d}")

    # Test 9: estimators stay in [0,1]
    for q in ["x", "why did the multi-service latency spike across payments and database after the deploy"]:
        c = assess_task_complexity(q)
        u = estimate_uncertainty(q)
        if not (0.0 <= c <= 1.0 and 0.0 <= u <= 1.0):
            failures.append(f"estimator out of range for {q!r}: c={c} u={u}")

    # Test 10: investigation query scores higher uncertainty than a flat lookup
    u_invest = estimate_uncertainty("why did checkout latency spike, investigate root cause")
    u_lookup = estimate_uncertainty("show the checkout policy number")
    if u_invest <= u_lookup:
        failures.append(f"investigation should be more uncertain than lookup: {u_invest} vs {u_lookup}")

    # Test 11: end-to-end route_query produces a degraded decision with a reason
    d = route_query("why did latency spike, investigate across services", available_memory_mb=1)
    if not d.degraded or "->" not in d.reason:
        failures.append(f"route_query degradation reason malformed: {d}")

    n = 11
    print("=" * 70)
    print(f"pipeline-architecture-selector benchmark - {n - len(failures)}/{n} passed")
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
    sub = parser.add_subparsers(dest="cmd")

    p_assess = sub.add_parser("assess", help="Estimate complexity + uncertainty of a query")
    p_assess.add_argument("query")
    p_assess.set_defaults(func=cmd_assess)

    p_route = sub.add_parser("route", help="Route a query to a pipeline architecture")
    p_route.add_argument("query")
    p_route.add_argument("--memory", type=float, default=float("inf"), help="available memory MB")
    p_route.add_argument("--budget", type=float, default=float("inf"), help="remaining time budget seconds")
    p_route.set_defaults(func=cmd_route)

    p_scen = sub.add_parser("scenario", help="DevOps latency-investigation routing scenario")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    if not getattr(args, "cmd", None):
        print(_skill_description())
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
