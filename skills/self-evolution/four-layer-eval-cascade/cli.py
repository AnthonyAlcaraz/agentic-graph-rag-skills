#!/usr/bin/env python3
"""four-layer-eval-cascade CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    GateResult,
    ContextVerdict,
    CognitiveVerdict,
    TIRReward,
    layer0_hallucination_gate,
    layer1_context_evaluator,
    layer2_cognitive_fault_isolator,
    layer3_tir_judge,
    run_cascade,
    PROMPT_REFINEMENT,
    RETRIEVAL_FIX,
    BLOCK_AND_REGENERATE,
    FINE_TUNE,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "execution-graph primitive (Ch7)"
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
    return " ".join(d for d in desc if d) or "four-layer-eval-cascade (Ch7)"


# -- devops-autopsy scenario (the chapter's premature-closure autopsy) -------

def _devops_execution() -> dict:
    """Rebuild the chapter's premature-closure execution end to end.

    Fictional AWS account 123456789012. stripe-python 3.2.1 -> 3.3.0, timeout
    30s -> 10s, checkout-service -> order-service -> fulfillment-service.
    """
    return {
        "execution_id": "pred_7f3a9c",
        "query": (
            "Will updating stripe-python from 3.2.1 to 3.3.0 cause failures "
            "in the checkout-service?"
        ),
        # Grounded answer: Layer 0 passes.
        "answer": (
            "checkout-service depends_on stripe-python. changelog 3.3.0 "
            "deprecated batch_charge and reduced timeout 30s to 10s."
        ),
        "context_premise": (
            "checkout-service DEPENDS_ON stripe-python. stripe-python "
            "HAS_VERSION 3.3.0. changelog 3.3.0: deprecated batch_charge API; "
            "connection pool timeout reduced 30s to 10s. checkout-service "
            "order-service fulfillment-service. aws account 123456789012."
        ),
        # No required_claims: Layer 1 defaults to sufficient at 0.97.
        "required_claims": [],
        "infogain_trace": [0.34, 0.29, 0.22, 0.03, -0.01, 0.19],
        "knowledge_index": 0.91,
        "fault_node": {"node_id": "CausalAttributionNode"},
        "diagnosis": (
            "Premature commitment to 'API contract violation' hypothesis at "
            "step 4. Configuration change (timeout reduction 30s to 10s) had "
            "equal evidentiary support but was not explored after early "
            "commitment to the API path."
        ),
        "claim_value": None,
        "expected_value": None,
        "format_ok": True,
        "tool_ok": True,
    }


# -- subcommands -------------------------------------------------------------

def cmd_gate(args):
    result = layer0_hallucination_gate(
        args.query, args.answer, args.premise, threshold=args.threshold,
    )
    print(json.dumps(result.to_dict(), indent=2))


def cmd_context(args):
    verdict = layer1_context_evaluator(
        args.query, args.context, required_claims=args.required_claim or None,
    )
    print(json.dumps(verdict.to_dict(), indent=2))


def cmd_cognitive(args):
    fault_node = None
    if args.fault_node:
        try:
            fault_node = json.loads(args.fault_node)
        except json.JSONDecodeError:
            fault_node = {"node_id": args.fault_node}
    verdict = layer2_cognitive_fault_isolator(
        infogain_trace=args.infogain,
        knowledge_index=args.ki,
        fault_node=fault_node,
        ki_threshold=args.ki_threshold,
        infogain_floor=args.infogain_floor,
        diagnosis=args.diagnosis,
    )
    print(json.dumps(verdict.to_dict(), indent=2))


def cmd_tir(args):
    reward = layer3_tir_judge(
        claim_value=args.claim,
        expected_value=args.expected,
        format_ok=not args.no_format_ok,
        tool_ok=not args.no_tool_ok,
    )
    print(json.dumps(reward.to_dict(), indent=2))


def cmd_cascade(args):
    with open(args.path, encoding="utf-8") as f:
        execution = json.load(f)
    report = run_cascade(execution)
    print(json.dumps(report, indent=2))


def cmd_scenario(args):
    if args.name != "devops-autopsy":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps Cognitive Autopsy - four-layer cascade on one prediction")
    print("=" * 70)
    execution = _devops_execution()
    report = run_cascade(execution)
    print(json.dumps(report, indent=2))
    print()
    print(f"stopped_at_layer         : {report['stopped_at_layer']}")
    print(f"overall_verdict          : {report['overall_verdict']}")
    print(f"recommended_intervention : {report['recommended_intervention']}")
    print(f"target_nodes             : {report['target_nodes']}")


def cmd_benchmark(args):
    failures = []
    total = 0

    def check(name, cond):
        nonlocal total
        total += 1
        if not cond:
            failures.append(name)

    # 1: multiplicative TIR zeroes on a wrong answer (well formatted, good tool)
    r = layer3_tir_judge(claim_value=340, expected_value=210,
                         format_ok=True, tool_ok=True)
    check("TIR composite zeroes on wrong answer", r.composite == 0.0)
    check("TIR correctness is 0 on wrong answer", r.correctness == 0.0)

    # 2: TIR all-correct composite is 1.0
    r2 = layer3_tir_judge(claim_value=340, expected_value=340)
    check("TIR composite is 1.0 on correct answer", r2.composite == 1.0)

    # 3: TIR bad format zeroes composite even with correct value
    r3 = layer3_tir_judge(claim_value=340, expected_value=340,
                          format_ok=False, tool_ok=True)
    check("TIR bad format zeroes composite", r3.composite == 0.0)

    # 4: Layer 0 grounded answer passes
    g_ok = layer0_hallucination_gate(
        "does checkout-service depend on stripe-python",
        "checkout-service depends_on stripe-python",
        "checkout-service DEPENDS_ON stripe-python. stripe-python HAS_VERSION 3.3.0.",
    )
    check("Layer 0 passes on grounded answer", g_ok.passed and g_ok.action == "PROCEED")

    # 5: Layer 0 ungrounded (absent entity) hard-blocks
    g_bad = layer0_hallucination_gate(
        "how does checkout-service call stripe-python",
        "checkout-service uses batch_charge via the payments gateway module",
        "checkout-service depends_on stripe-python. stripe-python has_version 3.3.0.",
    )
    check("Layer 0 hard-blocks ungrounded answer",
          (not g_bad.passed) and g_bad.skip_full_eval
          and g_bad.action == BLOCK_AND_REGENERATE)

    # 6: cascade stops at Layer 0 on an ungrounded answer
    rep0 = run_cascade({
        "execution_id": "ex_l0",
        "query": "how does checkout-service call stripe-python",
        "answer": "checkout-service uses batch_charge via the payments gateway module",
        "context_premise": "checkout-service depends_on stripe-python. stripe-python has_version 3.3.0.",
        "required_claims": [],
        "infogain_trace": [0.4, 0.3],
        "knowledge_index": 0.95,
    })
    check("cascade stops at Layer 0 on ungrounded answer",
          rep0["stopped_at_layer"] == 0
          and rep0["recommended_intervention"] == BLOCK_AND_REGENERATE)

    # 7: cascade stops at Layer 1 on insufficient context (grounded but claim missing)
    rep1 = run_cascade({
        "execution_id": "ex_l1",
        "query": "will the upgrade break checkout-service",
        "answer": "checkout-service depends_on stripe-python",
        "context_premise": "checkout-service depends_on stripe-python. stripe-python has_version 3.3.0.",
        "required_claims": ["specific stripe-python methods called by checkout-service"],
        "infogain_trace": [0.4, 0.3],
        "knowledge_index": 0.95,
    })
    check("cascade stops at Layer 1 on insufficient context",
          rep1["stopped_at_layer"] == 1
          and rep1["recommended_intervention"] == RETRIEVAL_FIX
          and rep1["layer_1_context"]["sufficient"] is False)

    # 8: Layer 2 classifies REASONING vs KNOWLEDGE by KI
    reasoning = layer2_cognitive_fault_isolator([0.34, 0.29, 0.22, 0.03, -0.01, 0.19], 0.91)
    knowledge = layer2_cognitive_fault_isolator([0.34, 0.29, 0.22, 0.03, -0.01, 0.19], 0.50)
    check("Layer 2 classifies REASONING when KI above threshold",
          reasoning.failure_type == "REASONING")
    check("Layer 2 classifies KNOWLEDGE when KI below threshold",
          knowledge.failure_type == "KNOWLEDGE")

    # 9: low_infogain_steps computed correctly from a known trace
    check("low_infogain_steps are [4, 5] for the premature-closure trace",
          reasoning.low_infogain_steps == [4, 5])
    clean = layer2_cognitive_fault_isolator([0.34, 0.29, 0.22, 0.19, 0.11, 0.18], 0.91)
    check("low_infogain_steps empty on a clean trace",
          clean.low_infogain_steps == [])

    # 10: devops-autopsy recommends PROMPT_REFINEMENT, stops at Layer 2
    dev = run_cascade(_devops_execution())
    check("devops-autopsy overall verdict is FAILURE", dev["overall_verdict"] == "FAILURE")
    check("devops-autopsy stops at Layer 2", dev["stopped_at_layer"] == 2)
    check("devops-autopsy recommends PROMPT_REFINEMENT",
          dev["recommended_intervention"] == PROMPT_REFINEMENT)
    check("devops-autopsy targets CausalAttributionNode",
          dev["target_nodes"] == ["CausalAttributionNode"])
    check("devops-autopsy Layer 1 context sufficient",
          dev["layer_1_context"]["sufficient"] is True)
    check("devops-autopsy Layer 2 low steps are [4, 5]",
          dev["layer_2_cognitive"]["low_infogain_steps"] == [4, 5])

    # 11: a KNOWLEDGE failure routes to FINE_TUNE (not PROMPT_REFINEMENT)
    repk = run_cascade({
        "execution_id": "ex_know",
        "query": "will the upgrade break checkout-service",
        "answer": "checkout-service depends_on stripe-python",
        "context_premise": "checkout-service depends_on stripe-python. stripe-python has_version 3.3.0.",
        "required_claims": [],
        "infogain_trace": [0.34, 0.29, 0.22, 0.03, -0.01, 0.19],
        "knowledge_index": 0.55,
        "fault_node": {"node_id": "FactRecallNode"},
    })
    check("KNOWLEDGE failure routes to FINE_TUNE",
          repk["stopped_at_layer"] == 2
          and repk["layer_2_cognitive"]["failure_type"] == "KNOWLEDGE"
          and repk["recommended_intervention"] == FINE_TUNE)

    # 12: a fully clean execution passes all four layers
    reppass = run_cascade({
        "execution_id": "ex_pass",
        "query": "what version does checkout-service depend on",
        "answer": "checkout-service depends_on stripe-python 3.3.0",
        "context_premise": "checkout-service depends_on stripe-python. stripe-python has_version 3.3.0.",
        "required_claims": [],
        "infogain_trace": [0.34, 0.29, 0.22, 0.19, 0.11, 0.18],
        "knowledge_index": 0.95,
        "claim_value": 340,
        "expected_value": 340,
        "format_ok": True,
        "tool_ok": True,
    })
    check("clean execution passes all layers",
          reppass["overall_verdict"] == "PASS"
          and reppass["stopped_at_layer"] is None
          and reppass["recommended_intervention"] == "NONE")

    # 13: cascade stops at Layer 3 on a wrong quantitative claim
    rep3 = run_cascade({
        "execution_id": "ex_l3",
        "query": "how much did p99 latency increase",
        "answer": "checkout-service p99 latency increased after the stripe-python upgrade",
        "context_premise": "checkout-service p99 latency increased after the stripe-python upgrade.",
        "required_claims": [],
        "infogain_trace": [0.34, 0.29, 0.22, 0.19, 0.11, 0.18],
        "knowledge_index": 0.95,
        "claim_value": 340,
        "expected_value": 210,
        "format_ok": True,
        "tool_ok": True,
    })
    check("cascade stops at Layer 3 on wrong quantitative claim",
          rep3["stopped_at_layer"] == 3
          and rep3["recommended_intervention"] == FINE_TUNE)

    print("=" * 70)
    print(f"four-layer-eval-cascade benchmark - {total - len(failures)}/{total} passed")
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

    p_gate = sub.add_parser("gate", help="Layer 0 hallucination gate")
    p_gate.add_argument("--query", required=True)
    p_gate.add_argument("--answer", required=True)
    p_gate.add_argument("--premise", required=True, help="materialized context premise")
    p_gate.add_argument("--threshold", type=float, default=0.85)
    p_gate.set_defaults(func=cmd_gate)

    p_ctx = sub.add_parser("context", help="Layer 1 context evaluator")
    p_ctx.add_argument("--query", required=True)
    p_ctx.add_argument("--context", required=True)
    p_ctx.add_argument("--required-claim", action="append", default=[],
                       help="a required claim (repeatable)")
    p_ctx.set_defaults(func=cmd_context)

    p_cog = sub.add_parser("cognitive", help="Layer 2 cognitive fault isolator")
    p_cog.add_argument("--infogain", type=float, nargs="+", required=True,
                       help="InfoGain values per reasoning step")
    p_cog.add_argument("--ki", type=float, required=True, help="Knowledge Index")
    p_cog.add_argument("--fault-node", default="",
                       help="fault node id or JSON dict")
    p_cog.add_argument("--ki-threshold", type=float, default=0.8)
    p_cog.add_argument("--infogain-floor", type=float, default=0.05)
    p_cog.add_argument("--diagnosis", default="")
    p_cog.set_defaults(func=cmd_cognitive)

    p_tir = sub.add_parser("tir", help="Layer 3 TIR-Judge reward")
    p_tir.add_argument("--claim", required=True, help="the agent's claimed value")
    p_tir.add_argument("--expected", required=True, help="ground-truth value")
    p_tir.add_argument("--no-format-ok", action="store_true",
                       help="mark format as non-compliant")
    p_tir.add_argument("--no-tool-ok", action="store_true",
                       help="mark tool usage as inaccurate")
    p_tir.set_defaults(func=cmd_tir)

    p_cas = sub.add_parser("cascade", help="Run the four-layer cascade on an execution JSON")
    p_cas.add_argument("--path", required=True, help="path to an execution JSON")
    p_cas.set_defaults(func=cmd_cascade)

    p_scen = sub.add_parser("scenario", help="DevOps cognitive-autopsy scenario")
    p_scen.add_argument("name", help="scenario name: devops-autopsy")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
