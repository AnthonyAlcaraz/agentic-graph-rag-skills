#!/usr/bin/env python3
"""subgraph-access-control CLI — RBAC policy, PII erasure, compliance audit.

Invocations:
    subgraph-access-control --help
    subgraph-access-control policy sre_oncall
    subgraph-access-control check sre_oncall Service cost_per_hour
    subgraph-access-control audit sre_oncall --labels Service,Library,Employee
    subgraph-access-control erase user-abc-123 --mode hard
    subgraph-access-control governance --role sre_on_call
    subgraph-access-control benchmark

Every Process step in SKILL.md maps to a subcommand.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lib  # noqa: E402

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "subgraph-access-control (Ch8 — Data Governance and Access Control)"
    text = SKILL_MD.read_text(encoding="utf-8")
    desc, in_desc, fm, in_fm = [], False, 0, False
    for line in text.splitlines():
        if line.strip() == "---":
            fm += 1
            in_fm = fm == 1
            if fm == 2:
                break
            continue
        if not in_fm:
            continue
        if line.startswith("description:"):
            in_desc = True
            continue
        if in_desc:
            if line and not line[0].isspace():
                in_desc = False
                continue
            desc.append(line.strip())
    return " ".join(d for d in desc if d) or "subgraph-access-control"


def cmd_policy(args):
    print(lib.generate_policy(args.role))


def cmd_check(args):
    print(json.dumps({
        "role": args.role,
        "label": args.label,
        "property": args.property,
        "can_traverse": lib.can_traverse(args.role, args.label),
        "can_read": lib.can_read(args.role, args.label, args.property) if args.property else None,
        "note": "can_traverse False => the node is INVISIBLE to the agent, not "
                "access-denied (security transparency).",
    }, indent=2))


def cmd_audit(args):
    labels = [l.strip() for l in args.labels.split(",") if l.strip()]
    needed_props = {}
    if args.props:
        # format: Service:cost_per_hour,budget_code
        label, _, plist = args.props.partition(":")
        needed_props[label] = [p.strip() for p in plist.split(",") if p.strip()]
    print(json.dumps(lib.audit_access(args.role, labels, needed_props), indent=2))


def cmd_erase(args):
    print(json.dumps(lib.gdpr_erase(args.uuid, args.mode), indent=2))


def cmd_governance(args):
    record = lib.governance_metadata(
        data_sources_accessed=["infrastructure_graph", "metrics_api"],
        access_role=args.role,
        model_id="llama-3.1-8b-instruct",
        model_version="v2.3.1",
        decision_confidence=0.87,
        pii_accessed=args.pii,
    )
    print(json.dumps(record, indent=2))


def cmd_benchmark(args):
    failures = []

    # 1: SRE cannot read cost; finance can.
    if lib.can_read("sre_oncall", "Service", "cost_per_hour"):
        failures.append("sre_oncall must NOT read cost_per_hour")
    if not lib.can_read("finance_analyst", "Service", "cost_per_hour"):
        failures.append("finance_analyst must read cost_per_hour")

    # 2: SRE can traverse Library; finance cannot (deployment details denied).
    if not lib.can_traverse("sre_oncall", "Library"):
        failures.append("sre_oncall must traverse Library")
    if lib.can_traverse("finance_analyst", "Library"):
        failures.append("finance_analyst must NOT traverse Library")

    # 3: Employee/Compensation invisible to every role.
    for role in lib.ROLES:
        if lib.can_traverse(role, "Employee"):
            failures.append(f"{role} must NOT traverse Employee")

    # 4: generated policy contains GRANT + DENY statements.
    pol = lib.generate_policy("sre_oncall")
    if "GRANT TRAVERSE" not in pol or "DENY READ" not in pol:
        failures.append("sre_oncall policy missing GRANT/DENY statements")

    # 5: audit flags the pitfall — an SRE query needing Library is complete;
    #    a query needing Employee is not.
    a1 = lib.audit_access("sre_oncall", ["Service", "Library"])
    if not a1["functionally_complete"]:
        failures.append("sre_oncall dependency query should be functionally complete")
    a2 = lib.audit_access("finance_analyst", ["Service", "Library"])
    if a2["functionally_complete"]:
        failures.append("finance_analyst cannot see Library; query is NOT complete")

    # 6: GDPR soft delete preserves aggregate analysis; hard delete detaches.
    soft = lib.gdpr_erase("u1", "soft")
    hard = lib.gdpr_erase("u1", "hard")
    if not soft["aggregate_analysis_preserved"]:
        failures.append("soft delete should preserve aggregate analysis")
    if "DETACH DELETE" not in hard["graph_action"]:
        failures.append("hard delete should DETACH DELETE the UUID node")

    # 7: governance record carries model id/version + pii flag (Example 8-6).
    rec = lib.governance_metadata(["infrastructure_graph"], "sre_on_call",
                                  "llama-3.1-8b-instruct", "v2.3.1", 0.87, pii_accessed=False)
    for k in ("model_id", "model_version", "pii_accessed", "access_role"):
        if k not in rec:
            failures.append(f"governance record missing {k}")

    # 8: audit_query filters compliance records by pii_accessed.
    records = [rec, lib.governance_metadata(["identity_store"], "billing", "m", "v", 0.9, pii_accessed=True)]
    pii_hits = lib.audit_query(records, pii_accessed=True)
    if len(pii_hits) != 1 or not pii_hits[0]["pii_accessed"]:
        failures.append("audit_query should return exactly the PII-accessing decision")

    total = 8
    print("=" * 70)
    print(f"subgraph-access-control benchmark — {total - len(failures)}/{total} passed")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All gates passed.")
    sys.exit(0)


def main():
    p = argparse.ArgumentParser(prog="subgraph-access-control", description=_skill_description())
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("policy", help="Emit Neo4j GRANT/DENY policy for a role")
    pp.add_argument("role", choices=sorted(lib.ROLES))
    pp.set_defaults(func=cmd_policy)

    pc = sub.add_parser("check", help="Check traverse/read permission (security transparency)")
    pc.add_argument("role", choices=sorted(lib.ROLES))
    pc.add_argument("label", choices=sorted(lib.NODE_LABELS))
    pc.add_argument("property", nargs="?", default=None)
    pc.set_defaults(func=cmd_check)

    pa = sub.add_parser("audit", help="Test a policy against an agent query pattern")
    pa.add_argument("role", choices=sorted(lib.ROLES))
    pa.add_argument("--labels", required=True, help="Comma-separated node labels the agent must traverse")
    pa.add_argument("--props", default=None, help="Label:prop1,prop2 the agent must read")
    pa.set_defaults(func=cmd_audit)

    pe = sub.add_parser("erase", help="GDPR Article 17 erasure (soft/hard)")
    pe.add_argument("uuid")
    pe.add_argument("--mode", choices=["soft", "hard"], default="soft")
    pe.set_defaults(func=cmd_erase)

    pg = sub.add_parser("governance", help="Build an execution-graph governance record")
    pg.add_argument("--role", default="sre_on_call")
    pg.add_argument("--pii", action="store_true")
    pg.set_defaults(func=cmd_governance)

    pb = sub.add_parser("benchmark", help="Verification gate battery")
    pb.set_defaults(func=cmd_benchmark)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
