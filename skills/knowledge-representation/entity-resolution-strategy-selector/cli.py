#!/usr/bin/env python3
"""entity-resolution-strategy-selector CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    StrategyProfile, score_strategies, recommend_strategy,
    resolve_match, classify_edge, flag_edge_cases, FACTORS, STRATEGIES,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "entity-resolution-strategy-selector (Ch3)"
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
    return " ".join(d for d in desc if d) or "entity-resolution-strategy-selector"


def _profile_from_args(args) -> StrategyProfile:
    return StrategyProfile(
        high_stakes=args.high_stakes,
        adversarial=args.adversarial,
        needs_explainability=args.needs_explainability,
        needs_determinism=args.needs_determinism,
        cultural_variation=args.cultural_variation,
        has_training_examples=args.has_training_examples,
    )


# Default demo pair: two channel-separated aliases of one launderer.
_DEMO_A = {"name": "Robert Smith", "address": "123 Main Street", "phone": "555-0100"}
_DEMO_B = {"name": "Robert Smith Jr", "address": "123 Main St", "phone": "(555) 0100"}


def cmd_recommend(args):
    profile = _profile_from_args(args)
    print(json.dumps(recommend_strategy(profile), indent=2))


def cmd_resolve(args):
    rec_a = json.loads(args.record_a) if args.record_a else _DEMO_A
    rec_b = json.loads(args.record_b) if args.record_b else _DEMO_B
    match = resolve_match(rec_a, rec_b)
    out = {
        "record_a": rec_a,
        "record_b": rec_b,
        "match": match,
        "edge_cases": flag_edge_cases(rec_a, rec_b),
    }
    print(json.dumps(out, indent=2))


def cmd_classify_edge(args):
    print(json.dumps(classify_edge(args.confidence, declared=args.declared), indent=2))


def cmd_scenario(args):
    if args.name != "fraud-channel-separation":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("Fraud channel separation - one launderer, three engineered aliases")
    print("=" * 70)
    print("Adversarial identity work: variations are deliberately designed to")
    print("pass simple fuzzy filters while appearing distinct. Pick the strategy")
    print("first, then consolidate the channel with explainable evidence.\n")

    profile = StrategyProfile(high_stakes=3, adversarial=3, needs_explainability=3,
                              needs_determinism=3, cultural_variation=2)
    print("Strategy recommendation:")
    print(json.dumps(recommend_strategy(profile), indent=2))

    aliases = [
        {"name": "Bob Jones", "address": "123 Main Street", "phone": "555-010-2020"},
        {"name": "Bob R. Smith II", "address": "123 Main St", "phone": "(555) 0102020"},
        {"name": "Robert Smith Jr", "address": "45 Oak Avenue", "phone": "555-010-2020"},
    ]
    print("\nPairwise evidence-based resolution across the aliases:")
    for i in range(len(aliases)):
        for j in range(i + 1, len(aliases)):
            match = resolve_match(aliases[i], aliases[j])
            print(f"\n  {aliases[i]['name']}  <->  {aliases[j]['name']}")
            print(f"    confidence={match['confidence']}  edge={match['edge_type']}")
            for e in match["evidence"]:
                print(f"    - {e['feature']}: {e['score']}")
            for w in flag_edge_cases(aliases[i], aliases[j]):
                print(f"    ! {w['case']} -> {w['action']}")


def cmd_benchmark(args):
    failures = []

    # Test 1: adversarial + high-stakes fraud profile picks evidence_based.
    fraud = StrategyProfile(high_stakes=3, adversarial=3, needs_explainability=3,
                            needs_determinism=3, cultural_variation=2)
    if recommend_strategy(fraud)["recommended"] != "evidence_based":
        failures.append("adversarial high-stakes should pick evidence_based")

    # Test 2: low-stakes fuzzy dedup with abundant examples picks generalization.
    dedup = StrategyProfile(has_training_examples=3)
    if recommend_strategy(dedup)["recommended"] != "generalization_ai":
        failures.append("low-stakes example-rich dedup should pick generalization_ai")

    # Test 3: mixed profile flags a hybrid.
    mixed = StrategyProfile(high_stakes=3, has_training_examples=3)
    rec = recommend_strategy(mixed)
    if rec["recommended"] != "hybrid" or not rec["hybrid_recommended"]:
        failures.append("mixed high-stakes + examples should recommend hybrid")

    # Test 4: identical records resolve at full confidence -> RESOLVED.
    rec_a = {"name": "Acme Corp", "address": "1 Way", "phone": "555-1234"}
    match = resolve_match(rec_a, dict(rec_a))
    if match["confidence"] < 0.999 or match["edge_type"] != "RESOLVED":
        failures.append(f"identical records should be RESOLVED at 1.0, got {match}")

    # Test 5: evidence metadata is present and explainable (per-feature scores).
    a = {"name": "Robert Smith", "address": "123 Main St", "phone": "555-0100"}
    b = {"name": "Robert Smith Jr", "address": "123 Main St", "phone": "(555) 0100"}
    match = resolve_match(a, b)
    if len(match["evidence"]) != 3 or set(match["features_used"]) != {"name", "address", "phone"}:
        failures.append("resolve_match must emit per-feature evidence for all 3 features")
    if not all("score" in e and "contribution" in e for e in match["evidence"]):
        failures.append("evidence entries must carry per-feature score + contribution")

    # Test 6: aggregate equals the weighted sum of feature contributions.
    agg = round(sum(e["contribution"] for e in match["evidence"]), 4)
    if abs(agg - match["confidence"]) > 0.001:
        failures.append(f"confidence must equal summed contributions ({agg} vs {match['confidence']})")

    # Test 7: edge-type thresholds + DISCLOSED override.
    if classify_edge(0.9)["edge_type"] != "RESOLVED":
        failures.append("0.90 should classify as RESOLVED")
    if classify_edge(0.6)["edge_type"] != "POSSIBLY_RELATED":
        failures.append("0.60 should classify as POSSIBLY_RELATED")
    if classify_edge(0.2)["edge_type"] != "NO_MATCH":
        failures.append("0.20 should classify as NO_MATCH")
    if classify_edge(0.1, declared=True)["edge_type"] != "DISCLOSED":
        failures.append("declared=True should always classify as DISCLOSED")

    # Test 8: edge case (a) different strings, same entity (Arabic honorifics).
    ec = flag_edge_cases({"name": "al-Hajj Abdullah Qardash"},
                         {"name": "Abu Abdullah Qardash bin Amir"})
    if not any(w["case"] == "different_strings_same_entity" for w in ec):
        failures.append("should flag different_strings_same_entity for honorific names")

    # Test 9: edge case (b) near-identical strings, different entity (do-not-merge).
    ec = flag_edge_cases({"name": "John R Smith"}, {"name": "John E Smith"})
    hit = [w for w in ec if w["case"] == "near_identical_different_entity"]
    if not hit or hit[0]["action"] != "do_not_merge_without_evidence":
        failures.append("should flag near_identical_different_entity as do-not-merge")

    # Test 10: edge case (c) different address strings, same location.
    ec = flag_edge_cases(
        {"address": "#03-28, 400 Orchard Road, 238875 SNG"},
        {"address": "400 Orchard Tower #03-28 Orchard Rd, Singapore 238875 Singapore"},
    )
    if not any(w["case"] == "different_address_same_location" for w in ec):
        failures.append("should flag different_address_same_location for Orchard Rd pair")

    total = 10
    print("=" * 70)
    print(f"entity-resolution-strategy-selector benchmark - {total - len(failures)}/{total} passed")
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
        p.add_argument("--high-stakes", type=int, default=0)
        p.add_argument("--adversarial", type=int, default=0)
        p.add_argument("--needs-explainability", type=int, default=0)
        p.add_argument("--needs-determinism", type=int, default=0)
        p.add_argument("--cultural-variation", type=int, default=0)
        p.add_argument("--has-training-examples", type=int, default=0)

    p_rec = sub.add_parser("recommend", help="Recommend a resolution strategy from a profile")
    add_profile_args(p_rec)
    p_rec.set_defaults(func=cmd_recommend)

    p_res = sub.add_parser("resolve", help="Feature-score two records into an explainable match")
    p_res.add_argument("--record-a", default=None, help='JSON {name, address, phone}')
    p_res.add_argument("--record-b", default=None, help='JSON {name, address, phone}')
    p_res.set_defaults(func=cmd_resolve)

    p_cls = sub.add_parser("classify-edge", help="Classify a match confidence into an edge type")
    p_cls.add_argument("--confidence", type=float, required=True)
    p_cls.add_argument("--declared", action="store_true", help="Relationship declared in source data -> DISCLOSED")
    p_cls.set_defaults(func=cmd_classify_edge)

    p_scen = sub.add_parser("scenario", help="Worked scenario (fraud-channel-separation)")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
