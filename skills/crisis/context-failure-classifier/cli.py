#!/usr/bin/env python3
"""context-failure-classifier CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import classify, classify_batch, ALL_MODES, FIVE_FATAL_FLAWS

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "context-failure-classifier (Ch1)"
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
    return " ".join(d for d in desc if d) or "context-failure-classifier"


def cmd_classify(args):
    print(json.dumps(classify(args.symptom), indent=2))


def cmd_batch(args):
    with open(args.symptoms_path) as f:
        symptoms = json.load(f)
    print(json.dumps(classify_batch(symptoms), indent=2))


def cmd_taxonomy(args):
    print("Ch1 context-failure taxonomy\n")
    print("Root-cause layer — the five fatal flaws:")
    for flaw, desc in FIVE_FATAL_FLAWS.items():
        print(f"  - {flaw:24s} {desc}")
    print("\nSymptom layer — classifiable failure modes:")
    for mode, spec in ALL_MODES.items():
        print(f"  - {mode:22s} root_flaw={spec['root_flaw']:24s} cure={spec['cure']}")


def cmd_scenario(args):
    if args.name != "outage-postmortem":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps post-mortem — classify each symptom (account 123456789012)")
    print("=" * 70)
    symptoms = [
        "The agent restarted checkout-service unaware it would cascade failures "
        "through dependent payment systems.",
        "Every investigation starts from scratch; it forgot last week's vendor problem.",
        "It recommended reverting to a configuration that no longer exists.",
        "It couldn't answer which services were affected by the database migration "
        "that followed the security patch, because that needs transitive reasoning.",
        "It called the wrong API, guessing which tool to use among too many tools.",
    ]
    out = classify_batch(symptoms)
    for r in out["results"]:
        if r["classified"]:
            p = r["primary"]
            print(f"\n[{p['failure_mode']}] root={p['root_flaw']} -> cure={p['cure']}")
            print(f"   symptom: {r['symptom']}")
            if r["cascade_modes"]:
                print(f"   cascade also touches: {', '.join(r['cascade_modes'])}")
        else:
            print(f"\n[unclassified] {r['symptom']}")
    print("\n--- Aggregate ---")
    print(json.dumps({
        "fatal_flaws_present": out["fatal_flaws_present"],
        "prioritized_cures": out["prioritized_cures"],
        "unclassified": out["unclassified"],
    }, indent=2))


def cmd_benchmark(args):
    failures = []

    # Test 1: action blindness — cascade/restart signal
    r = classify("It restarted the service and it cascaded failures through dependencies")
    if not r["classified"] or r["primary"]["failure_mode"] != "action_blindness":
        failures.append(f"cascade/restart should be action_blindness, got {r.get('primary')}")

    # Test 2: memory fragmentation — forgets / starts fresh
    r = classify("The agent forgot the prior conversation and starts from scratch each query")
    if r["primary"]["failure_mode"] != "memory_fragmentation":
        failures.append(f"forgot/fresh should be memory_fragmentation, got {r['primary']}")

    # Test 3: context drift — outdated / revert
    r = classify("It recommended reverting to an outdated config that no longer exists")
    if r["primary"]["failure_mode"] != "context_drift":
        failures.append(f"outdated/revert should be context_drift, got {r['primary']}")

    # Test 4: planning paralysis — transitive multi-doc synthesis
    r = classify("It can't synthesize across multiple documents to form a logical chain")
    if r["primary"]["failure_mode"] != "planning_paralysis":
        failures.append(f"synthesis/chain should be planning_paralysis, got {r['primary']}")

    # Test 5: tool chaos — wrong API
    r = classify("It guessed which API to call and called the wrong tool")
    if r["primary"]["failure_mode"] != "tool_chaos":
        failures.append(f"wrong-api should be tool_chaos, got {r['primary']}")

    # Test 6: each primary carries the correct root flaw + cure mapping
    r = classify("forgot everything, starts fresh")
    if r["primary"]["root_flaw"] != "context_amnesia" or r["primary"]["cure"] != "evolving_memory":
        failures.append(f"memory mode root/cure wrong: {r['primary']}")

    # Test 7: unmatched symptom is reported unclassified, not forced
    r = classify("The UI button was the wrong shade of blue")
    if r["classified"]:
        failures.append("irrelevant symptom should be unclassified")

    # Test 8: batch aggregates flaws and prioritizes cures
    out = classify_batch([
        "forgot the prior session, starts fresh",
        "amnesia: no memory of past interactions",
        "cascaded failures through dependencies on restart",
    ])
    if out["fatal_flaws_present"].get("context_amnesia") != 2:
        failures.append(f"batch should count 2 context_amnesia, got {out['fatal_flaws_present']}")
    if out["prioritized_cures"][0] != "evolving_memory":
        failures.append(f"top cure should be evolving_memory, got {out['prioritized_cures']}")

    # Test 9: cascade surfaces secondary modes when multiple match
    r = classify("It forgot prior state AND that caused cascading dependency failures")
    if not r["cascade_modes"]:
        failures.append("multi-signal symptom should expose cascade_modes")

    # Test 10: every taxonomy mode maps to a known fatal flaw
    for mode, spec in ALL_MODES.items():
        if spec["root_flaw"] not in FIVE_FATAL_FLAWS:
            failures.append(f"{mode} maps to unknown flaw {spec['root_flaw']}")

    print("=" * 70)
    print(f"context-failure-classifier benchmark - {10 - len(failures)}/10 passed")
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
    p_c = sub.add_parser("classify", help="Classify one symptom sentence")
    p_c.add_argument("--symptom", required=True)
    p_c.set_defaults(func=cmd_classify)
    p_b = sub.add_parser("batch", help="Classify a JSON list of symptoms")
    p_b.add_argument("--symptoms-path", required=True)
    p_b.set_defaults(func=cmd_batch)
    p_t = sub.add_parser("taxonomy", help="Print the Ch1 failure taxonomy")
    p_t.set_defaults(func=cmd_taxonomy)
    p_s = sub.add_parser("scenario", help="DevOps outage-postmortem worked example")
    p_s.add_argument("name")
    p_s.set_defaults(func=cmd_scenario)
    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
