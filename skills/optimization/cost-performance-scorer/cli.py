#!/usr/bin/env python3
"""cost-performance-scorer CLI — measure a routing policy on cost vs quality.

Invocations:
    cost-performance-scorer --help
    cost-performance-scorer score
    cost-performance-scorer score --log sample-invocations.json --json
    cost-performance-scorer node AlertClassifier
    cost-performance-scorer evaluate AlertClassifier
    cost-performance-scorer compare
    cost-performance-scorer benchmark

Every Process step in SKILL.md maps to a subcommand so any harness gets the
same behavior.
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
DEFAULT_LOG = HERE / "sample-invocations.json"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "cost-performance-scorer (Ch8 — Measuring Cost-Performance Tradeoffs)"
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
    return " ".join(d for d in desc if d) or "cost-performance-scorer"


def _load_tracker(log_path: Path) -> lib.CostTracker:
    data = json.loads(Path(log_path).read_text(encoding="utf-8"))
    tracker = lib.CostTracker()
    for row in data["invocations"]:
        tracker.log(lib.NodeInvocation(**row))
    return tracker


def cmd_score(args):
    tracker = _load_tracker(args.log)
    result = lib.score_policy(tracker)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    print(f"Pipeline total cost:       ${result['pipeline_total_cost_usd']}")
    print(f"Pipeline cost per success: ${result['pipeline_cost_per_success']}")
    print()
    print(f"{'node':<26} {'calls':>6} {'succ%':>7} {'$/success':>11} {'p95 ms':>8}")
    print("-" * 62)
    for r in result["nodes"]:
        print(f"{r['node']:<26} {r['n_calls']:>6} {r['success_rate'] * 100:>6.1f}% "
              f"{r['cost_per_success']:>11.6f} {r['p95_latency_ms']:>8.1f}")


def cmd_node(args):
    tracker = _load_tracker(args.log)
    print(json.dumps(tracker.node_report(args.node), indent=2))


def cmd_evaluate(args):
    if args.node not in lib.EVAL_SETS:
        print(f"no eval set for {args.node}; known: {sorted(lib.EVAL_SETS)}", file=sys.stderr)
        sys.exit(1)
    eval_set = lib.EVAL_SETS[args.node]
    if args.predictions:
        preds = [tuple(p) for p in json.loads(Path(args.predictions).read_text())]
    else:
        # Illustrative: a fine-tuned SLM that clears the AlertClassifier bar.
        preds = ([("P1", "P1")] * 40 + [("P2", "P2")] * 30 + [("P3", "P3")] * 29
                 + [("P1", "P3")])  # one catastrophic miss -> weighted error
    print(json.dumps(lib.evaluate_candidate(preds, eval_set), indent=2))


def cmd_compare(args):
    # A moderately cheaper model that fails 40% of the time vs a slightly pricier
    # reliable model that succeeds 98% of the time (Ch8 cost-per-success claim).
    result = lib.compare_cost_per_success(
        cheap_cost=0.007, cheap_success_rate=0.60,
        reliable_cost=0.010, reliable_success_rate=0.98,
    )
    print(json.dumps(result, indent=2))


def cmd_benchmark(args):
    failures = []
    tracker = _load_tracker(DEFAULT_LOG)

    # 1: cost_per_success computed and finite for a node.
    ac = tracker.node_report("AlertClassifier")
    if ac["cost_per_success"] <= 0:
        failures.append("AlertClassifier cost_per_success should be > 0")

    # 2: cheap SLM node is far cheaper per success than the frontier node.
    ps = tracker.node_report("PredictionSynthesis")
    if not ac["cost_per_success"] < ps["cost_per_success"]:
        failures.append("SLM node should be cheaper per success than frontier node")

    # 3: success rate reflects the seeded failures.
    if not (0.0 < tracker.success_rate("AlertClassifier") < 1.0):
        failures.append("AlertClassifier should have a mix of success/failure")

    # 4: evaluate_candidate applies the domain failure weight (P1_as_P3 = 10).
    preds = [("P1", "P3")]  # single catastrophic miss
    ev = lib.evaluate_candidate(preds, lib.EVAL_SETS["AlertClassifier"])
    if ev["weighted_error_rate"] != 10.0:
        failures.append(f"P1_as_P3 should weight 10.0, got {ev['weighted_error_rate']}")

    # 5: reverse miss is 10x cheaper.
    ev2 = lib.evaluate_candidate([("P3", "P1")], lib.EVAL_SETS["AlertClassifier"])
    if ev2["weighted_error_rate"] != 1.0:
        failures.append("P3_as_P1 should weight 1.0")

    # 6: meets_threshold gate honours the required accuracy.
    perfect = lib.evaluate_candidate([("P1", "P1")] * 100, lib.EVAL_SETS["AlertClassifier"])
    if not perfect["meets_threshold"]:
        failures.append("100% accuracy should meet the 0.99 threshold")
    near = lib.evaluate_candidate([("P1", "P1")] * 98 + [("P1", "P3")] * 2,
                                  lib.EVAL_SETS["AlertClassifier"])
    if near["meets_threshold"]:
        failures.append("0.98 accuracy should NOT meet the 0.99 threshold")

    # 7: the cost-per-success inversion (book's headline claim).
    cmp = lib.compare_cost_per_success(0.007, 0.60, 0.010, 0.98)
    if cmp["cheaper_per_call"] != "cheap":
        failures.append("cheap model should be cheaper per call")
    if cmp["cheaper_per_success"] != "reliable":
        failures.append("reliable model should win on cost per success")

    # 8: QueryAnalyst eval set has the book's 0.90 bar.
    if lib.EVAL_SETS["QueryAnalyst"]["required_accuracy"] != 0.90:
        failures.append("QueryAnalyst bar drifted from 0.90")

    total = 8
    print("=" * 70)
    print(f"cost-performance-scorer benchmark — {total - len(failures)}/{total} passed")
    print(f"  cost/success inversion: cheaper per call={cmp['cheaper_per_call']}, "
          f"cheaper per success={cmp['cheaper_per_success']}")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All gates passed.")
    sys.exit(0)


def main():
    p = argparse.ArgumentParser(prog="cost-performance-scorer", description=_skill_description())
    log_parent = argparse.ArgumentParser(add_help=False)
    log_parent.add_argument("--log", type=Path, default=DEFAULT_LOG,
                            help="Path to an invocation log JSON (default: bundled sample)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sc = sub.add_parser("score", parents=[log_parent],
                        help="Score the whole policy: cost-per-success per node")
    sc.add_argument("--json", action="store_true")
    sc.set_defaults(func=cmd_score)

    nd = sub.add_parser("node", parents=[log_parent], help="Per-node cost/latency report")
    nd.add_argument("node")
    nd.set_defaults(func=cmd_node)

    ev = sub.add_parser("evaluate", help="Evaluate a candidate against a per-node eval set")
    ev.add_argument("node", choices=sorted(lib.EVAL_SETS))
    ev.add_argument("--predictions", type=Path, default=None,
                    help="JSON list of [gold, predicted] pairs")
    ev.set_defaults(func=cmd_evaluate)

    cp = sub.add_parser("compare", help="Demonstrate the cost-per-success inversion")
    cp.set_defaults(func=cmd_compare)

    bm = sub.add_parser("benchmark", help="Verification gate battery")
    bm.set_defaults(func=cmd_benchmark)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
