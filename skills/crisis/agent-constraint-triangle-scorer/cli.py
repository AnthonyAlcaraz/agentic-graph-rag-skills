#!/usr/bin/env python3
"""agent-constraint-triangle-scorer CLI.

Invocations:
    cli.py --help
    cli.py score --steps 8 --tools 90 --ambiguous --window 200000 --used 178000
    cli.py score ... --json
    cli.py batch --configs sample-agent-configs.json
    cli.py triangle
    cli.py scenario latency-spike
    cli.py benchmark

Every Process step in SKILL.md maps to a subcommand/flag. The CLI mirrors the
skill so any harness that runs CLI tools (cron, CI, Claude Code, Cursor,
Gemini CLI, Windsurf, OpenCode) gets identical behavior.
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
DEFAULT_CONFIGS = HERE / "sample-agent-configs.json"


def _skill_description() -> str:
    """Return the SKILL.md frontmatter description block verbatim."""
    if not SKILL_MD.exists():
        return "agent-constraint-triangle-scorer (Ch1)"
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
    return " ".join(d for d in desc if d) or "agent-constraint-triangle-scorer"


def _config_from_args(args: argparse.Namespace) -> dict:
    return {
        "name": args.name,
        "avg_task_steps": args.steps,
        "tool_count": args.tools,
        "tools_disambiguable": not args.ambiguous,
        "context_window_tokens": args.window,
        "avg_context_tokens_used": args.used,
    }


def _print_report(report: dict) -> None:
    print(f"Overall: {report['overall_band']}  (dominant: {report['dominant_constraint']})")
    print(f"Context fill ratio: {report['context_fill_ratio']}")
    print()
    print(f"{'constraint':<24}{'pressure':>10}  band")
    print("-" * 50)
    for name, p in report["pressures"].items():
        print(f"{name:<24}{p['pressure']:>10}  {p['band']}")
    if report["active_pressure_cycles"]:
        print("\nActive pressure cycles (Ch1 trade-offs):")
        for c in report["active_pressure_cycles"]:
            print(f"  * {c['edge']}")
            print(f"      {c['cascade']}")
    if report["recommendations"]:
        print("\nRecommendations (minimal-but-sufficient):")
        for r in report["recommendations"]:
            print(f"  * {r['constraint']}: {r['action']}")
    print(f"\nPrinciple: {report['principle']}")


def cmd_score(args: argparse.Namespace) -> int:
    report = lib.score(_config_from_args(args))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.configs).read_text(encoding="utf-8"))
    configs = data["configs"] if isinstance(data, dict) else data
    out = lib.score_batch(configs)
    if args.json:
        print(json.dumps(out, indent=2))
        return 0
    print(f"Ranked by peak constraint pressure (most constrained first):")
    print("-" * 60)
    ranked = sorted(
        out["results"],
        key=lambda r: max(p["pressure"] for p in r["pressures"].values()),
        reverse=True,
    )
    for r in ranked:
        peak = max(p["pressure"] for p in r["pressures"].values())
        name = r["config"].get("name", "unnamed")
        print(f"  {name:<28} peak={peak:>5}  {r['overall_band']}")
    return 0


def cmd_triangle(args: argparse.Namespace) -> int:
    print("The Agent Constraint Triangle (Ch1)\n")
    print("Three interconnected constraints:")
    print("  1. complexity_management  — multistep planning; exponential cognitive load")
    print("  2. tool_orchestration     — NL -> structured API; ambiguity is the failure")
    print("  3. context_utilization    — fixed attention budget; context-rot gradient")
    print("\nThree cyclic trade-offs (raising one pushes pressure around the cycle):")
    for name, cyc in lib._PRESSURE_CYCLES.items():
        print(f"  * {cyc['edge']}")
        print(f"      {cyc['cascade']}")
    print(
        "\nPrinciple: the smallest possible set of high-signal tokens that "
        "maximizes\nthe likelihood of the desired outcome."
    )
    return 0


def cmd_scenario(args: argparse.Namespace) -> int:
    if args.name != "latency-spike":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        return 1
    print("=" * 70)
    print("DevOps latency-spike investigation — account 123456789012")
    print("Comparing the bloated-MCP agent against the balanced graph agent")
    print("=" * 70)
    data = json.loads(DEFAULT_CONFIGS.read_text(encoding="utf-8"))
    for cfg in data["configs"]:
        if cfg["name"] in ("bloated-mcp-agent", "balanced-graph-agent"):
            print(f"\n### {cfg['name']} — {cfg['note']}")
            _print_report(lib.score(cfg))
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    failures: list[str] = []

    # 1. More steps => higher complexity pressure (monotonic, exponential).
    if not (lib.score_complexity(3) < lib.score_complexity(10) < lib.score_complexity(20)):
        failures.append("complexity pressure must increase with steps")

    # 2. Ambiguous tool set raises tool pressure above a disambiguable one.
    amb = lib.score_tool_orchestration(30, tools_disambiguable=False)
    clear = lib.score_tool_orchestration(30, tools_disambiguable=True)
    if not amb > clear:
        failures.append(f"ambiguous tools should score higher: amb={amb} clear={clear}")

    # 3. Higher context fill => higher context pressure (rot gradient).
    if not (
        lib.score_context_utilization(200000, 40000)
        < lib.score_context_utilization(200000, 180000)
    ):
        failures.append("context pressure must increase with fill ratio")

    # 4. The bloated-MCP config is OVERCONSTRAINED and fires cycles.
    data = json.loads(DEFAULT_CONFIGS.read_text(encoding="utf-8"))
    by_name = {c["name"]: c for c in data["configs"]}
    bloated = lib.score(by_name["bloated-mcp-agent"])
    if bloated["overall_band"] != "OVERCONSTRAINED":
        failures.append(f"bloated agent should be OVERCONSTRAINED, got {bloated['overall_band']}")
    if not bloated["active_pressure_cycles"]:
        failures.append("bloated agent should fire at least one pressure cycle")

    # 5. The balanced config is BALANCED with no active cycles.
    balanced = lib.score(by_name["balanced-graph-agent"])
    if balanced["overall_band"] != "BALANCED":
        failures.append(f"balanced agent should be BALANCED, got {balanced['overall_band']}")

    # 6. Dominant constraint on the bloated agent is tool_orchestration.
    if bloated["dominant_constraint"] != "tool_orchestration":
        failures.append(
            f"bloated agent dominant should be tool_orchestration, got "
            f"{bloated['dominant_constraint']}"
        )

    # 7. Every active cycle carries a known Ch1 edge.
    for c in bloated["active_pressure_cycles"]:
        if "->" not in c["edge"]:
            failures.append(f"cycle missing edge notation: {c}")

    # 8. batch ranks the most-constrained config first.
    out = lib.score_batch(data["configs"])
    if out["order"][0] != "bloated-mcp-agent":
        failures.append(f"batch should rank bloated-mcp-agent first, got {out['order']}")

    total = 8
    print("=" * 70)
    print(f"agent-constraint-triangle-scorer benchmark - {total - len(failures)}/{total} passed")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All gates passed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-constraint-triangle-scorer", description=_skill_description())
    sub = parser.add_subparsers(dest="command", required=True)

    p_score = sub.add_parser("score", help="Score one agent config against the triangle")
    p_score.add_argument("--name", default="agent", help="A label for the config")
    p_score.add_argument("--steps", type=int, required=True, help="avg reasoning-chain steps per task")
    p_score.add_argument("--tools", type=int, required=True, help="number of tools exposed")
    p_score.add_argument("--ambiguous", action="store_true", help="tool set is NOT cleanly disambiguable")
    p_score.add_argument("--window", type=int, default=200000, help="context window budget (tokens)")
    p_score.add_argument("--used", type=int, required=True, help="avg context tokens used per task")
    p_score.add_argument("--json", action="store_true")
    p_score.set_defaults(func=cmd_score)

    p_batch = sub.add_parser("batch", help="Score a JSON list/{configs:[...]} of agent configs")
    p_batch.add_argument("--configs", default=str(DEFAULT_CONFIGS))
    p_batch.add_argument("--json", action="store_true")
    p_batch.set_defaults(func=cmd_batch)

    p_tri = sub.add_parser("triangle", help="Print the constraint triangle + the three trade-off cycles")
    p_tri.set_defaults(func=cmd_triangle)

    p_scn = sub.add_parser("scenario", help="DevOps latency-spike worked example")
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
