#!/usr/bin/env python3
"""model-routing-selector CLI — selective intelligence for the workflow graph.

Invocations:
    model-routing-selector --help
    model-routing-selector route AlertClassifier
    model-routing-selector static CausalAttributionNode
    model-routing-selector cascade CausalAttributionNode --confidence 0.62
    model-routing-selector learned CausalAttributionNode --cost-threshold 0.7
    model-routing-selector pipeline --escalation-rate 0.3
    model-routing-selector benchmark

Every Process step in SKILL.md maps to a subcommand so any harness (cron, CI,
Claude Code, Cursor, Gemini CLI, Windsurf, OpenCode) gets the same behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lib  # noqa: E402

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "model-routing-selector (Ch8 — Selective Intelligence)"
    text = SKILL_MD.read_text(encoding="utf-8")
    desc, in_desc, fm, in_fm = [], False, 0, False
    for line in text.splitlines():
        if line.strip() == "---":
            fm += 1
            in_fm = fm == 1
            if fm == 2:
                break
            continue
        if not in_fm:
            continue
        if line.startswith("description:"):
            in_desc = True
            continue
        if in_desc:
            if line and not line[0].isspace():
                in_desc = False
                continue
            desc.append(line.strip())
    return " ".join(d for d in desc if d) or "model-routing-selector"


def cmd_route(args):
    print(json.dumps(lib.cheapest_meeting_bar(args.node), indent=2))


def cmd_static(args):
    print(json.dumps(lib.static_route(args.node), indent=2))


def cmd_cascade(args):
    print(json.dumps(lib.cascade_route(args.node, args.confidence), indent=2))


def cmd_learned(args):
    print(json.dumps(lib.learned_route(args.node, args.cost_threshold), indent=2))


def cmd_pipeline(args):
    print(json.dumps(lib.pipeline_cost(args.escalation_rate), indent=2))


def cmd_benchmark(args):
    failures = []

    # 1-6: the router re-derives the book's DEVOPS_MODEL_CONFIG assignment.
    expect = {
        "AlertClassifier": "llama-3.1-3b",
        "QueryAnalyst": "llama-3.1-3b",
        "LogParser": "llama-3.1-3b",
        "DependencyAnalyzer": "llama-3.1-8b",
        "PredictionSynthesis": "claude-sonnet",
    }
    for node, model in expect.items():
        got = lib.cheapest_meeting_bar(node)["model"]
        if got != model:
            failures.append(f"{node}: expected {model}, got {got}")

    # 7: CausalAttributionNode should be recommended as a cascade, not raw frontier.
    causal = lib.cheapest_meeting_bar("CausalAttributionNode")
    if causal["strategy"] != "cascade":
        failures.append("CausalAttributionNode should recommend a cascade")

    # 8: cascade escalates on low confidence, serves cheap on high.
    if lib.cascade_route("X", 0.9)["served_by"] != "llama-3.1-3b":
        failures.append("high confidence should be served by the cheap SLM")
    if lib.cascade_route("X", 0.5)["served_by"] != "claude-sonnet":
        failures.append("low confidence should escalate to frontier")

    # 9: blended pipeline cost reduction is substantial (book: ~80% under
    #    token-weighting; ~70% under the equal-weight model here).
    pc = lib.pipeline_cost(0.30)
    if pc["reduction_pct"] < 65.0:
        failures.append(f"pipeline reduction {pc['reduction_pct']}% below 65%")

    # 10: a fine-tuned SLM clears the 0.99 alert bar; a frontier model is still
    #     needed for synthesis (the specialization mechanism).
    if lib.effective_quality("llama-3.1-3b", lib.NODES["AlertClassifier"]) < 0.99:
        failures.append("fine-tuned SLM should meet the 0.99 classification bar")
    if lib.effective_quality("llama-3.1-3b", lib.NODES["PredictionSynthesis"]) >= 0.92:
        failures.append("a 3B model should NOT clear the synthesis bar")

    total = 10
    print("=" * 70)
    print(f"model-routing-selector benchmark — {total - len(failures)}/{total} passed")
    print(f"  blended pipeline reduction: {pc['reduction_pct']}% "
          f"(equal-weight; book reports ~80% under token-weighting)")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All gates passed.")
    sys.exit(0)


def main():
    p = argparse.ArgumentParser(prog="model-routing-selector", description=_skill_description())
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("route", help="Pick the cheapest model that meets the node's quality bar")
    pr.add_argument("node", choices=sorted(lib.NODES))
    pr.set_defaults(func=cmd_route)

    ps = sub.add_parser("static", help="Static routing by node type (book assignment)")
    ps.add_argument("node", choices=sorted(lib.NODES))
    ps.set_defaults(func=cmd_static)

    pc = sub.add_parser("cascade", help="Threshold-based cascade given a confidence score")
    pc.add_argument("node")
    pc.add_argument("--confidence", type=float, required=True)
    pc.set_defaults(func=cmd_cascade)

    pl = sub.add_parser("learned", help="Learned routing (RouteLLM / MixLLM)")
    pl.add_argument("node")
    pl.add_argument("--cost-threshold", type=float, default=0.7)
    pl.set_defaults(func=cmd_learned)

    pp = sub.add_parser("pipeline", help="Blended cost: frontier-everywhere vs selective")
    pp.add_argument("--escalation-rate", type=float, default=0.30)
    pp.set_defaults(func=cmd_pipeline)

    pb = sub.add_parser("benchmark", help="Verification gate battery")
    pb.set_defaults(func=cmd_benchmark)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
