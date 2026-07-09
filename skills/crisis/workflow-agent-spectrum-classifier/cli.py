#!/usr/bin/env python3
"""workflow-agent-spectrum-classifier CLI.

Invocations:
    cli.py --help
    cli.py classify --autonomy 0.9 --action 0.8 --authority 0.5 --determinism 0.15
    cli.py classify ... --memory --tools --contextual --json
    cli.py describe "the agent determines the investigation path and remediates"
    cli.py batch --systems sample-systems.json
    cli.py spectrum
    cli.py scenario devops
    cli.py benchmark

Every Process step in SKILL.md maps to a subcommand/flag so any harness that
runs CLI tools gets identical behavior.
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
DEFAULT_SYSTEMS = HERE / "sample-systems.json"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "workflow-agent-spectrum-classifier (Ch1)"
    text = SKILL_MD.read_text(encoding="utf-8")
    desc: list[str] = []
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
    return " ".join(d for d in desc if d) or "workflow-agent-spectrum-classifier"


def _print_result(r: dict) -> None:
    print(f"{r['name']}: {r['band']}  (position {r['spectrum_position']} on workflow 0 .. 1 agent)")
    d = r["agency_dimensions"]
    print(f"  autonomy={d['autonomy']}  action={d['action']}  authority={d['authority']}  path_determinism={r['path_determinism']}")
    print(f"  true-agent-by-action-test: {r['is_agent_by_action_test']}")
    caps = r["emergent_capabilities"]
    on = [k for k, v in caps.items() if v]
    print(f"  emergent capabilities present: {', '.join(on) if on else 'none'}")
    print(f"  band examples: {', '.join(r['examples_at_band'])}")
    for n in r["notes"]:
        print(f"  note: {n}")


def cmd_classify(args: argparse.Namespace) -> int:
    r = lib.classify(
        autonomy=args.autonomy,
        action=args.action,
        authority=args.authority,
        path_determinism=args.determinism,
        memory=args.memory,
        tool_use=args.tools,
        contextual=args.contextual,
        name=args.name,
    )
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        _print_result(r)
    return 0


def cmd_describe(args: argparse.Namespace) -> int:
    r = lib.classify_text(args.text, name=args.name)
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        _print_result(r)
        est = r["estimated_dimensions"]
        print(f"  (estimated from text) autonomy={est['autonomy']} action={est['action']} "
              f"authority={est['authority']} determinism={est['path_determinism']}")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.systems).read_text(encoding="utf-8"))
    systems = data["systems"] if isinstance(data, dict) else data
    results = [
        lib.classify(
            autonomy=s.get("autonomy", 0.0),
            action=s.get("action", 0.0),
            authority=s.get("authority", 0.0),
            path_determinism=s.get("path_determinism", 1.0),
            memory=s.get("memory", False),
            tool_use=s.get("tool_use", False),
            contextual=s.get("contextual", False),
            name=s.get("name", "system"),
        )
        for s in systems
    ]
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    for r in results:
        _print_result(r)
        print()
    return 0


def cmd_spectrum(args: argparse.Namespace) -> int:
    print("The Workflow-Agent Spectrum (Ch1)\n")
    print("Three dimensions of agency (sliding scales, not binary):")
    print("  * autonomy  — independent decision-making without external direction")
    print("  * action    — ability to effect change in the environment (no action -> advisor)")
    print("  * authority — scope and limits of permitted actions")
    print("\nBands on the continuous spectrum (workflow 0 .. 1 agent):")
    for band, examples in lib.SPECTRUM_EXAMPLES.items():
        print(f"  * {band.upper():<9} e.g. {', '.join(examples)}")
    print("\nFour emergent capabilities when a system operates across the dimensions:")
    print("  autonomous decision-making, contextual understanding,")
    print("  strategic tool utilization, memory persistence")
    return 0


def cmd_scenario(args: argparse.Namespace) -> int:
    if args.name != "devops":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        return 1
    print("=" * 70)
    print("DevOps systems on the spectrum — account 123456789012")
    print("=" * 70)
    data = json.loads(DEFAULT_SYSTEMS.read_text(encoding="utf-8"))
    for s in data["systems"]:
        print(f"\n### {s['name']} — {s['note']}")
        _print_result(
            lib.classify(
                autonomy=s["autonomy"], action=s["action"], authority=s["authority"],
                path_determinism=s["path_determinism"], memory=s.get("memory", False),
                tool_use=s.get("tool_use", False), contextual=s.get("contextual", False),
                name=s["name"],
            )
        )
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    failures: list[str] = []
    data = json.loads(DEFAULT_SYSTEMS.read_text(encoding="utf-8"))
    by_name = {s["name"]: s for s in data["systems"]}

    def cls(s):
        return lib.classify(
            autonomy=s["autonomy"], action=s["action"], authority=s["authority"],
            path_determinism=s["path_determinism"], memory=s.get("memory", False),
            tool_use=s.get("tool_use", False), contextual=s.get("contextual", False),
            name=s["name"],
        )

    # 1. FAQ generator lands at the WORKFLOW end.
    if cls(by_name["faq-generator"])["band"] != "WORKFLOW":
        failures.append("faq-generator should be WORKFLOW")

    # 2. DevOps investigation agent lands at the AGENT end.
    if cls(by_name["devops-investigation-agent"])["band"] != "AGENT":
        failures.append("devops-investigation-agent should be AGENT")

    # 3. Market-commentary report lands in the BLENDED middle.
    if cls(by_name["market-commentary-report"])["band"] != "BLENDED":
        failures.append("market-commentary-report should be BLENDED")

    # 4. The read-only advisor fails the action test (assistant/advisor, not agent).
    adv = cls(by_name["latency-advisor"])
    if adv["is_agent_by_action_test"]:
        failures.append("latency-advisor should FAIL the action test (advisor, not agent)")
    if not any("assistant/advisor" in n for n in adv["notes"]):
        failures.append("latency-advisor should carry the assistant/advisor note")

    # 5. Position is monotonic: more autonomy + less determinism => higher position.
    low = lib.spectrum_position(0.2, 0.9)
    high = lib.spectrum_position(0.9, 0.1)
    if not high > low:
        failures.append(f"position should rise with autonomy and fall with determinism: {low} !< {high}")

    # 6. Emergent capabilities reflect the supplied signals.
    r = lib.classify(0.9, 0.8, 0.5, 0.1, memory=True, tool_use=False, contextual=True)
    caps = r["emergent_capabilities"]
    if not (caps["autonomous_decision_making"] and caps["memory_persistence"]
            and caps["contextual_understanding"] and not caps["strategic_tool_utilization"]):
        failures.append(f"emergent capabilities wrong: {caps}")

    # 7. Free-text classifier places a dynamic-agent sentence toward AGENT.
    t = lib.classify_text(
        "The agent autonomously determines the investigation path, executes "
        "remediation, and rolls back deployments without step-by-step human direction."
    )
    if t["band"] == "WORKFLOW":
        failures.append(f"dynamic-agent text should not be WORKFLOW, got {t['band']}")

    # 8. Free-text classifier places a scripted sentence toward WORKFLOW.
    t2 = lib.classify_text(
        "A scripted FAQ generator follows a predefined path and only answers "
        "questions with read-only responses; it takes no actions."
    )
    if t2["band"] == "AGENT":
        failures.append(f"scripted text should not be AGENT, got {t2['band']}")

    total = 8
    print("=" * 70)
    print(f"workflow-agent-spectrum-classifier benchmark - {total - len(failures)}/{total} passed")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All gates passed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workflow-agent-spectrum-classifier", description=_skill_description())
    sub = parser.add_subparsers(dest="command", required=True)

    p_c = sub.add_parser("classify", help="Place a system by numeric agency dimensions")
    p_c.add_argument("--name", default="system")
    p_c.add_argument("--autonomy", type=float, required=True, help="0..1 independent decision-making")
    p_c.add_argument("--action", type=float, required=True, help="0..1 ability to effect change")
    p_c.add_argument("--authority", type=float, required=True, help="0..1 scope of permitted actions")
    p_c.add_argument("--determinism", type=float, required=True, help="0..1 how predefined the path is")
    p_c.add_argument("--memory", action="store_true", help="has memory persistence")
    p_c.add_argument("--tools", action="store_true", help="strategic tool utilization")
    p_c.add_argument("--contextual", action="store_true", help="contextual understanding")
    p_c.add_argument("--json", action="store_true")
    p_c.set_defaults(func=cmd_classify)

    p_d = sub.add_parser("describe", help="Place a system from a free-text description (best-effort)")
    p_d.add_argument("text", help="Free-text system description")
    p_d.add_argument("--name", default="system")
    p_d.add_argument("--json", action="store_true")
    p_d.set_defaults(func=cmd_describe)

    p_b = sub.add_parser("batch", help="Classify a JSON list/{systems:[...]} of systems")
    p_b.add_argument("--systems", default=str(DEFAULT_SYSTEMS))
    p_b.add_argument("--json", action="store_true")
    p_b.set_defaults(func=cmd_batch)

    p_s = sub.add_parser("spectrum", help="Print the spectrum, dimensions, and examples")
    p_s.set_defaults(func=cmd_spectrum)

    p_scn = sub.add_parser("scenario", help="DevOps systems worked example")
    p_scn.add_argument("name")
    p_scn.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
