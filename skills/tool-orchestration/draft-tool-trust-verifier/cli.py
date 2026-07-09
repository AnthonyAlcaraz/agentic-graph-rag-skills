#!/usr/bin/env python3
"""
draft-tool-trust-verifier — multi-harness CLI wrapper.

    draft-tool-trust-verifier --help
    draft-tool-trust-verifier verify-claims
    draft-tool-trust-verifier trust --success 6 --fail 2 --slow 1
    draft-tool-trust-verifier gather
    draft-tool-trust-verifier learn
    draft-tool-trust-verifier rewrite
    draft-tool-trust-verifier draft --json
    draft-tool-trust-verifier benchmark

The CLI mirrors the SKILL.md Process section step by step so any harness that
runs CLI tools (cron, CI, Claude Code, Cursor, Gemini CLI, Windsurf, OpenCode)
gets the same behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lib  # noqa: E402

DEFAULT_TOOL = HERE / "sample-tool-under-test.json"
SKILL_DESCRIPTION = (
    "Learn what a tool actually does, not what it claims. Flags marketing-gamed "
    "descriptions, tracks performance-based trust scores, and runs the DRAFT loop "
    "(gather boundary-probing experience, learn the doc-vs-reality gap, rewrite an "
    "AI-optimized spec) so tool selection is driven by measured capability."
)


def cmd_verify_claims(args: argparse.Namespace) -> int:
    tool = lib.load_tool_under_test(args.tool)
    result = lib.verify_claims(tool)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"Tool: {result['tool']}")
    print(f"Marketing phrases flagged: {result['marketing_phrases']}")
    print(f"Declared capabilities:  {result['declared_capabilities']}")
    print(f"Structured (testable):  {result['structured_capabilities']}")
    print(f"Verifiable: {result['verifiable']}  "
          "(all capabilities have name + input_types + output_types)")
    return 0


def cmd_trust(args: argparse.Namespace) -> int:
    ts = lib.TrustScore()
    # Replay a synthetic execution history: successes, then failures, then slow calls.
    for _ in range(args.success):
        ts.record(success=True, latency_ms=100)
    for _ in range(args.fail):
        ts.record(success=False, latency_ms=100)
    for _ in range(args.slow):
        ts.record(success=True, latency_ms=5000)
    out = ts.as_dict()
    if args.json:
        print(json.dumps(out, indent=2))
        return 0
    print(f"neutral start: 0.5")
    print(f"after {args.success} success / {args.fail} fail / {args.slow} slow calls:")
    for k, v in out.items():
        print(f"  {k}: {v}")
    return 0


def cmd_gather(args: argparse.Namespace) -> int:
    tool = lib.load_tool_under_test(args.tool)
    obs = lib.gather_experience(tool, tool.get("probes", []))
    if args.json:
        print(json.dumps([o.__dict__ for o in obs], indent=2))
        return 0
    print(f"Experience gathering — {len(obs)} diverse probes (dedup enforced):\n")
    for o in obs:
        status = "ok " if o.success else "FAIL"
        note = o.error or ""
        print(f"  [{status}] {o.latency_ms:7.1f}ms  {o.probe[:48]!r} {note}")
    return 0


def cmd_learn(args: argparse.Namespace) -> int:
    tool = lib.load_tool_under_test(args.tool)
    obs = lib.gather_experience(tool, tool.get("probes", []))
    learning = lib.learn_from_experience(tool, obs)
    if args.json:
        print(json.dumps(learning, indent=2))
        return 0
    print(f"Tool: {learning['tool']}")
    print(f"Claimed: {learning['claim']!r}\n")
    print(f"probes run: {learning['probes_run']}  failures: {learning['failures']}")
    print(f"discovered error conditions: {learning['discovered_error_conditions']}")
    print(f"max successful input length: {learning['max_successful_len']}")
    print(f"latency payload-dependent: {learning['latency_payload_dependent']}")
    print(f"claim over-promises 'any text': {learning['gap_over_promises_any_text']}")
    print(f"converged (no gaps left): {learning['converged']}")
    return 0


def cmd_rewrite(args: argparse.Namespace) -> int:
    tool = lib.load_tool_under_test(args.tool)
    result = lib.run_draft(tool, tool.get("probes", []))
    refined = result["refined_spec"]
    if args.json:
        print(json.dumps(refined, indent=2))
        return 0
    print("Refined (AI-optimized) spec:\n")
    print(f"  {refined['refined_description']}")
    print(f"  error_conditions: {refined['error_conditions']}")
    print(f"  observed_max_input_len: {refined['observed_max_input_len']}")
    print(f"  performance: {refined['performance']}")
    return 0


def cmd_draft(args: argparse.Namespace) -> int:
    tool = lib.load_tool_under_test(args.tool)
    result = lib.run_draft(tool, tool.get("probes", []))
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"DRAFT loop over {len(result['observations'])} probes\n")
    print(f"discovered errors: {result['learning']['discovered_error_conditions']}")
    print(f"refined: {result['refined_spec']['refined_description']}")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    """
    Prove: (1) the claim is flagged as marketing/unverifiable, (2) DRAFT
    discovers the undocumented constraints, (3) trust drops for a failing tool.
    """
    tool = lib.load_tool_under_test(args.tool)
    claims = lib.verify_claims(tool)
    draft = lib.run_draft(tool, tool.get("probes", []))
    learning = draft["learning"]

    # Performance-based trust on a genuinely flaky tool (failures dominate,
    # plus slow calls) — proves the mechanism moves trust below neutral.
    flaky = lib.TrustScore()
    for _ in range(2):
        flaky.record(success=True, latency_ms=100)
    for _ in range(6):
        flaky.record(success=False, latency_ms=100)
    for _ in range(2):
        flaky.record(success=True, latency_ms=5000)  # slow -> latency penalty

    expected = {"empty input rejected", "input over 256 chars rejected", "non-ASCII input rejected"}
    discovered = set(learning["discovered_error_conditions"])
    all_discovered = expected.issubset(discovered)

    if args.json:
        print(json.dumps({
            "marketing_flagged": bool(claims["marketing_phrases"]),
            "verifiable_capabilities": claims["verifiable"],
            "expected_constraints_discovered": all_discovered,
            "over_promise_detected": learning["gap_over_promises_any_text"],
            "flaky_tool_trust": flaky.as_dict(),
            "flaky_trust_below_neutral": flaky.score < 0.5,
        }, indent=2))
        return 0
    print("DRAFT tool-trust benchmark\n")
    print(f"marketing phrases flagged: {bool(claims['marketing_phrases'])} "
          f"({claims['marketing_phrases']})")
    print(f"capabilities fully verifiable: {claims['verifiable']}")
    print(f"expected constraints discovered by DRAFT: {all_discovered}")
    print(f"   discovered: {sorted(discovered)}")
    print(f"'any text' over-promise detected: {learning['gap_over_promises_any_text']}")
    print(f"flaky-tool trust (2 ok / 6 fail / 2 slow): {flaky.as_dict()}")
    print(f"flaky-tool trust below neutral (0.5): {flaky.score < 0.5}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="draft-tool-trust-verifier", description=SKILL_DESCRIPTION
    )
    parser.add_argument("--tool", type=str, default=str(DEFAULT_TOOL),
                        help="Path to the tool-under-test JSON (default: bundled sample)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_vc = sub.add_parser("verify-claims", help="Flag marketing claims; check structured capabilities")
    p_vc.add_argument("--json", action="store_true")
    p_vc.set_defaults(func=cmd_verify_claims)

    p_tr = sub.add_parser("trust", help="Replay an execution history into a performance-based trust score")
    p_tr.add_argument("--success", type=int, default=6)
    p_tr.add_argument("--fail", type=int, default=2)
    p_tr.add_argument("--slow", type=int, default=1)
    p_tr.add_argument("--json", action="store_true")
    p_tr.set_defaults(func=cmd_trust)

    p_g = sub.add_parser("gather", help="DRAFT phase 1 — probe tool boundaries")
    p_g.add_argument("--json", action="store_true")
    p_g.set_defaults(func=cmd_gather)

    p_l = sub.add_parser("learn", help="DRAFT phase 2 — doc-vs-reality gap")
    p_l.add_argument("--json", action="store_true")
    p_l.set_defaults(func=cmd_learn)

    p_rw = sub.add_parser("rewrite", help="DRAFT phase 3 — AI-optimized refined spec")
    p_rw.add_argument("--json", action="store_true")
    p_rw.set_defaults(func=cmd_rewrite)

    p_d = sub.add_parser("draft", help="Run the full DRAFT loop (gather -> learn -> rewrite)")
    p_d.add_argument("--json", action="store_true")
    p_d.set_defaults(func=cmd_draft)

    p_b = sub.add_parser("benchmark", help="Prove claim-flagging + constraint-discovery + trust-drop")
    p_b.add_argument("--json", action="store_true")
    p_b.set_defaults(func=cmd_benchmark)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
