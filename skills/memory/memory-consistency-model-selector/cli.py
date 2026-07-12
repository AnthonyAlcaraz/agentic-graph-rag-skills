#!/usr/bin/env python3
"""memory-consistency-model-selector CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    Operation, score_models, recommend_model, detect_cache_divergence,
    MODEL_PROFILE, MODELS, REQS,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "memory-consistency-model-selector (Ch4)"
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
    return " ".join(d for d in desc if d) or "memory-consistency-model-selector"


def _op_from_args(args) -> Operation:
    try:
        return Operation(
            shared_authoritative_state=args.shared_authoritative_state,
            conflict_intolerance=args.conflict_intolerance,
            staleness_budget=args.staleness_budget,
            collaboration=args.collaboration,
            self_session_only=args.self_session_only,
        )
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)


def cmd_recommend(args):
    op = _op_from_args(args)
    print(json.dumps(recommend_model(op), indent=2))


def cmd_score(args):
    op = _op_from_args(args)
    out = {
        "scores": dict(score_models(op)),
        "profiles": MODEL_PROFILE,
    }
    print(json.dumps(out, indent=2))


def _default_cache_case():
    # A DevOps handoff (Ch4): the diagnostics agent commits a root cause, but
    # the remediation agent still holds a cache from before that write.
    writes = [
        {"key": "root_cause", "timestamp": 100, "value": "env_var_misconfig"},
        {"key": "root_cause", "timestamp": 140, "value": "env_var_misconfig_v2"},
        {"key": "budget_left", "timestamp": 120, "value": 500},
    ]
    snapshots = [
        {"agent": "remediation", "key": "root_cause", "cached_at": 110},
        {"agent": "communication", "key": "root_cause", "cached_at": 140},
        {"agent": "capacity", "key": "budget_left", "cached_at": 90},
    ]
    return writes, snapshots


def cmd_cache_check(args):
    if args.path:
        with open(args.path) as f:
            spec = json.load(f)
        writes = spec.get("writes", [])
        snapshots = spec.get("snapshots", [])
    else:
        writes, snapshots = _default_cache_case()
    warnings = detect_cache_divergence(writes, snapshots)
    out = {
        "divergences": warnings,
        "stale_agents": sorted({w["agent"] for w in warnings}),
        "clean": not warnings,
    }
    print(json.dumps(out, indent=2))


_SCENARIOS = {
    "shared-budget-lock": Operation(
        shared_authoritative_state=3, conflict_intolerance=3,
        staleness_budget=0, collaboration=1, self_session_only=0),
    "background-enrichment": Operation(
        shared_authoritative_state=0, conflict_intolerance=0,
        staleness_budget=3, collaboration=1, self_session_only=0),
    "collaborative-research": Operation(
        shared_authoritative_state=0, conflict_intolerance=0,
        staleness_budget=1, collaboration=3, self_session_only=1),
    "session-assistant": Operation(
        shared_authoritative_state=0, conflict_intolerance=0,
        staleness_budget=2, collaboration=0, self_session_only=3),
}


def cmd_scenario(args):
    op = _SCENARIOS.get(args.name)
    if op is None:
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        print(f"known: {', '.join(sorted(_SCENARIOS))}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print(f"Scenario: {args.name}")
    print("=" * 70)
    print(json.dumps(recommend_model(op), indent=2))


def cmd_benchmark(args):
    failures = []

    # Test 1: shared authoritative state dominates -> strong.
    if recommend_model(Operation(shared_authoritative_state=3))["recommended"] != "strong":
        failures.append("shared-authoritative-state should pick strong")

    # Test 2: high staleness budget dominates -> eventual (cheapest).
    if recommend_model(Operation(staleness_budget=3))["recommended"] != "eventual":
        failures.append("high staleness budget should pick eventual")

    # Test 3: collaboration dominates -> causal (the practical default).
    if recommend_model(Operation(collaboration=3))["recommended"] != "causal":
        failures.append("collaboration should pick causal")

    # Test 4: self-session-only dominates -> read_your_writes.
    if recommend_model(Operation(self_session_only=3))["recommended"] != "read_your_writes":
        failures.append("self-session-only should pick read_your_writes")

    # Test 5: conflict intolerance dominates -> strong (safety barrier).
    if recommend_model(Operation(conflict_intolerance=3))["recommended"] != "strong":
        failures.append("conflict-intolerance should pick strong")

    # Test 6: zero requirements -> all scores zero, no crash.
    scored = score_models(Operation())
    if any(s != 0 for _, s in scored):
        failures.append("zero requirements should score all models 0")

    # Test 7: every model scored, scores ordered descending.
    scored = score_models(Operation(shared_authoritative_state=1, collaboration=1,
                                     staleness_budget=1, self_session_only=1,
                                     conflict_intolerance=1))
    if len(scored) != len(MODELS):
        failures.append("all four models must be scored")
    if [s for _, s in scored] != sorted([s for _, s in scored], reverse=True):
        failures.append("scores must be sorted descending")

    # Test 8: cache-divergence flags a stale read (cached older than a
    # committed write it depends on).
    writes = [{"key": "root_cause", "timestamp": 100},
              {"key": "root_cause", "timestamp": 140}]
    snaps = [{"agent": "remediation", "key": "root_cause", "cached_at": 110}]
    warns = detect_cache_divergence(writes, snaps)
    if len(warns) != 1 or warns[0]["agent"] != "remediation":
        failures.append("cache-check should flag the one stale agent")
    elif warns[0]["staleness_gap"] != 30:
        failures.append(f"staleness_gap should be 30, got {warns[0]['staleness_gap']}")

    # Test 9: cache-divergence clean when the cache is current (>= latest write).
    snaps_ok = [{"agent": "communication", "key": "root_cause", "cached_at": 140}]
    if detect_cache_divergence(writes, snaps_ok):
        failures.append("current cache should produce no divergence warnings")

    # Test 10: escalate_to_strong fires when causal is chosen but the operation
    # touches shared authoritative state (Ch4: default causal, escalate the
    # irreversible decision points).
    rec = recommend_model(Operation(collaboration=3, shared_authoritative_state=1))
    if rec["recommended"] != "causal":
        failures.append("collaboration+low-authority should still default to causal")
    elif not rec["escalate_to_strong"]:
        failures.append("authoritative-state present should flag escalate_to_strong")

    # Test 11: requirement + model sets did not drift.
    if set(REQS) != {"shared_authoritative_state", "conflict_intolerance",
                     "staleness_budget", "collaboration", "self_session_only"}:
        failures.append("requirement axes drifted from the chapter set")
    if set(MODELS) != {"strong", "causal", "read_your_writes", "eventual"}:
        failures.append("model set drifted from the four consistency models")

    total = 11
    print("=" * 70)
    print(f"memory-consistency-model-selector benchmark - {total - len(failures)}/{total} passed")
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

    def add_op_args(p):
        p.add_argument("--shared-authoritative-state", type=int, default=0)
        p.add_argument("--conflict-intolerance", type=int, default=0)
        p.add_argument("--staleness-budget", type=int, default=0)
        p.add_argument("--collaboration", type=int, default=0)
        p.add_argument("--self-session-only", type=int, default=0)

    p_rec = sub.add_parser("recommend", help="Recommend a consistency model for one operation")
    add_op_args(p_rec)
    p_rec.set_defaults(func=cmd_recommend)

    p_score = sub.add_parser("score", help="Score all four models + print their profiles")
    add_op_args(p_score)
    p_score.set_defaults(func=cmd_score)

    p_cache = sub.add_parser("cache-check", help="Flag agents acting on stale shared cache")
    p_cache.add_argument("--path", default=None, help="JSON {writes:[...], snapshots:[...]}")
    p_cache.set_defaults(func=cmd_cache_check)

    p_scen = sub.add_parser("scenario", help="Worked scenario (shared-budget-lock, background-enrichment, ...)")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
