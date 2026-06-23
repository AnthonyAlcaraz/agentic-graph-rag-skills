#!/usr/bin/env python3
"""parallel-reconcile-merge CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    BranchResult,
    REDUCERS,
    reduce_field,
    execute_branches,
    reconcile,
    run_parallel_window,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "parallel-reconcile-merge (Ch5)"
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
    return " ".join(d for d in desc if d) or "parallel-reconcile-merge"


def _outcome_to_dict(o):
    return {
        "completed": o.completed,
        "mode": o.mode,
        "succeeded": o.succeeded,
        "failed": o.failed,
        "flags": o.flags,
        "merged_value": o.merged_value,
        "rationale": o.rationale,
    }


def cmd_scenario(args):
    if args.name != "parallel-hypotheses":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps parallel hypothesis tests (account 123456789012)")
    print("=" * 70)

    def db_pool(ctx):
        return {"utilization": 1.0, "waiting_threads": 47, "flags": ["pool_exhausted"]}

    def payment_mem(ctx):
        return {"heap_pct": 0.42, "flags": []}

    def network_partition(ctx):
        raise TimeoutError("probe to payment->db link timed out")

    branches = {
        "db_pool": db_pool,
        "payment_mem": payment_mem,
        "network_partition": network_partition,
    }

    print("\n--- partial_coverage (3 branches, 1 crashes) ---")
    out = run_parallel_window(branches, {"incident": "checkout-latency"}, mode="partial_coverage")
    print(json.dumps(_outcome_to_dict(out), indent=2))

    print("\n--- all_or_nothing confirmation phase (must have every branch) ---")
    out2 = run_parallel_window(
        {"db_pool": db_pool, "payment_mem": payment_mem},
        {"incident": "checkout-latency"}, mode="all_or_nothing",
    )
    print(json.dumps(_outcome_to_dict(out2), indent=2))


def cmd_benchmark(args):
    failures = []

    def ok_a(ctx): return {"v": 1, "flags": ["flag_a"]}
    def ok_b(ctx): return {"v": 2, "flags": []}
    def boom(ctx): raise ValueError("branch exploded")

    # Test 1: raising branch isolated, siblings still run
    results = execute_branches({"a": ok_a, "b": ok_b, "c": boom}, {})
    by_name = {r.name: r for r in results}
    if by_name["c"].ok or "branch exploded" not in by_name["c"].error:
        failures.append("crashing branch should be isolated with error recorded")
    if not (by_name["a"].ok and by_name["b"].ok):
        failures.append("sibling branches should still succeed when one crashes")

    # Test 2: all_or_nothing fails if any branch failed
    out = reconcile(results, mode="all_or_nothing")
    if out.completed:
        failures.append("all_or_nothing should NOT complete with a failed branch")

    # Test 3: all_or_nothing completes when all succeed
    out = reconcile(execute_branches({"a": ok_a, "b": ok_b}, {}), mode="all_or_nothing")
    if not out.completed:
        failures.append("all_or_nothing should complete when all branches succeed")

    # Test 4: partial_coverage completes at majority quorum (2 of 3 ok)
    out = reconcile(results, mode="partial_coverage")
    if not out.completed:
        failures.append("partial_coverage should complete with 2/3 succeeding (majority)")

    # Test 5: partial_coverage fails below quorum (1 of 3)
    res_one = execute_branches({"a": ok_a, "b": boom, "c": boom}, {})
    out = reconcile(res_one, mode="partial_coverage")
    if out.completed:
        failures.append("partial_coverage should fail with only 1/3 succeeding (below majority)")

    # Test 6: explicit min_success honored
    out = reconcile(res_one, mode="partial_coverage", min_success=1)
    if not out.completed:
        failures.append("partial_coverage with min_success=1 should complete on 1 success")

    # Test 7: flags unioned across branches (flag from a non-failing sibling kept)
    out = reconcile(results, mode="partial_coverage")
    if "flag_a" not in out.flags:
        failures.append(f"flags should be unioned, got {out.flags}")

    # Test 8: failed branch does not drop another branch's flag
    res2 = execute_branches({"flagger": ok_a, "crasher": boom}, {})
    out = reconcile(res2, mode="partial_coverage", min_success=1)
    if "flag_a" not in out.flags:
        failures.append("a failed sibling must not drop a surviving branch's flag")

    # Test 9: reducer merge is order-independent (commutative add)
    add = REDUCERS["add"]
    if reduce_field([1, 2, 3], add) != reduce_field([3, 1, 2], add):
        failures.append("commutative reducer should be order-independent")

    # Test 10: union reducer deduplicates and sorts
    if reduce_field([["x", "y"], ["y", "z"]], REDUCERS["union"]) != ["x", "y", "z"]:
        failures.append("union reducer should dedup+sort")

    # Test 11: succeeded/failed partition matches outcomes
    out = reconcile(results, mode="partial_coverage")
    if set(out.succeeded) != {"a", "b"} or out.failed != ["c"]:
        failures.append(f"partition wrong: succeeded={out.succeeded} failed={out.failed}")

    # Test 12: branches receive a copy; mutating context does not leak
    def mutator(ctx):
        ctx["leaked"] = True
        return {"v": 0, "flags": []}
    shared = {"incident": "x"}
    execute_branches({"m": mutator}, shared)
    if "leaked" in shared:
        failures.append("branch mutation leaked into shared context (isolation broken)")

    n = 12
    print("=" * 70)
    print(f"parallel-reconcile-merge benchmark - {n - len(failures)}/{n} passed")
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

    p_scen = sub.add_parser("scenario", help="DevOps parallel-hypotheses scenario")
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
