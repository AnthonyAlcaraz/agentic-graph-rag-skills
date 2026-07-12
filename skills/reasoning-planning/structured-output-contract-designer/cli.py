#!/usr/bin/env python3
"""structured-output-contract-designer CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    NodeProfile, recommend_enforcement, schema_from_node_type,
    validate_against_contract, reliability_gain, node_types,
    LEVEL_STRENGTH,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "structured-output-contract-designer (Ch5)"
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
    return " ".join(d for d in desc if d) or "structured-output-contract-designer"


def _profile_from_args(args) -> NodeProfile:
    return NodeProfile(
        consumed_by=args.consumed_by,
        needs_valid_parse=not args.no_valid_parse,
        fixed_vocabulary=args.fixed_vocabulary,
        reliability_criticality=args.reliability,
        latency_budget=args.latency_budget,
    )


def _load_payload(spec: str):
    """Accept an inline JSON string or a path to a JSON file."""
    p = Path(spec)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return json.loads(spec)


def cmd_recommend(args):
    profile = _profile_from_args(args)
    print(json.dumps(recommend_enforcement(profile), indent=2))


def cmd_contract(args):
    print(json.dumps(schema_from_node_type(args.node_type), indent=2))


def cmd_validate(args):
    contract = schema_from_node_type(args.node_type)
    payload = _load_payload(args.payload)
    result = validate_against_contract(payload, contract)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 2)


def cmd_scenario(args):
    print("=" * 70)
    print("Hypothesis node -> next node hand-off (DevOps latency investigation)")
    print("=" * 70)
    # A hypothesis node emits to the next node that ranks/tests hypotheses.
    # That is a machine seam: at least JSON_SCHEMA.
    profile = NodeProfile(consumed_by="next_node", needs_valid_parse=True,
                          fixed_vocabulary=False, reliability_criticality=2,
                          latency_budget=2)
    print("\nEnforcement recommendation for the hypothesis-node seam:")
    print(json.dumps(recommend_enforcement(profile), indent=2))

    contract = schema_from_node_type("hypothesis")
    print("\nHypothesis contract:")
    print(json.dumps(contract, indent=2))

    good = {"id": "h1",
            "statement": "DB connection pool exhausted after config change",
            "confidence": 0.82,
            "evidence": ["pool_wait_ms spiked 09:12", "config diff at 09:10"]}
    bad = {"id": "h2", "statement": "missing evidence and confidence is a string",
           "confidence": "high"}
    print("\nValidate a well-formed hypothesis payload:")
    print(json.dumps(validate_against_contract(good, contract), indent=2))
    print("\nValidate a malformed hypothesis payload (free-text-style drift):")
    print(json.dumps(validate_against_contract(bad, contract), indent=2))

    print("\nReliability gain from constraining this seam (99.9% -> 100%):")
    print(json.dumps(reliability_gain(0.999, 1.0), indent=2))


def cmd_benchmark(args):
    failures = []

    def rec(**kw):
        return recommend_enforcement(NodeProfile(**kw))["recommended"]

    # 1: graph_write seam -> JSON_SCHEMA or stricter.
    r = rec(consumed_by="graph_write", fixed_vocabulary=False)
    if LEVEL_STRENGTH[r] < LEVEL_STRENGTH["JSON_SCHEMA"]:
        failures.append(f"graph_write should be JSON_SCHEMA or stricter, got {r}")

    # 2: next_node seam -> at least JSON_SCHEMA.
    r = rec(consumed_by="next_node", fixed_vocabulary=False)
    if LEVEL_STRENGTH[r] < LEVEL_STRENGTH["JSON_SCHEMA"]:
        failures.append(f"next_node should be JSON_SCHEMA or stricter, got {r}")

    # 3: tool_call seam -> at least JSON_SCHEMA.
    r = rec(consumed_by="tool_call", fixed_vocabulary=False)
    if LEVEL_STRENGTH[r] < LEVEL_STRENGTH["JSON_SCHEMA"]:
        failures.append(f"tool_call should be JSON_SCHEMA or stricter, got {r}")

    # 4: fixed vocabulary / node-type target -> GRAMMAR_CONSTRAINED.
    r = rec(consumed_by="graph_write", fixed_vocabulary=True)
    if r != "GRAMMAR_CONSTRAINED":
        failures.append(f"fixed_vocabulary should be GRAMMAR_CONSTRAINED, got {r}")

    # 5: FREE_TEXT only for a human terminal reader that is not critical.
    r = rec(consumed_by="human", needs_valid_parse=False,
            reliability_criticality=0)
    if r != "FREE_TEXT":
        failures.append(f"human non-critical terminal output should be FREE_TEXT, got {r}")

    # 6: a reliability-critical human seam is NOT free text.
    r = rec(consumed_by="human", needs_valid_parse=False,
            reliability_criticality=3)
    if r == "FREE_TEXT":
        failures.append("reliability-critical human output must not be FREE_TEXT")

    # 7: validate catches a missing required field.
    contract = schema_from_node_type("hypothesis")
    res = validate_against_contract(
        {"id": "h1", "statement": "s", "confidence": 0.5}, contract)
    if res["valid"] or not any("evidence" in v for v in res["violations"]):
        failures.append("validate should flag the missing 'evidence' field")

    # 8: validate catches a type mismatch.
    res = validate_against_contract(
        {"id": "h1", "statement": "s", "confidence": "high", "evidence": []},
        contract)
    if res["valid"] or not any("type mismatch" in v for v in res["violations"]):
        failures.append("validate should flag confidence type mismatch")

    # 9: validate catches a closed-vocabulary violation.
    remediation = schema_from_node_type("remediation")
    res = validate_against_contract(
        {"action": "rollback", "risk": "catastrophic", "rollback": "revert"},
        remediation)
    if res["valid"] or not any("vocabulary violation" in v for v in res["violations"]):
        failures.append("validate should flag the 'risk' vocabulary violation")

    # 10: a well-formed payload validates clean.
    res = validate_against_contract(
        {"id": "h1", "statement": "s", "confidence": 0.9,
         "evidence": ["e1"]}, contract)
    if not res["valid"]:
        failures.append(f"well-formed hypothesis should validate: {res['violations']}")

    # 11: reliability_gain reports the keystone delta correctly.
    gain = reliability_gain(0.999, 1.0)
    if gain["failures_eliminated_per_million"] != 1000 or gain["absolute_gain"] <= 0:
        failures.append("reliability_gain miscomputed the seam delta")

    total = 11
    print("=" * 70)
    print(f"structured-output-contract-designer benchmark - {total - len(failures)}/{total} passed")
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

    def add_profile_args(p):
        p.add_argument("--consumed-by", choices=list(CONSUMERS_CHOICES),
                       default="next_node")
        p.add_argument("--no-valid-parse", action="store_true",
                       help="consumer does NOT need a deterministic parse")
        p.add_argument("--fixed-vocabulary", action="store_true",
                       help="output must match a closed vocabulary / node-type")
        p.add_argument("--reliability", type=int, default=1,
                       help="0..3 cost of a malformed output")
        p.add_argument("--latency-budget", type=int, default=2,
                       help="0..3 slack for generation cost")

    p_rec = sub.add_parser("recommend", help="Recommend an enforcement level for a node seam")
    add_profile_args(p_rec)
    p_rec.set_defaults(func=cmd_recommend)

    p_con = sub.add_parser("contract", help="Print the contract for a node type")
    p_con.add_argument("node_type", choices=node_types())
    p_con.set_defaults(func=cmd_contract)

    p_val = sub.add_parser("validate", help="Validate a JSON payload against a node-type contract")
    p_val.add_argument("node_type", choices=node_types())
    p_val.add_argument("payload", help="inline JSON or a path to a JSON file")
    p_val.set_defaults(func=cmd_validate)

    p_scen = sub.add_parser("scenario", help="Worked hypothesis-node hand-off scenario")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


CONSUMERS_CHOICES = ("human", "next_node", "graph_write", "tool_call")


if __name__ == "__main__":
    main()
