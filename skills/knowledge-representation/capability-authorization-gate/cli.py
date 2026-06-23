#!/usr/bin/env python3
"""capability-authorization-gate CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import Agent, Capability, authorize, can_do, agent_from_spec, AUTH_ORDER

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "capability-authorization-gate (Ch3)"
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
    return " ".join(d for d in desc if d) or "capability-authorization-gate"


def cmd_authorize(args):
    with open(args.agent_path) as f:
        agent = agent_from_spec(json.load(f))
    print(json.dumps(authorize(agent, args.capability, amount=args.amount), indent=2))


def _support_agent() -> Agent:
    """Chapter's Customer-Support-Agent (Example 3-5)."""
    a = Agent(id="Customer-Support-Agent", granted_level="Public",
              granted_resources=["Product-Knowledge"])
    a.add_capability(Capability(type="Answer-Product-Question",
                                authorization_level="Public",
                                requires=["Product-Knowledge"]))
    a.add_capability(Capability(type="Process-Refund",
                                authorization_level="Supervisor",
                                requires=["Financial-System-Access"],
                                limit=500, limit_unit="USD"))
    return a


def cmd_scenario(args):
    if args.name == "support-refund":
        print("=" * 70)
        print("Customer-Support-Agent refund authority (Ch3 Example 3-5)")
        print("=" * 70)
        agent = _support_agent()
        print("\n[1] Answer a product question (Public, no limit):")
        print(json.dumps(authorize(agent, "Answer-Product-Question"), indent=2))
        print("\n[2] Process a $400 refund (within $500 limit, but Supervisor + Financial access needed):")
        print(json.dumps(authorize(agent, "Process-Refund", amount=400), indent=2))
        print("\n[3] Process a $600 refund (exceeds $500 limit -> escalate):")
        print(json.dumps(authorize(agent, "Process-Refund", amount=600), indent=2))
        print("\n[4] Attempt an undeclared capability -> deny:")
        print(json.dumps(authorize(agent, "Delete-Customer-Account"), indent=2))
        return

    if args.name == "devops-latency":
        print("=" * 70)
        print("DevOps latency investigation - AWS account 123456789012")
        print("=" * 70)
        spec_path = HERE / "sample_devops_agent.json"
        with open(spec_path) as f:
            agent = agent_from_spec(json.load(f))
        print("\n[1] read_metrics (Public, has cloudwatch:read) -> allow:")
        print(json.dumps(authorize(agent, "read_metrics"), indent=2))
        print("\n[2] query_logs (User, has logs:read) -> allow:")
        print(json.dumps(authorize(agent, "query_logs"), indent=2))
        print("\n[3] restart_instance (Supervisor + ec2:write) - agent is User w/o ec2:write -> escalate:")
        print(json.dumps(authorize(agent, "restart_instance"), indent=2))
        print("\n[4] scale_autoscaling_group by 25 instances (limit 10) -> escalate:")
        print(json.dumps(authorize(agent, "scale_autoscaling_group", amount=25), indent=2))
        return

    print(f"unknown scenario: {args.name}", file=sys.stderr)
    sys.exit(1)


def cmd_benchmark(args):
    failures = []
    agent = _support_agent()

    # Test 1: Public capability with resources present -> allow.
    if authorize(agent, "Answer-Product-Question")["decision"] != "allow":
        failures.append("Answer-Product-Question should be allowed (Public, has Product-Knowledge)")

    # Test 2: $600 refund exceeds $500 limit -> escalate (the canonical case).
    d = authorize(agent, "Process-Refund", amount=600)
    if d["decision"] != "escalate":
        failures.append(f"$600 refund should escalate, got {d['decision']}")
    if not any("exceeds limit" in r for r in d["reasons"]):
        failures.append("escalation reason should cite exceeding the limit")

    # Test 3: undeclared capability -> deny (not escalate).
    if authorize(agent, "Delete-Customer-Account")["decision"] != "deny":
        failures.append("undeclared capability should deny")

    # Test 4: $400 refund within limit but missing Supervisor + Financial access -> escalate.
    d = authorize(agent, "Process-Refund", amount=400)
    if d["decision"] != "escalate":
        failures.append("$400 refund should still escalate (auth level + resource gaps)")

    # Test 5: grant Supervisor + Financial access, then $400 -> allow.
    sup = _support_agent()
    sup.granted_level = "Supervisor"
    sup.granted_resources = ["Product-Knowledge", "Financial-System-Access"]
    if authorize(sup, "Process-Refund", amount=400)["decision"] != "allow":
        failures.append("Supervisor with Financial access should allow $400 refund")

    # Test 6: same supervisor, $600 still exceeds limit -> escalate.
    if authorize(sup, "Process-Refund", amount=600)["decision"] != "escalate":
        failures.append("even Supervisor should escalate $600 over the $500 limit")

    # Test 7: can_do convenience matches decision.
    if can_do(sup, "Process-Refund", amount=400) is not True:
        failures.append("can_do should be True for allowed action")
    if can_do(agent, "Process-Refund", amount=600) is not False:
        failures.append("can_do should be False for escalated action")

    # Test 8: unknown authorization level raises at construction.
    try:
        Capability(type="x", authorization_level="Wizard")
        failures.append("unknown auth level should raise")
    except ValueError:
        pass

    # Test 9: DevOps spec - User cannot restart_instance (Supervisor + ec2:write) -> escalate.
    spec_path = HERE / "sample_devops_agent.json"
    with open(spec_path) as f:
        dev = agent_from_spec(json.load(f))
    if authorize(dev, "restart_instance")["decision"] != "escalate":
        failures.append("User-level devops agent should escalate restart_instance")

    # Test 10: DevOps allowed read path + over-limit scale escalates.
    if authorize(dev, "read_metrics")["decision"] != "allow":
        failures.append("devops read_metrics should allow")
    if authorize(dev, "scale_autoscaling_group", amount=25)["decision"] != "escalate":
        failures.append("scaling 25 instances over a 10 limit should escalate")

    total = 10
    print("=" * 70)
    print(f"capability-authorization-gate benchmark - {total - len(failures)}/{total} passed")
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

    p_auth = sub.add_parser("authorize", help="Authorize a capability for an agent spec")
    p_auth.add_argument("--agent-path", required=True)
    p_auth.add_argument("--capability", required=True)
    p_auth.add_argument("--amount", type=float, default=None)
    p_auth.set_defaults(func=cmd_authorize)

    p_scen = sub.add_parser("scenario", help="Worked scenario (support-refund | devops-latency)")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
