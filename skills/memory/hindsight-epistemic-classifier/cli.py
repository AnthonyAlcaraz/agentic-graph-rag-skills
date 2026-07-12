#!/usr/bin/env python3
"""hindsight-epistemic-classifier CLI."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    classify, classify_batch, justify, network_audit,
    EpistemicFact,
    NETWORK_WORLD, NETWORK_EXPERIENCE, NETWORK_OPINION, NETWORK_OBSERVATION,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "hindsight-epistemic-classifier (Ch4)"
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
    return " ".join(d for d in desc if d) or "hindsight-epistemic-classifier"


def cmd_classify(args):
    md = json.loads(args.metadata) if args.metadata else None
    try:
        f = classify(args.text, metadata=md, confidence=args.confidence)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(f.to_dict(), indent=2))


def cmd_audit(args):
    with open(args.facts_path) as f:
        raw = json.load(f)
    facts = [classify(r["text"], metadata=r.get("metadata"), confidence=r.get("confidence")) for r in raw]
    print(json.dumps(network_audit(facts), indent=2))


def cmd_scenario(args):
    if args.name != "incident-postmortem":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    samples = [
        # World facts (objective)
        ("The checkout API returned 503 errors between 08:00 and 08:30 UTC.", None),
        ("The production AWS account is 123456789012.", {"external_ref": "iam-policy.json"}),
        ("Sarah Chen is the on-call lead this week.", None),
        # Experience facts (agent first-person)
        ("I called CloudWatch GetMetricData at 08:15.", {"action_type": "cloudwatch_call", "source": "agent",
                                                          "timestamp": datetime.now(timezone.utc).isoformat()}),
        ("I retrieved the deployment log for v3.5.0.", {"source": "agent",
                                                          "timestamp": datetime.now(timezone.utc).isoformat()}),
        # Opinion facts (hedged)
        ("I believe the root cause is the v3.5.0 deployment.", {"confidence": 0.7, "inferred_from": [
            "The checkout API returned 503 errors between 08:00 and 08:30 UTC.",
            "I retrieved the deployment log for v3.5.0.",
        ]}),
        ("The latency spike is likely correlated with payments-service backpressure.", {"confidence": 0.5}),
        # Observation facts (synthesized)
        ("In summary, the incident timeline is: deploy at 22:30, latency rising 07:45, 503s at 08:00, rollback 08:32.",
         {"derived_from": ["deploy-log", "cloudwatch-metrics", "rollback-log", "incident-channel"]}),
    ]
    facts = []
    for text, md in samples:
        facts.append(classify(text, metadata=md))
    print("=" * 70)
    print("DevOps Incident Postmortem — epistemic classification")
    print("=" * 70)
    for f in facts:
        print(f"\n[{f.network}] {f.text}")
        if f.confidence < 1.0:
            print(f"    confidence={f.confidence}")
        if f.inferred_from:
            print(f"    inferred_from: {f.inferred_from}")
        if f.derived_from:
            print(f"    derived_from: {f.derived_from}")
    print("\n" + "=" * 70)
    print("Audit:")
    print(json.dumps(network_audit(facts), indent=2))
    print("\nJustify the opinion: 'I believe the root cause is the v3.5.0 deployment.'")
    print(json.dumps(justify(facts, "I believe the root cause is the v3.5.0 deployment."), indent=2))


def cmd_benchmark(args):
    failures = []

    # Test 1: World — declarative third-person
    f = classify("The production region is us-east-1.")
    if f.network != NETWORK_WORLD:
        failures.append(f"declarative -> World failed: got {f.network}")

    # Test 2: Experience — first-person action
    f = classify("I called the deploy API at 22:30.", {"action_type": "deploy"})
    if f.network != NETWORK_EXPERIENCE:
        failures.append(f"first-person -> Experience failed: got {f.network}")

    # Test 3: Opinion — hedging language
    f = classify("I believe the root cause is X.")
    if f.network != NETWORK_OPINION:
        failures.append(f"hedging -> Opinion failed: got {f.network}")

    # Test 4: Opinion — low confidence
    f = classify("The cause was the deployment.", confidence=0.7)
    if f.network != NETWORK_OPINION:
        failures.append(f"low-confidence -> Opinion failed: got {f.network}")

    # Test 5: Observation — synthesis language + multi-source
    f = classify(
        "In summary the user prefers Python.",
        {"derived_from": ["prior-conv-1", "prior-conv-2", "prior-conv-3"]},
    )
    if f.network != NETWORK_OBSERVATION:
        failures.append(f"synthesis -> Observation failed: got {f.network}")

    # Test 6: classify_batch is deterministic
    inputs = [
        {"text": "The API returned 200."},
        {"text": "I called the API."},
        {"text": "I believe the API is healthy."},
        {"text": "Based on multiple checks, the service is operational.",
         "metadata": {"derived_from": ["check-1", "check-2", "check-3"]}},
    ]
    out1 = [f.network for f in classify_batch(inputs)]
    out2 = [f.network for f in classify_batch(inputs)]
    if out1 != out2:
        failures.append("classify_batch non-deterministic")
    if set(out1) != {NETWORK_WORLD, NETWORK_EXPERIENCE, NETWORK_OPINION, NETWORK_OBSERVATION}:
        failures.append(f"classify_batch should cover all 4 networks, got {set(out1)}")

    # Test 7: justify returns provenance chain for Opinion
    facts = classify_batch([
        {"text": "The API returned 503."},  # World
        {"text": "I retrieved the deployment log.", "metadata": {"action_type": "fetch"}},  # Experience
        {"text": "I believe the deploy caused it.",
         "metadata": {"inferred_from": ["The API returned 503.", "I retrieved the deployment log."]}},
    ])
    j = justify(facts, "I believe the deploy caused it.")
    if not j.get("provenance") or len(j["provenance"]) < 2:
        failures.append("justify should return >= 2 provenance entries for the opinion")

    # Test 8: network_audit flags Experience without timestamp
    no_ts_fact = classify("I called something.", metadata={"action_type": "call"})  # no timestamp
    audit = network_audit([no_ts_fact])
    if not any("no timestamp" in w for w in audit["warnings"]):
        failures.append("audit should warn on Experience without timestamp")

    # Test 9: network_audit flags orphan Opinion
    orphan = classify("I believe X.")
    audit = network_audit([orphan])
    if not any("inferred_from" in w for w in audit["warnings"]):
        failures.append("audit should warn on orphan Opinion (no inferred_from)")

    # Test 10: World fact with external_ref preserved
    f = classify("The deploy is v3.5.0.", {"external_ref": "github://release/v3.5.0"})
    if f.external_ref != "github://release/v3.5.0":
        failures.append(f"World external_ref not preserved: {f.external_ref}")

    print("=" * 70)
    print(f"hindsight-epistemic-classifier benchmark - {10 - len(failures)}/10 passed")
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
    p_cl = sub.add_parser("classify", help="Classify one fact")
    p_cl.add_argument("--text", required=True)
    p_cl.add_argument("--metadata", default=None, help="JSON metadata")
    p_cl.add_argument("--confidence", type=float, default=None)
    p_cl.set_defaults(func=cmd_classify)
    p_aud = sub.add_parser("audit", help="Audit a list of facts")
    p_aud.add_argument("--facts-path", required=True)
    p_aud.set_defaults(func=cmd_audit)
    p_scen = sub.add_parser("scenario", help="DevOps incident-postmortem scenario")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)
    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
