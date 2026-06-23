#!/usr/bin/env python3
"""homoiconic-meta-schema CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    validate_entity_type, validate_data_against_type, validate_rule,
    parse_action, evaluate_rule, METASCHEMA,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "homoiconic-meta-schema (Ch3)"
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
    return " ".join(d for d in desc if d) or "homoiconic-meta-schema"


def cmd_validate_type(args):
    with open(args.type_path) as f:
        definition = json.load(f)
    print(json.dumps(validate_entity_type(definition), indent=2))


def cmd_validate_data(args):
    with open(args.type_path) as f:
        entity_type = json.load(f)
    with open(args.instance_path) as f:
        instance = json.load(f)
    print(json.dumps(validate_data_against_type(entity_type, instance), indent=2))


def cmd_validate_rule(args):
    with open(args.rule_path) as f:
        rule = json.load(f)
    print(json.dumps(validate_rule(rule), indent=2))


def cmd_eval_rule(args):
    with open(args.rule_path) as f:
        rule = json.load(f)
    facts = json.loads(args.facts)
    print(json.dumps({"result": evaluate_rule(rule, facts)}, indent=2))


def cmd_scenario(args):
    if args.name != "customer-segment":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("Homoiconic KR: Person entity-type as data + DetermineCustomerSegment rule")
    print("=" * 70)

    print("\n[1] Person entity-type definition validated against the metaschema:")
    person = {
        "name": "Person", "description": "A human individual",
        "properties": [
            {"name": "name", "type": "string", "required": True},
            {"name": "birth_date", "type": "date"},
            {"name": "occupation", "type": "string"},
        ],
    }
    print(json.dumps(validate_entity_type(person), indent=2))

    print("\n[2] A data instance validated against the SAME Person type (homoiconic):")
    inst = {"name": "John Doe", "occupation": "Engineer"}
    print(json.dumps(validate_data_against_type(person, inst), indent=2))

    print("\n[3] Executable rule (Example 3-7) parsed + validated:")
    rule = {
        "name": "DetermineCustomerSegment",
        "description": "Assigns customer segment based on purchase history",
        "condition": "MATCH (c:Customer)-[:PURCHASED]->(p:Product) WITH c, COUNT(p) as purchase_count RETURN c, purchase_count",
        "action": ("WHEN purchase_count > 20 THEN SET c.segment = 'Premium' "
                   "WHEN purchase_count > 10 THEN SET c.segment = 'Regular' "
                   "ELSE SET c.segment = 'Basic'"),
    }
    print(json.dumps(validate_rule(rule), indent=2))

    print("\n[4] Evaluate the rule against purchase counts (tiered):")
    for n in (25, 15, 3):
        print(f"  purchase_count={n:3d} -> {evaluate_rule(rule, {'purchase_count': n})}")


def cmd_benchmark(args):
    failures = []

    person = {
        "name": "Person", "description": "A human individual",
        "properties": [
            {"name": "name", "type": "string", "required": True},
            {"name": "birth_date", "type": "date"},
            {"name": "occupation", "type": "string"},
        ],
    }

    # Test 1: valid Person type passes the metaschema.
    if not validate_entity_type(person)["valid"]:
        failures.append("valid Person entity-type should pass")

    # Test 2: type missing 'name' fails.
    if validate_entity_type({"properties": []})["valid"]:
        failures.append("type missing name should fail")

    # Test 3: type with duplicate property names fails.
    dup = {"name": "X", "properties": [
        {"name": "a", "type": "string"}, {"name": "a", "type": "int"}]}
    if validate_entity_type(dup)["valid"]:
        failures.append("duplicate property names should fail (Ch3: property names must be unique)")

    # Test 4: invalid property type fails.
    badtype = {"name": "X", "properties": [{"name": "a", "type": "frobnicate"}]}
    if validate_entity_type(badtype)["valid"]:
        failures.append("invalid property type should fail")

    # Test 5: data instance with required field present passes.
    if not validate_data_against_type(person, {"name": "John Doe"})["valid"]:
        failures.append("instance with required name should pass")

    # Test 6: data instance missing required field fails (homoiconic, same validator level).
    if validate_data_against_type(person, {"occupation": "Engineer"})["valid"]:
        failures.append("instance missing required 'name' should fail")

    # Test 7: data instance with wrong type fails.
    if validate_data_against_type(person, {"name": 12345})["valid"]:
        failures.append("name=int should fail type check")

    rule = {
        "name": "DetermineCustomerSegment",
        "condition": "MATCH ... RETURN c, purchase_count",
        "action": ("WHEN purchase_count > 20 THEN SET c.segment = 'Premium' "
                   "WHEN purchase_count > 10 THEN SET c.segment = 'Regular' "
                   "ELSE SET c.segment = 'Basic'"),
    }

    # Test 8: rule parses 2 WHEN clauses + 1 ELSE.
    parsed = parse_action(rule["action"])
    if len(parsed["when"]) != 2 or parsed["else"] is None:
        failures.append(f"rule should parse 2 WHEN + 1 ELSE, got {len(parsed['when'])} when, else={parsed['else']}")

    # Test 9: tiered evaluation: 25->Premium, 15->Regular, 3->Basic.
    if evaluate_rule(rule, {"purchase_count": 25}) != {"segment": "Premium"}:
        failures.append("25 purchases should be Premium")
    if evaluate_rule(rule, {"purchase_count": 15}) != {"segment": "Regular"}:
        failures.append("15 purchases should be Regular")
    if evaluate_rule(rule, {"purchase_count": 3}) != {"segment": "Basic"}:
        failures.append("3 purchases should be Basic")

    # Test 10: rule missing action fails validation.
    if validate_rule({"name": "R", "condition": "X"})["valid"]:
        failures.append("rule missing action should fail")

    total = 10
    print("=" * 70)
    print(f"homoiconic-meta-schema benchmark - {total - len(failures)}/{total} passed")
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

    p_vt = sub.add_parser("validate-type", help="Validate an entity-type definition vs the metaschema")
    p_vt.add_argument("--type-path", required=True)
    p_vt.set_defaults(func=cmd_validate_type)

    p_vd = sub.add_parser("validate-data", help="Validate a data instance vs its entity-type")
    p_vd.add_argument("--type-path", required=True)
    p_vd.add_argument("--instance-path", required=True)
    p_vd.set_defaults(func=cmd_validate_data)

    p_vr = sub.add_parser("validate-rule", help="Validate an executable-knowledge Rule")
    p_vr.add_argument("--rule-path", required=True)
    p_vr.set_defaults(func=cmd_validate_rule)

    p_er = sub.add_parser("eval-rule", help="Evaluate a Rule's tiered action against facts JSON")
    p_er.add_argument("--rule-path", required=True)
    p_er.add_argument("--facts", required=True, help='JSON dict, e.g. {"purchase_count": 25}')
    p_er.set_defaults(func=cmd_eval_rule)

    p_scen = sub.add_parser("scenario", help="Worked scenario (customer-segment)")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
