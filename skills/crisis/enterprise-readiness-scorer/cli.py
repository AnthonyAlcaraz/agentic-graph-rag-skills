#!/usr/bin/env python3
"""enterprise-readiness-scorer CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    assess,
    score_flaws,
    score_capabilities,
    decision_trace_test,
    FIVE_FATAL_FLAWS,
    FLAW_CURE,
    AGENT_CAPABILITIES,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "enterprise-readiness-scorer (Ch1)"
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
    return " ".join(d for d in desc if d) or "enterprise-readiness-scorer"


def cmd_assess(args):
    with open(args.profile_path) as f:
        profile = json.load(f)
    print(json.dumps(assess(profile), indent=2))


def cmd_flaws(args):
    """Step 1: show which of the five fatal flaws are cured / open."""
    with open(args.profile_path) as f:
        profile = json.load(f)
    pts, cured, open_flaws = score_flaws(profile.get("graph_capabilities", {}))
    print(f"Five fatal flaws (Ch1) — {len(cured)}/5 cured, {pts:.1f} pts\n")
    for flaw in FIVE_FATAL_FLAWS:
        status = "CURED" if flaw in cured else "OPEN "
        print(f"  [{status}] {flaw:24s} cured-by: {FLAW_CURE[flaw]}")


def cmd_scenario(args):
    if args.name != "devops-agent":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps latency-investigation agent — readiness assessment")
    print("Fictional AWS account 123456789012")
    print("=" * 70)
    # A team has wired an LLM to a vector store only. Classic naive stack.
    naive = {
        "graph_capabilities": {
            "entity_relationships": False,
            "evolving_memory": False,
            "temporal_evolution": False,
            "multi_hop_reasoning": False,
            "tool_orchestration": False,
        },
        "agency": {"autonomy": 0.7, "action": 0.5},  # authority left uncalibrated
        "capabilities": {
            "autonomous_decision_making": True,
            "contextual_understanding": False,
            "strategic_tool_utilization": False,
            "memory_persistence": False,
        },
        "captures_rejected_alternatives": False,
    }
    print("\n--- Naive vector-only stack ---")
    print(json.dumps(assess(naive), indent=2))

    # After adding a graph + context-graph substrate.
    graph = {
        "graph_capabilities": {
            "entity_relationships": True,
            "evolving_memory": True,
            "temporal_evolution": True,
            "multi_hop_reasoning": True,
            "tool_orchestration": True,
        },
        "agency": {"autonomy": 0.7, "action": 0.6, "authority": 0.4},
        "capabilities": {k: True for k in AGENT_CAPABILITIES},
        "captures_rejected_alternatives": True,
    }
    print("\n--- Graph + context-graph stack ---")
    print(json.dumps(assess(graph), indent=2))


def cmd_benchmark(args):
    failures = []

    # Test 1: all flaws open => 0 flaw points, NAIVE-VECTOR band region
    res = assess({"graph_capabilities": {}})
    if res["breakdown"]["flaws_cured"] != 0.0:
        failures.append(f"all-open flaws should score 0, got {res['breakdown']['flaws_cured']}")
    if res["open_flaws"] != list(FLAW_CURE.keys()):
        failures.append("all five flaws should be open when no capabilities present")

    # Test 2: all flaws cured => full 40 points
    full_caps = {c: True for c in FLAW_CURE.values()}
    pts, cured, open_flaws = score_flaws(full_caps)
    if abs(pts - 40.0) > 1e-9 or len(cured) != 5 or open_flaws:
        failures.append(f"all-cured should be 40 pts / 5 cured, got {pts}/{len(cured)}")

    # Test 3: each flaw is cured by exactly its mapped capability (not another)
    one = {"entity_relationships": True}
    pts, cured, _ = score_flaws(one)
    if cured != ["relationship_blindness"]:
        failures.append(f"entity_relationships should cure only relationship_blindness, got {cured}")

    # Test 4: decision-trace test is binary and worth 15
    p_yes, _ = decision_trace_test(True)
    p_no, _ = decision_trace_test(False)
    if p_yes != 15 or p_no != 0:
        failures.append(f"decision trace should be 15/0, got {p_yes}/{p_no}")

    # Test 5: capability scoring is proportional
    pts, missing = score_capabilities({"memory_persistence": True})
    if abs(pts - 25 / 4) > 1e-9 or len(missing) != 3:
        failures.append(f"1/4 capabilities should be 6.25 pts, got {pts}")

    # Test 6: perfect profile scores 100 and is PRODUCTION-READY
    perfect = {
        "graph_capabilities": {c: True for c in FLAW_CURE.values()},
        "agency": {"autonomy": 1, "action": 1, "authority": 1},
        "capabilities": {c: True for c in AGENT_CAPABILITIES},
        "captures_rejected_alternatives": True,
    }
    res = assess(perfect)
    if res["score"] != 100.0:
        failures.append(f"perfect profile should be 100, got {res['score']}")
    if res["band"] != "PRODUCTION-READY":
        failures.append(f"perfect profile band should be PRODUCTION-READY, got {res['band']}")

    # Test 7: empty profile is NAIVE-VECTOR
    res = assess({})
    if res["band"] != "NAIVE-VECTOR":
        failures.append(f"empty profile should be NAIVE-VECTOR, got {res['band']}")

    # Test 8: open flaws produce a recommendation each
    res = assess({"graph_capabilities": {"evolving_memory": True}})
    rec_flaws = [r for r in res["recommendations"] if r.startswith("OPEN FLAW")]
    if len(rec_flaws) != 4:
        failures.append(f"expected 4 open-flaw recommendations, got {len(rec_flaws)}")

    # Test 9: agency scored by coverage not magnitude (calibration point)
    from lib import score_agency
    pts_lo, _ = score_agency({"autonomy": 0.1, "action": 0.1, "authority": 0.1})
    pts_hi, _ = score_agency({"autonomy": 0.9, "action": 0.9, "authority": 0.9})
    if pts_lo != pts_hi:
        failures.append("agency should score coverage (calibration), not magnitude")

    # Test 10: score is bounded 0..100 across random-ish inputs
    res = assess({
        "graph_capabilities": {"entity_relationships": True, "temporal_evolution": True},
        "agency": {"autonomy": 0.5},
        "capabilities": {"contextual_understanding": True},
        "captures_rejected_alternatives": True,
    })
    if not (0 <= res["score"] <= 100):
        failures.append(f"score out of bounds: {res['score']}")

    print("=" * 70)
    print(f"enterprise-readiness-scorer benchmark - {10 - len(failures)}/10 passed")
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
    p_assess = sub.add_parser("assess", help="Full readiness assessment from a profile JSON")
    p_assess.add_argument("--profile-path", required=True)
    p_assess.set_defaults(func=cmd_assess)
    p_flaws = sub.add_parser("flaws", help="Show five-fatal-flaws cure status")
    p_flaws.add_argument("--profile-path", required=True)
    p_flaws.set_defaults(func=cmd_flaws)
    p_scen = sub.add_parser("scenario", help="DevOps-agent worked example")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)
    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
