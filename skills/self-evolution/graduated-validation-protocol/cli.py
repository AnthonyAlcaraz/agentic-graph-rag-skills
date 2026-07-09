#!/usr/bin/env python3
"""graduated-validation-protocol CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    TIERS,
    GateResult,
    Learning,
    airlock_gate,
    assign_tier,
    canary_gate,
    garbage_collect,
    graduated_validation,
    promotion_health,
    promotion_rate,
    provenance_signature,
    staging_gate,
    staging_utility,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "graduated-validation-protocol primitive (Ch7)"
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
    return " ".join(d for d in desc if d) or "graduated-validation-protocol (Ch7)"


def _load(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cmd_assign(args):
    candidate = _load(args.path)
    tier = assign_tier(candidate)
    print(json.dumps({
        "tier": tier,
        "signature": provenance_signature(candidate),
    }, indent=2))


def cmd_validate(args):
    candidate = _load(args.path)
    result = graduated_validation(candidate)
    out = result.to_dict()
    out["signature"] = provenance_signature(candidate)
    print(json.dumps(out, indent=2))
    sys.exit(0 if result.passed else 2)


def cmd_gc(args):
    raw = _load(args.path)
    learnings = [Learning.from_dict(d) for d in raw]
    kept, removed = garbage_collect(learnings, ttl_days=args.ttl_days)
    total = len(learnings)
    promoted = sum(1 for lrn in learnings if lrn.resolved_promoted)
    rate = promotion_rate(total, promoted)
    print(json.dumps({
        "ttl_days": args.ttl_days,
        "total": total,
        "kept": [lrn.id for lrn in kept],
        "removed": [lrn.id for lrn in removed],
        "promoted": promoted,
        "promotion_rate": rate,
        "promotion_health": promotion_health(rate),
    }, indent=2))


def cmd_scenario(args):
    if args.name != "prompt-canary":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps agent - Tier 1 canary for a prompt refinement (account 123456789012)")
    print("=" * 70)
    # The diagnostic loop refined the prompt of the CausalAttributionNode after a
    # cascade: a stripe-python 3.2.1 -> 3.3.0 bump changed a default request
    # timeout 30s -> 10s, cascading checkout-service -> order-service ->
    # fulfillment-service. The refinement is a minor prompt update: Tier 1.
    candidate = {
        "id": "cand-causal-attr-prompt-v7",
        "intervention_type": "prompt_refinement",
        "novel": False,
        "touches_safety": False,
        "new_tool": False,
        "target_node": "CausalAttributionNode",
        "note": "sharpen root-cause attribution for library-version-mismatch cascades",
        "metrics": {
            "target_lift": 0.041,        # +4.1% root-cause attribution accuracy
            "target_pvalue": 0.004,      # significant at alpha=0.05
            # normalized deltas: positive is improvement, negative is degradation
            "kpi_deltas": {
                "task_success_rate": 0.006,  # slight improvement
                "cost_usd": 0.0,             # unchanged
                "safety_score": 0.0,         # unchanged
            },
        },
    }

    tier = assign_tier(candidate)
    print(f"assigned tier: {tier}")
    print(f"provenance signature: {provenance_signature(candidate)}")

    result = graduated_validation(candidate)
    print("\ncanary gate:")
    print(json.dumps(result.to_dict(), indent=2))

    # Passing canary -> the resolution pattern is promoted from a Learning node
    # to curated Knowledge; the garbage collector then reclaims it from the
    # ephemeral Learnings subgraph.
    learnings = [
        Learning(
            id="learn-stripe-timeout-cascade",
            confidence=0.91,
            last_accessed_days=1,
            resolved_promoted=result.passed,
        ),
        Learning(
            id="learn-stale-retry-guess",
            confidence=0.40,
            last_accessed_days=45,          # idle past 30-day TTL
        ),
        Learning(
            id="learn-superseded-timeout-hypothesis",
            confidence=0.55,
            last_accessed_days=3,
            contradicted_by_higher_conf=True,
        ),
        Learning(
            id="learn-order-service-backpressure",
            confidence=0.88,
            last_accessed_days=2,           # fresh, high-confidence: kept
        ),
    ]
    kept, removed = garbage_collect(learnings)
    total = len(learnings)
    promoted = sum(1 for lrn in learnings if lrn.resolved_promoted)
    rate = promotion_rate(total, promoted)
    print("\ndaily garbage collection (Kepler dual-store):")
    print(json.dumps({
        "kept": [lrn.id for lrn in kept],
        "removed": [lrn.id for lrn in removed],
        "promotion_rate": rate,
        "promotion_health": promotion_health(rate),
    }, indent=2))
    print("\nresult: prompt refinement passed canary, promoted to Knowledge; "
          "stale, contradicted, and idle Learnings reclaimed.")


def cmd_benchmark(args):
    failures = []

    # Test 1: assign_tier routes prompt_refinement -> TIER1
    if assign_tier({"intervention_type": "prompt_refinement"}) != "TIER1_CANARY":
        failures.append("prompt_refinement should route to TIER1_CANARY")
    if assign_tier({"intervention_type": "hyperparameter"}) != "TIER1_CANARY":
        failures.append("hyperparameter should route to TIER1_CANARY")

    # Test 2: assign_tier routes fine_tune / tool_integration -> TIER2
    if assign_tier({"intervention_type": "fine_tune"}) != "TIER2_STAGING":
        failures.append("fine_tune should route to TIER2_STAGING")
    if assign_tier({"intervention_type": "tool_integration"}) != "TIER2_STAGING":
        failures.append("tool_integration should route to TIER2_STAGING")

    # Test 3: Tier 3 overrides (touches_safety / new_tool / novel)
    if assign_tier({"intervention_type": "prompt_refinement", "touches_safety": True}) != "TIER3_AIRLOCK":
        failures.append("touches_safety should override to TIER3_AIRLOCK")
    if assign_tier({"intervention_type": "fine_tune", "new_tool": True}) != "TIER3_AIRLOCK":
        failures.append("new_tool should override to TIER3_AIRLOCK")
    if assign_tier({"intervention_type": "hyperparameter", "novel": True}) != "TIER3_AIRLOCK":
        failures.append("novel should override to TIER3_AIRLOCK")

    # Test 4: unknown intervention with no Tier 3 flag raises
    try:
        assign_tier({"intervention_type": "mystery"})
        failures.append("unknown intervention_type should raise ValueError")
    except ValueError:
        pass

    # Test 5: canary passes on significant lift + no regression
    ok = canary_gate({
        "target_lift": 0.04,
        "target_pvalue": 0.01,
        "kpi_deltas": {"task_success_rate": 0.006, "cost_usd": 0.0},
    })
    if not ok.passed or ok.tier != "TIER1_CANARY":
        failures.append("canary should pass on significant lift with no regression")

    # Test 6: canary fails on KPI regression despite significant lift
    bad = canary_gate({
        "target_lift": 0.04,
        "target_pvalue": 0.01,
        "kpi_deltas": {"safety_score": -0.02},
    })
    if bad.passed:
        failures.append("canary should fail on core-KPI regression")

    # Test 6b: canary fails on non-significant p-value
    nonsig = canary_gate({"target_lift": 0.04, "target_pvalue": 0.20, "kpi_deltas": {}})
    if nonsig.passed:
        failures.append("canary should fail when p-value not below alpha")

    # Test 7: staging utility formula U = wa*acc + wc*(1-cost) + ws*safety
    u = staging_utility(
        {"accuracy": 0.9, "cost": 0.2, "safety_score": 1.0},
        {"w_accuracy": 0.5, "w_cost": 0.3, "w_safety": 0.2},
    )
    expected = 0.5 * 0.9 + 0.3 * (1 - 0.2) + 0.2 * 1.0
    if abs(u - expected) > 1e-9:
        failures.append(f"staging_utility wrong: {u} != {expected}")

    # Test 8: staging FAILS when safety_regression True even if utility high
    weights = {"w_accuracy": 0.5, "w_cost": 0.3, "w_safety": 0.2}
    high = staging_gate(
        {"accuracy": 0.99, "cost": 0.05, "safety_score": 1.0, "safety_regression": True},
        weights,
        baseline={"accuracy": 0.70, "cost": 0.40, "safety_score": 0.90},
    )
    if high.passed:
        failures.append("staging must fail on safety_regression even with high utility")

    # Test 9: staging passes net-positive over baseline with no safety regression
    good = staging_gate(
        {"accuracy": 0.92, "cost": 0.10, "safety_score": 0.98, "safety_regression": False},
        weights,
        baseline={"accuracy": 0.80, "cost": 0.25, "safety_score": 0.95},
    )
    if not good.passed or good.tier != "TIER2_STAGING":
        failures.append("staging should pass net-positive over baseline, no safety regression")

    # Test 10: airlock requires human; pending on None, pass only on approve
    pending = airlock_gate({"risk": "high", "reward": "large"}, None)
    if pending.passed or not pending.requires_human:
        failures.append("airlock with no decision should be pending + requires_human")
    approved = airlock_gate({"risk": "high"}, "approve")
    if not approved.passed or not approved.requires_human:
        failures.append("airlock should pass only on human approve, still requires_human")
    rejected = airlock_gate({"risk": "high"}, "reject")
    if rejected.passed:
        failures.append("airlock reject should not pass")

    # Test 11: graduated_validation end-to-end routes and gates
    gv = graduated_validation({
        "intervention_type": "prompt_refinement",
        "metrics": {"target_lift": 0.03, "target_pvalue": 0.02, "kpi_deltas": {}},
    })
    if not gv.passed or gv.tier != "TIER1_CANARY":
        failures.append("graduated_validation should route prompt->canary and pass")
    gv3 = graduated_validation({
        "intervention_type": "fine_tune", "new_tool": True,
        "risk_reward": {"risk": "high"}, "human_decision": None,
    })
    if gv3.passed or not gv3.requires_human or gv3.tier != "TIER3_AIRLOCK":
        failures.append("graduated_validation new_tool should airlock + require human")

    # Test 12: garbage_collect removes idle / promoted / contradicted, keeps fresh
    learnings = [
        Learning(id="idle", confidence=0.5, last_accessed_days=45),
        Learning(id="promoted", confidence=0.8, last_accessed_days=1, resolved_promoted=True),
        Learning(id="contradicted", confidence=0.5, last_accessed_days=2,
                 contradicted_by_higher_conf=True),
        Learning(id="fresh", confidence=0.9, last_accessed_days=3),
    ]
    kept, removed = garbage_collect(learnings, ttl_days=30)
    kept_ids = {lrn.id for lrn in kept}
    removed_ids = {lrn.id for lrn in removed}
    if kept_ids != {"fresh"}:
        failures.append(f"gc should keep only fresh, kept={kept_ids}")
    if removed_ids != {"idle", "promoted", "contradicted"}:
        failures.append(f"gc should remove idle/promoted/contradicted, removed={removed_ids}")

    # Test 13: TTL boundary — exactly 30 days is kept, 31 removed
    boundary = [
        Learning(id="at-ttl", confidence=0.5, last_accessed_days=30),
        Learning(id="past-ttl", confidence=0.5, last_accessed_days=31),
    ]
    k2, r2 = garbage_collect(boundary, ttl_days=30)
    if {lrn.id for lrn in k2} != {"at-ttl"} or {lrn.id for lrn in r2} != {"past-ttl"}:
        failures.append("gc TTL boundary wrong: 30 kept, 31 removed")

    # Test 14: promotion_health flags < 10%
    if promotion_health(promotion_rate(100, 5)) != "criteria too strict":
        failures.append("promotion_health should flag 5% as too strict")
    if promotion_health(promotion_rate(100, 25)) != "healthy":
        failures.append("promotion_health should mark 25% as healthy")
    if promotion_rate(0, 0) != 0.0:
        failures.append("promotion_rate should be 0.0 on empty set")

    # Test 15: provenance signature is deterministic + content-sensitive
    c = {"intervention_type": "prompt_refinement", "id": "x"}
    if provenance_signature(c) != provenance_signature(dict(c)):
        failures.append("provenance signature should be deterministic")
    if provenance_signature(c) == provenance_signature({**c, "id": "y"}):
        failures.append("provenance signature should change with content")

    # Test 16: GateResult.to_dict round-trips the fields
    d = GateResult(passed=True, tier="TIER1_CANARY", reasons=["ok"]).to_dict()
    if d != {"passed": True, "tier": "TIER1_CANARY", "reasons": ["ok"], "requires_human": False}:
        failures.append(f"GateResult.to_dict shape wrong: {d}")

    total = 16
    print("=" * 70)
    print(f"graduated-validation-protocol benchmark - {total - len(failures)}/{total} passed")
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

    p_assign = sub.add_parser("assign", help="Assign a candidate to a risk tier")
    p_assign.add_argument("--path", required=True, help="candidate.json")
    p_assign.set_defaults(func=cmd_assign)

    p_val = sub.add_parser("validate", help="Assign tier and run the matching gate")
    p_val.add_argument("--path", required=True, help="candidate.json")
    p_val.set_defaults(func=cmd_validate)

    p_gc = sub.add_parser("gc", help="Garbage-collect the Learnings subgraph")
    p_gc.add_argument("--path", required=True, help="learnings.json (list of Learning dicts)")
    p_gc.add_argument("--ttl-days", type=int, default=30, dest="ttl_days")
    p_gc.set_defaults(func=cmd_gc)

    p_scen = sub.add_parser("scenario", help="DevOps prompt-canary scenario")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
