#!/usr/bin/env python3
"""knowledge-organization-classifier CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    migration_cost,
    classify, validate_ontology_components, recommend_upgrade,
    SPECTRUM, ONTOLOGY_COMPONENTS,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "knowledge-organization-classifier (Ch3)"
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
    return " ".join(d for d in desc if d) or "knowledge-organization-classifier"


def cmd_classify(args):
    with open(args.spec_path) as f:
        spec = json.load(f)
    out = classify(spec)
    out["upgrade"] = recommend_upgrade(spec)
    print(json.dumps(out, indent=2))


def cmd_validate_ontology(args):
    with open(args.ontology_path) as f:
        ontology = json.load(f)
    print(json.dumps(validate_ontology_components(ontology), indent=2))


def cmd_scenario(args):
    if args.name != "healthcare-ontology":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("Knowledge organization spectrum + healthcare ontology validation")
    print("=" * 70)

    print("\n[1] Currency codes (controlled values, no hierarchy):")
    print(json.dumps(classify({"values": ["USD", "EUR", "GBP"]}), indent=2))

    print("\n[2] Transportation taxonomy (hierarchy):")
    print(json.dumps(classify({"has_hierarchy": True,
                               "values": ["Bike", "Bus", "Car", "Truck"]}), indent=2))

    print("\n[3] Healthcare ontology (5 core components, Ch3 example):")
    ontology = {
        "classes": [{"name": "Person"}, {"name": "Disease"}, {"name": "Test"},
                    {"name": "Hospital"}],
        "subclasses": [{"name": "Patient", "parent": "Person"},
                       {"name": "Oncologist", "parent": "Person"},
                       {"name": "Glioblastoma", "parent": "Disease"}],
        "individuals": [{"name": "John Doe", "type": "Patient"}],
        "axioms": ["Cancer is a subclass of Disease",
                   "A patient can have at most one primary physician"],
        "relationships": [
            {"name": "personUtilizesFacility", "from": "Person", "to": "Hospital"},
            {"name": "diseaseHasSymptom", "from": "Disease", "to": "Person"},
        ],
    }
    print(json.dumps(validate_ontology_components(ontology), indent=2))

    print("\n[4] BROKEN ontology (subclass references unknown parent, missing axioms):")
    broken = {
        "classes": [{"name": "Person"}],
        "subclasses": [{"name": "Patient", "parent": "Animal"}],
        "individuals": [{"name": "x"}],
        "relationships": [{"name": "r", "from": "Person", "to": "Ghost"}],
    }
    print(json.dumps(validate_ontology_components(broken), indent=2))


def cmd_benchmark(args):
    failures = []

    # Test 1: controlled values, no hierarchy -> pick_list.
    if classify({"values": ["USD", "EUR"]})["classification"] != "pick_list":
        failures.append("currency codes should classify as pick_list")

    # Test 2: hierarchy -> taxonomy.
    if classify({"has_hierarchy": True})["classification"] != "taxonomy":
        failures.append("hierarchy should classify as taxonomy")

    # Test 3: hierarchy + synonyms + associative -> thesaurus.
    r = classify({"has_hierarchy": True, "has_synonyms": True, "has_associative": True})
    if r["classification"] != "thesaurus":
        failures.append(f"hierarchy+synonyms+associative should be thesaurus, got {r['classification']}")

    # Test 4: classes + properties + inference -> ontology.
    r = classify({"has_classes": True, "has_properties": True, "has_inference": True})
    if r["classification"] != "ontology":
        failures.append(f"classes+properties+inference should be ontology, got {r['classification']}")

    # Test 5: partial ontology (classes only) does NOT over-claim.
    r = classify({"has_classes": True})
    if r["classification"] == "ontology":
        failures.append("classes-only should NOT classify as ontology (over-claim)")

    # Test 6: spectrum index ordering monotonic.
    idx_pl = classify({"values": []})["spectrum_index"]
    idx_tax = classify({"has_hierarchy": True})["spectrum_index"]
    idx_ont = classify({"has_classes": True, "has_properties": True, "has_inference": True})["spectrum_index"]
    if not (idx_pl < idx_tax < idx_ont):
        failures.append(f"spectrum index ordering wrong: {idx_pl},{idx_tax},{idx_ont}")

    # Test 7: complete healthcare ontology validates.
    ontology = {
        "classes": [{"name": "Person"}, {"name": "Disease"}, {"name": "Hospital"}],
        "subclasses": [{"name": "Patient", "parent": "Person"}],
        "individuals": [{"name": "John Doe"}],
        "axioms": ["Cancer subclassOf Disease"],
        "relationships": [{"name": "uses", "from": "Person", "to": "Hospital"}],
    }
    if not validate_ontology_components(ontology)["valid"]:
        failures.append("complete 5-component ontology should validate")

    # Test 8: missing a core component fails.
    no_axioms = dict(ontology)
    no_axioms = {k: v for k, v in ontology.items() if k != "axioms"}
    res = validate_ontology_components(no_axioms)
    if res["valid"] or "axioms" not in res["missing"]:
        failures.append("ontology missing axioms should be invalid with axioms in missing")

    # Test 9: subclass referencing unknown parent fails.
    bad = {
        "classes": [{"name": "Person"}],
        "subclasses": [{"name": "Patient", "parent": "Animal"}],
        "individuals": [{"name": "x"}], "axioms": ["a"],
        "relationships": [{"name": "r", "from": "Person", "to": "Person"}],
    }
    res = validate_ontology_components(bad)
    if res["valid"] or not any("unknown parent" in e for e in res["errors"]):
        failures.append("subclass with unknown parent should error")

    # Test 10: upgrade recommendation chains pick_list -> taxonomy.
    up = recommend_upgrade({"values": ["a", "b"]})
    if up["current"] != "pick_list" or up["next"] != "taxonomy":
        failures.append(f"pick_list upgrade should target taxonomy, got {up}")

    # Tests 11-14: migration-cost mechanism (Ch3 flexibility argument).
    r = migration_cost("ontology", "new_relationship_type")
    if r["cost"] != "LOCAL_ADD":
        failures.append("ontology must absorb a new relationship type as LOCAL_ADD")
    r = migration_cost("pick_list", "new_relationship_type")
    if r["cost"] != "NOT_EXPRESSIBLE" or r["upgrade_to"] != "ontology":
        failures.append("pick_list cannot express a relationship type; upgrade path must be ontology")
    r = migration_cost("taxonomy", "new_instance_cross_cutting")
    if r["cost"] != "SUBTREE_REORG":
        failures.append("cross-cutting instance in a taxonomy must cost SUBTREE_REORG")
    try:
        migration_cost("taxonomy", "cosmic_event")
        failures.append("unknown change event must raise ValueError")
    except ValueError:
        pass

    total = 14
    print("=" * 70)
    print(f"knowledge-organization-classifier benchmark - {total - len(failures)}/{total} passed")
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

    p_cls = sub.add_parser("classify", help="Classify a vocabulary spec onto the spectrum")
    p_cls.add_argument("--spec-path", required=True)
    p_cls.set_defaults(func=cmd_classify)

    p_val = sub.add_parser("validate-ontology", help="Validate the 5 ontology core components")
    p_val.add_argument("--ontology-path", required=True)
    p_val.set_defaults(func=cmd_validate_ontology)

    p_mig = sub.add_parser("migration-cost", help="Cost of absorbing a change at a spectrum level (Ch3 flexibility argument)")
    p_mig.add_argument("--level", required=True)
    p_mig.add_argument("--change", required=True)
    p_mig.set_defaults(func=lambda a: print(json.dumps(migration_cost(a.level, a.change), indent=2)))

    p_scen = sub.add_parser("scenario", help="Worked scenario (healthcare-ontology)")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
