#!/usr/bin/env python3
"""constraint-guided-plan-validator CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    PlanStep,
    Constraint,
    CapabilityModel,
    extract_constraints,
    steps_from_dicts,
    filter_executable_steps,
    verify,
    THRESHOLD,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "constraint-guided-plan-validator (Ch5)"
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
    return " ".join(d for d in desc if d) or "constraint-guided-plan-validator"


def _result_to_dict(r):
    return {
        "score": r.score,
        "passed": r.passed,
        "violations": [v.__dict__ for v in r.violations],
        "feedback": r.feedback,
    }


def cmd_validate(args):
    spec = json.loads(Path(args.spec_path).read_text(encoding="utf-8"))
    plan = steps_from_dicts(spec["plan"])
    constraints = extract_constraints(spec.get("constraints", {}))
    cap = None
    if "capability" in spec:
        c = spec["capability"]
        cap = CapabilityModel(allowed_actions=set(c.get("allowed_actions", [])),
                              max_privilege=c.get("max_privilege", "read"))
    result = verify(plan, constraints, cap, threshold=args.threshold)
    print(json.dumps(_result_to_dict(result), indent=2))


def cmd_scenario(args):
    if args.name != "remediation-plan":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps remediation-plan validation (account 123456789012)")
    print("=" * 70)
    cap = CapabilityModel(
        allowed_actions={"query_metrics", "read_logs", "record_incident", "rollback_config"},
        max_privilege="read",
    )
    constraints = extract_constraints({
        "max_steps": 6,
        "deadline_days": 30,
        "required_actions": ["record_incident"],
        "forbidden_actions": ["drop_table"],
    })

    print("\n--- Plan A: conforming, read-only ---")
    plan_a = steps_from_dicts([
        {"action": "query_metrics", "privilege": "read"},
        {"action": "read_logs", "privilege": "read"},
        {"action": "record_incident", "privilege": "read"},
    ])
    print(json.dumps(_result_to_dict(verify(plan_a, constraints, cap)), indent=2))

    print("\n--- Plan B: proposes a write the agent is not authorized for ---")
    plan_b = steps_from_dicts([
        {"action": "query_metrics", "privilege": "read"},
        {"action": "modify_db", "privilege": "write", "params": {"eta_days": 45}},
    ])
    print(json.dumps(_result_to_dict(verify(plan_b, constraints, cap)), indent=2))


def cmd_benchmark(args):
    cap = CapabilityModel(allowed_actions={"query_metrics", "read_logs", "record_incident"},
                          max_privilege="read")
    failures = []

    # Test 1: conforming plan passes with score 1.0
    constraints = extract_constraints({"max_steps": 5, "required_actions": ["record_incident"]})
    plan = steps_from_dicts([
        {"action": "query_metrics"}, {"action": "read_logs"}, {"action": "record_incident"},
    ])
    r = verify(plan, constraints, cap)
    if not r.passed or r.score != 1.0:
        failures.append(f"conforming plan should pass with score 1.0, got {r.score}/{r.passed}")

    # Test 2: too many steps drops score / fails
    constraints = extract_constraints({"max_steps": 1})
    r = verify(steps_from_dicts([{"action": "query_metrics"}, {"action": "read_logs"}]), constraints, cap)
    if r.score >= THRESHOLD:
        failures.append(f"over-max-steps should drop below threshold, got {r.score}")

    # Test 3: missing required action flagged
    constraints = extract_constraints({"required_actions": ["record_incident"]})
    r = verify(steps_from_dicts([{"action": "query_metrics"}]), constraints, cap)
    if not any(v.constraint_kind == "required_action" for v in r.violations):
        failures.append("missing required action should be flagged")

    # Test 4: forbidden action is a hard violation
    constraints = extract_constraints({"forbidden_actions": ["drop_table"]})
    r = verify(steps_from_dicts([{"action": "query_metrics"}, {"action": "drop_table"}]),
               constraints, cap)
    if r.passed:
        failures.append("forbidden action should be a hard violation (passed=False)")

    # Test 5: write step under read-only capability is hard
    r = verify(steps_from_dicts([{"action": "query_metrics", "privilege": "write"}]), [], cap)
    if r.passed:
        failures.append("write under read-only should be hard violation")

    # Test 6: unknown action filtered by capability
    cv = filter_executable_steps(steps_from_dicts([{"action": "exfiltrate"}]), cap)
    if len(cv) != 1 or cv[0].constraint_kind != "capability":
        failures.append(f"unknown action should produce capability violation, got {cv}")

    # Test 7: deadline-exceeding step flagged per-step
    constraints = extract_constraints({"deadline_days": 30})
    r = verify(steps_from_dicts([{"action": "query_metrics", "params": {"eta_days": 45}}]),
               constraints, cap)
    if not any(v.constraint_kind == "deadline_days" and v.step_index == 0 for v in r.violations):
        failures.append("deadline-exceeding step should be flagged at its index")

    # Test 8: score stays in [0,1]
    constraints = extract_constraints({"max_steps": 0, "forbidden_actions": ["query_metrics"]})
    r = verify(steps_from_dicts([{"action": "query_metrics"}]), constraints, cap)
    if not (0.0 <= r.score <= 1.0):
        failures.append(f"score out of range: {r.score}")

    # Test 9: feedback enumerates violations
    if len(r.feedback) != len(r.violations):
        failures.append("feedback length should match violation count")

    # Test 10: capability.authorizes respects privilege ordering
    if cap.authorizes(PlanStep("query_metrics", "admin")):
        failures.append("admin step should not be authorized under read-only capability")
    if not cap.authorizes(PlanStep("query_metrics", "read")):
        failures.append("read step of allowed action should be authorized")

    # Test 11: no constraints + no capability -> trivially passes
    r = verify(steps_from_dicts([{"action": "anything"}]), [], None)
    if not r.passed or r.score != 1.0:
        failures.append(f"no-constraint plan should pass, got {r.score}/{r.passed}")

    n = 11
    print("=" * 70)
    print(f"constraint-guided-plan-validator benchmark - {n - len(failures)}/{n} passed")
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

    p_val = sub.add_parser("validate", help="Validate a plan spec JSON (plan + constraints + capability)")
    p_val.add_argument("--spec-path", required=True)
    p_val.add_argument("--threshold", type=float, default=THRESHOLD)
    p_val.set_defaults(func=cmd_validate)

    p_scen = sub.add_parser("scenario", help="DevOps remediation-plan validation scenario")
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
