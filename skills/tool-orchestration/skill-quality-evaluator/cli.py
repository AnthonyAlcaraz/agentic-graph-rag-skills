#!/usr/bin/env python3
"""
skill-quality-evaluator — multi-harness CLI wrapper.

    skill-quality-evaluator --help
    skill-quality-evaluator rate safe-readonly-sql-query
    skill-quality-evaluator retrieve "why is the checkout api slow" --min-quality 0.6 --top-k 3
    skill-quality-evaluator retrieve "..." --json
    skill-quality-evaluator monitor --min-quality 0.6
    skill-quality-evaluator benchmark

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

DEFAULT_CATALOG = HERE / "sample-skills-catalog.json"
SKILL_DESCRIPTION = (
    "Score a skill against SkillNet's five quality dimensions (safety, "
    "completeness, executability, maintainability, cost_awareness), compute a "
    "safety/executability-weighted composite, and gate skill retrieval so the "
    "agent pulls the most-relevant skill that ALSO clears a quality threshold. "
    "Use when a skill library surfaces low-quality or unsafe skills at scale."
)

_MONITOR_QUERIES = [
    "why is the checkout api slow",
    "show me 5xx errors in the last hour",
    "which downstream service is slow",
    "roll back the bad deploy",
    "run a shell command to clean up disk",
    "scrape the latency dashboard",
    "audit who changed the production database",
    "provision a brand new kubernetes cluster from scratch",
]


def cmd_rate(args: argparse.Namespace) -> int:
    catalog = lib.load_catalog(args.catalog)
    skill = next((s for s in catalog if s["name"] == args.name), None)
    if skill is None:
        print(f"No skill named {args.name!r} in {args.catalog}", file=sys.stderr)
        return 2
    q = lib.SkillQuality.from_skill(skill)
    payload = {
        "name": skill["name"],
        "dimensions": {d: getattr(q, d) for d in lib.DIMENSIONS},
        "composite": round(q.composite, 3),
        "hard_gate_ok": q.hard_gate_ok,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print(f"Skill: {payload['name']}")
    for d in lib.DIMENSIONS:
        weight = "x2" if d in ("safety", "executability") else "x1"
        print(f"  {d:<16} {payload['dimensions'][d]:.2f}  ({weight})")
    print(f"  {'composite':<16} {payload['composite']:.3f}")
    print(f"  {'hard_gate_ok':<16} {payload['hard_gate_ok']}"
          "  (safety>0 AND executability>0)")
    return 0


def cmd_retrieve(args: argparse.Namespace) -> int:
    catalog = lib.load_catalog(args.catalog)
    hits = lib.retrieve_quality_gated(
        args.task, catalog, min_quality=args.min_quality, top_k=args.top_k
    )
    if args.json:
        out = [
            {
                "name": h.name,
                "relevance": round(h.relevance, 3),
                "quality": round(h.quality, 3),
                "rank_score": round(h.rank_score, 3),
            }
            for h in hits
        ]
        print(json.dumps(out, indent=2))
        return 0
    print(f"Task: {args.task!r}")
    print(f"min_quality={args.min_quality}  top_k={args.top_k}  catalog={len(catalog)} skills\n")
    if not hits:
        print("(no skill passed both the relevance and quality gates)")
        return 0
    for h in hits:
        print(f"  [rank {h.rank_score:.3f}]  {h.name}")
        print(f"           relevance={h.relevance:.3f}  quality={h.quality:.3f}")
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    catalog = lib.load_catalog(args.catalog)
    report = lib.monitor_gaps(
        catalog, _MONITOR_QUERIES, min_quality=args.min_quality, top_k=args.top_k
    )
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"min_quality={report['min_quality']}  queries={len(report['rows'])}\n")
    print(f"{'event':<22}  {'gated_top':<28}  query")
    print("-" * 92)
    for row in report["rows"]:
        print(f"{row['event']:<22}  {(row['gated_top'] or '-'):<28}  {row['query']}")
    print("-" * 92)
    print(f"no_relevant_skill:    {report['no_relevant_skill']}")
    print(f"low_quality_filtered: {report['low_quality_filtered']}")
    print(f"interpretation: {report['interpretation']}")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    """
    Battery: confirm the gate admits high-quality skills, hard-excludes the
    unsafe skill, and that raising min_quality monotonically shrinks the set.
    """
    catalog = lib.load_catalog(args.catalog)
    thresholds = [0.0, 0.4, 0.6, 0.8]
    task = "why is the checkout api slow during the latency spike"
    rows = []
    prev_count = None
    monotone = True
    for t in thresholds:
        hits = lib.retrieve_quality_gated(task, catalog, min_quality=t, top_k=10)
        count = len(hits)
        if prev_count is not None and count > prev_count:
            monotone = False
        prev_count = count
        rows.append({"min_quality": t, "admitted": count,
                     "top": hits[0].name if hits else None})

    # Hard-gate proof: unsafe-shell-runner (safety=0) must never appear even
    # when it is textually the best match for a shell-cleanup query.
    shell_hits = lib.retrieve_quality_gated(
        "run a shell command to clean up disk", catalog, min_quality=0.0, top_k=10
    )
    unsafe_present = any(h.name == "unsafe-shell-runner" for h in shell_hits)

    if args.json:
        print(json.dumps(
            {"rows": rows, "monotone_shrink": monotone,
             "unsafe_excluded": not unsafe_present}, indent=2))
        return 0
    print(f"Task: {task!r}\n")
    print(f"{'min_quality':>12}  {'admitted':>9}  top skill")
    print("-" * 60)
    for r in rows:
        print(f"{r['min_quality']:>12}  {r['admitted']:>9}  {r['top'] or '-'}")
    print("-" * 60)
    print(f"Monotone shrink as threshold rises: {monotone}")
    print(f"unsafe-shell-runner hard-excluded (safety=0): {not unsafe_present}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill-quality-evaluator", description=SKILL_DESCRIPTION
    )
    parser.add_argument(
        "--catalog",
        type=str,
        default=str(DEFAULT_CATALOG),
        help="Path to the skills catalog JSON (default: bundled sample-skills-catalog.json)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_rate = sub.add_parser("rate", help="Show the five dimensions + composite for one skill")
    p_rate.add_argument("name", type=str, help="Skill name to rate")
    p_rate.add_argument("--json", action="store_true")
    p_rate.set_defaults(func=cmd_rate)

    p_ret = sub.add_parser("retrieve", help="Quality-gated retrieval for a task")
    p_ret.add_argument("task", type=str, help="The natural-language task description")
    p_ret.add_argument("--min-quality", type=float, default=0.6)
    p_ret.add_argument("--top-k", type=int, default=3)
    p_ret.add_argument("--json", action="store_true")
    p_ret.set_defaults(func=cmd_retrieve)

    p_mon = sub.add_parser("monitor", help="Report no-relevant vs low-quality-filtered gap events")
    p_mon.add_argument("--min-quality", type=float, default=0.6)
    p_mon.add_argument("--top-k", type=int, default=3)
    p_mon.add_argument("--json", action="store_true")
    p_mon.set_defaults(func=cmd_monitor)

    p_bench = sub.add_parser("benchmark", help="Threshold sweep + hard-gate proof")
    p_bench.add_argument("--json", action="store_true")
    p_bench.set_defaults(func=cmd_benchmark)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
