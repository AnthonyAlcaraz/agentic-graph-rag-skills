#!/usr/bin/env python3
"""loop-pipeline-router CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    ValidationError,
    route_after_validation,
    run_loop,
    PROCEED,
    REFINE,
    FALLBACK,
    TERMINATE_PARTIAL,
    SEVERITY_CORRECTABLE,
    SEVERITY_FUNDAMENTAL,
    DEFAULT_MAX_RETRIES,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "loop-pipeline-router (Ch5)"
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
    return " ".join(d for d in desc if d) or "loop-pipeline-router"


def cmd_route(args):
    error = None
    if not args.valid:
        error = ValidationError(severity=args.severity, message=args.message or "")
    result = route_after_validation(args.valid, error, args.retry_count, args.max_retries)
    print(json.dumps(result.__dict__, indent=2))


def cmd_scenario(args):
    if args.name != "doc-gap-loop":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps/claims doc-gap refine loop (account 123456789012)")
    print("=" * 70)
    # Operative report missing anesthesia-time records on the first two passes;
    # the third request fills the gap.
    state = {"attempts": 0}

    def attempt_fn(retry_count):
        state["attempts"] += 1
        return {"doc_request": f"anesthesia-time records (attempt {state['attempts']})"}

    def validate_fn(candidate):
        # Valid only once two refine requests have been made (3rd attempt).
        if state["attempts"] >= 3:
            return True, None
        return False, ValidationError(SEVERITY_CORRECTABLE, "operative report incomplete: missing anesthesia time")

    result = run_loop(attempt_fn, validate_fn, max_retries=DEFAULT_MAX_RETRIES)
    print(json.dumps(result, indent=2))

    print("\n--- fundamental error: schema contradiction in plan ---")
    res2 = run_loop(
        lambda rc: {"plan": "sync AND event-driven for same op"},
        lambda c: (False, ValidationError(SEVERITY_FUNDAMENTAL, "plan contradicts itself")),
        max_retries=DEFAULT_MAX_RETRIES,
    )
    print(json.dumps(res2, indent=2))


def cmd_benchmark(args):
    failures = []

    # Test 1: valid -> proceed
    r = route_after_validation(True, None, 0)
    if r.decision != PROCEED:
        failures.append(f"valid should proceed, got {r.decision}")

    # Test 2: correctable + budget -> refine, increments retry_count
    r = route_after_validation(False, ValidationError(SEVERITY_CORRECTABLE, "x"), 0, 3)
    if r.decision != REFINE or r.retry_count != 1:
        failures.append(f"correctable+budget should refine with retry 1, got {r}")

    # Test 3: correctable + exhausted -> fallback
    r = route_after_validation(False, ValidationError(SEVERITY_CORRECTABLE, "x"), 3, 3)
    if r.decision != FALLBACK:
        failures.append(f"correctable+exhausted should fallback, got {r.decision}")

    # Test 4: fundamental -> terminate_with_partial
    r = route_after_validation(False, ValidationError(SEVERITY_FUNDAMENTAL, "x"), 0, 3)
    if r.decision != TERMINATE_PARTIAL:
        failures.append(f"fundamental should terminate_with_partial, got {r.decision}")

    # Test 5: invalid + no error -> terminate_with_partial
    r = route_after_validation(False, None, 0, 3)
    if r.decision != TERMINATE_PARTIAL:
        failures.append(f"invalid+no-error should terminate, got {r.decision}")

    # Test 6: refine increments up to the boundary then fallback at the edge
    r = route_after_validation(False, ValidationError(SEVERITY_CORRECTABLE), 2, 3)
    if r.decision != REFINE or r.retry_count != 3:
        failures.append(f"retry 2/3 should refine to 3, got {r}")

    # Test 7: run_loop terminates and never exceeds max_retries
    state = {"n": 0}
    def attempt(rc):
        state["n"] += 1
        return rc
    res = run_loop(attempt, lambda c: (False, ValidationError(SEVERITY_CORRECTABLE)), max_retries=3)
    if res["decision"] != FALLBACK:
        failures.append(f"always-correctable loop should fallback, got {res['decision']}")
    if res["iterations"] > 3:
        failures.append(f"iterations exceeded max_retries: {res['iterations']}")

    # Test 8: candidate that becomes valid after 2 refines -> proceed at iteration 2
    state2 = {"n": 0}
    def attempt2(rc):
        return rc
    def validate2(c):
        return (c >= 2, None if c >= 2 else ValidationError(SEVERITY_CORRECTABLE))
    res = run_loop(attempt2, validate2, max_retries=5)
    if res["decision"] != PROCEED or res["iterations"] != 2:
        failures.append(f"should proceed at iteration 2, got {res['decision']} / {res['iterations']}")

    # Test 9: fundamental loop terminates immediately with partial
    res = run_loop(lambda rc: rc, lambda c: (False, ValidationError(SEVERITY_FUNDAMENTAL)), max_retries=3)
    if res["decision"] != TERMINATE_PARTIAL or res["iterations"] != 0:
        failures.append(f"fundamental should terminate at iteration 0, got {res}")

    # Test 10: negative budget raises
    try:
        route_after_validation(False, ValidationError(SEVERITY_CORRECTABLE), 0, -1)
        failures.append("negative max_retries should raise")
    except ValueError:
        pass

    # Test 11: max_retries=0 -> correctable goes straight to fallback (no refine)
    r = route_after_validation(False, ValidationError(SEVERITY_CORRECTABLE), 0, 0)
    if r.decision != FALLBACK:
        failures.append(f"zero-budget correctable should fallback immediately, got {r.decision}")

    n = 11
    print("=" * 70)
    print(f"loop-pipeline-router benchmark - {n - len(failures)}/{n} passed")
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

    p_route = sub.add_parser("route", help="Route one validation result")
    p_route.add_argument("--valid", action="store_true", help="validation passed")
    p_route.add_argument("--severity", default=SEVERITY_CORRECTABLE,
                         choices=[SEVERITY_CORRECTABLE, SEVERITY_FUNDAMENTAL])
    p_route.add_argument("--message", default="")
    p_route.add_argument("--retry-count", dest="retry_count", type=int, default=0)
    p_route.add_argument("--max-retries", dest="max_retries", type=int, default=DEFAULT_MAX_RETRIES)
    p_route.set_defaults(func=cmd_route)

    p_scen = sub.add_parser("scenario", help="Doc-gap refine loop scenario")
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
