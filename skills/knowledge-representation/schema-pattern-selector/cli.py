#!/usr/bin/env python3
"""schema-pattern-selector CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import select_patterns, recommend_pattern, validate_instance, PATTERNS

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "schema-pattern-selector (Ch3)"
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
    return " ".join(d for d in desc if d) or "schema-pattern-selector"


def cmd_select(args):
    print(json.dumps(recommend_pattern(args.description), indent=2))


def cmd_validate(args):
    with open(args.instance_path) as f:
        instance = json.load(f)
    print(json.dumps(validate_instance(args.pattern, instance), indent=2))


def cmd_scenario(args):
    if args.name != "devops-drift":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps: deployment events + config-drift across Terraform vs AWS")
    print("=" * 70)

    print("\n[1] Shape: 'a deployment event with timestamp affecting services':")
    print(json.dumps(recommend_pattern(
        "a deployment event with timestamp and git commit, affecting services, "
        "preceded by a prior deploy"), indent=2))

    print("\n[2] Shape: 'Terraform reports 2 ingress rules, AWS reports 3 — conflicting sources':")
    print(json.dumps(recommend_pattern(
        "conflicting configuration: Terraform state perspective disagrees with "
        "AWS api source, configuration drift, each according_to a source with confidence"),
        indent=2))

    print("\n[3] Validate a multi-perspective config-drift instance:")
    instance = {
        "relationships": {"according-to": ["terraform_state", "aws_api"]},
        "perspectives": [
            {"source": "terraform_state", "value": 2, "confidence": 1.0},
            {"source": "aws_api", "value": 3, "confidence": 1.0},
        ],
    }
    print(json.dumps(validate_instance("multi_perspective", instance), indent=2))

    print("\n[4] Validate a BROKEN deployment event (no temporal link):")
    broken = {"relationships": {"hasParticipant": ["payment-service"]}}
    print(json.dumps(validate_instance("event_centric", broken), indent=2))


def cmd_benchmark(args):
    failures = []

    # Test 1: temporal description -> event_centric.
    r = recommend_pattern("a meeting event before the project review with timestamps")
    if r["recommended"] != "event_centric":
        failures.append(f"temporal shape should select event_centric, got {r['recommended']}")

    # Test 2: scope/validity description -> contextual_boundary.
    r = recommend_pattern("knowledge valid_during a time_range and applies_to one team scope")
    if r["recommended"] != "contextual_boundary":
        failures.append(f"scope shape should select contextual_boundary, got {r['recommended']}")

    # Test 3: contradiction description -> multi_perspective.
    r = recommend_pattern("two departments disagree, conflicting forecast, each according_to a source with confidence")
    if r["recommended"] != "multi_perspective":
        failures.append(f"contradiction shape should select multi_perspective, got {r['recommended']}")

    # Test 4: authority description -> capability_model.
    r = recommend_pattern("agent authorization to process refunds with a limit, escalate above authority")
    if r["recommended"] != "capability_model":
        failures.append(f"authority shape should select capability_model, got {r['recommended']}")

    # Test 5: composition flagged when 2+ patterns hit.
    r = recommend_pattern("a deployment event with timestamp, and conflicting perspectives from two sources with confidence")
    if "compose" not in r:
        failures.append("event+perspective shape should flag composition")

    # Test 6: empty/irrelevant description -> no recommendation.
    r = recommend_pattern("the quick brown fox")
    if r["recommended"] is not None:
        failures.append("irrelevant description should recommend None")

    # Test 7: valid event-centric instance passes.
    inst = {"relationships": {"hasParticipant": ["Alice"], "hasStartTime": ["2023-04-01"]}}
    if not validate_instance("event_centric", inst)["valid"]:
        failures.append("valid event instance should pass")

    # Test 8: event without temporal link fails.
    inst = {"relationships": {"hasParticipant": ["Alice"]}}
    res = validate_instance("event_centric", inst)
    if res["valid"]:
        failures.append("event without temporal link should fail")

    # Test 9: multi-perspective with confidence out of range fails.
    inst = {"relationships": {"according-to": ["x"]},
            "perspectives": [{"source": "x", "confidence": 1.7}]}
    res = validate_instance("multi_perspective", inst)
    if res["valid"]:
        failures.append("confidence > 1 should fail validation")

    # Test 10: capability missing authorization-level fails; complete passes.
    bad = {"relationships": {"hasCapability": ["c"]}, "capabilities": [{"type": "Process-Refund"}]}
    if validate_instance("capability_model", bad)["valid"]:
        failures.append("capability missing authorization-level should fail")
    good = {"relationships": {"hasCapability": ["c"]},
            "capabilities": [{"type": "Process-Refund", "authorization-level": "Supervisor"}]}
    if not validate_instance("capability_model", good)["valid"]:
        failures.append("complete capability should pass")

    total = 10
    print("=" * 70)
    print(f"schema-pattern-selector benchmark - {total - len(failures)}/{total} passed")
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

    p_sel = sub.add_parser("select", help="Select pattern(s) from a knowledge-shape description")
    p_sel.add_argument("--description", required=True)
    p_sel.set_defaults(func=cmd_select)

    p_val = sub.add_parser("validate", help="Validate a pattern instance against its contract")
    p_val.add_argument("--pattern", required=True, choices=PATTERNS)
    p_val.add_argument("--instance-path", required=True)
    p_val.set_defaults(func=cmd_validate)

    p_scen = sub.add_parser("scenario", help="Worked scenario (devops-drift)")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
