#!/usr/bin/env python3
"""
eight-pillar-readiness-map — multi-harness CLI wrapper.

Invocations:
    eight-pillar-readiness-map --help
    eight-pillar-readiness-map assess --system initial
    eight-pillar-readiness-map assess --system mid --json
    eight-pillar-readiness-map assess --knowledge-representation present --memory partial
    eight-pillar-readiness-map pillars
    eight-pillar-readiness-map benchmark

The CLI mirrors the SKILL.md Process section so any harness that runs CLI tools
(cron, CI, Claude Code, Cursor, Gemini CLI, Windsurf, OpenCode) gets the same
behavior. `--help` prints the SKILL.md description verbatim.
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
        return "eight-pillar-readiness-map (Ch2)"
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
    return " ".join(d for d in desc if d) or "eight-pillar-readiness-map"


def _report_dict(r: lib.ReadinessReport) -> dict:
    return {
        "readiness_pct": r.readiness_pct,
        "statuses": r.statuses,
        "per_pillar": r.per_pillar,
        "dependency_violations": r.dependency_violations,
        "unresolved_flaws": r.unresolved_flaws,
        "next_pillar": r.next_pillar,
        "roadmap": r.roadmap,
    }


def _capabilities_from_args(args: argparse.Namespace) -> dict:
    if args.system:
        data = json.loads(DEFAULT_SYSTEMS.read_text(encoding="utf-8"))
        systems = data["systems"]
        if args.system not in systems:
            raise SystemExit(f"unknown system {args.system!r}; "
                             f"choices: {sorted(systems)}")
        return systems[args.system]
    caps = {}
    for key in lib.PILLAR_ORDER:
        val = getattr(args, key, None)
        if val:
            caps[key] = val
    return caps


def cmd_assess(args: argparse.Namespace) -> int:
    caps = _capabilities_from_args(args)
    report = lib.assess(caps)
    if args.json:
        print(json.dumps(_report_dict(report), indent=2))
        return 0
    print(f"Readiness: {report.readiness_pct}%   next pillar: {report.next_pillar}")
    print("-" * 78)
    for p in report.per_pillar:
        mark = {"present": "[x]", "partial": "[~]", "missing": "[ ]"}[p["status"]]
        solves = ", ".join(p["solves_flaws"])
        print(f"  {mark} {p['order']}. {p['name']:<30}{p['chapter']:<8}solves: {solves}")
    if report.dependency_violations:
        print("\nDEPENDENCY VIOLATIONS (layering broken):")
        for v in report.dependency_violations:
            print(f"  - {v['note']}")
    if report.unresolved_flaws:
        print("\nUNRESOLVED CHAPTER-1 FLAWS:")
        for f in report.unresolved_flaws:
            print(f"  - {f['flaw']} ({f['state']}) — needs "
                  f"{', '.join(f['solving_pillars'])}")
    if report.roadmap:
        print(f"\nRoadmap (build in this order): {' -> '.join(report.roadmap)}")
    return 0


def cmd_pillars(args: argparse.Namespace) -> int:
    rows = []
    for key in lib.PILLAR_ORDER:
        p = lib.PILLARS[key]
        rows.append({
            "order": p.order,
            "pillar": key,
            "name": p.name,
            "chapter": p.chapter,
            "depends_on": list(p.depends_on),
            "production_only": p.production_only,
        })
    print(json.dumps(rows, indent=2))
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    failures: list[str] = []
    data = json.loads(DEFAULT_SYSTEMS.read_text(encoding="utf-8"))
    systems = data["systems"]

    # 1. Eight pillars, layered order intact.
    if len(lib.PILLAR_ORDER) != 8:
        failures.append(f"expected 8 pillars, got {len(lib.PILLAR_ORDER)}")
    if lib.PILLAR_ORDER[0] != "knowledge_representation":
        failures.append("knowledge_representation must be the foundational (order-1) pillar")
    if lib.PILLAR_ORDER[-1] != "optimization":
        failures.append("optimization must be the final pillar")

    # 2. Five flaws mapped; self-evolution + optimization map to no flaw.
    if len(lib.FLAW_TO_PILLARS) != 5:
        failures.append("expected 5 Chapter-1 flaws in the mapping")
    for prod in ("self_evolution", "optimization"):
        if any(prod in ps for ps in lib.FLAW_TO_PILLARS.values()):
            failures.append(f"{prod} should map to production viability, not a flaw")

    # 3. Initial state: partial KR, everything else missing; next = knowledge_representation.
    init = lib.assess(systems["initial"])
    if init.next_pillar != "knowledge_representation":
        failures.append("initial state should recommend knowledge_representation next")
    unresolved = {f["flaw"] for f in init.unresolved_flaws}
    if unresolved != set(lib.FLAW_TO_PILLARS):
        failures.append("initial state should leave all five flaws unsolved")
    if init.dependency_violations:
        failures.append("initial state should have no dependency violations")

    # 4. Mid state: KR..planning present -> relationship_blindness, context_amnesia,
    #    temporal_ignorance, reasoning_paralysis solved; tool_chaos still open.
    mid = lib.assess(systems["mid"])
    mid_unresolved = {f["flaw"] for f in mid.unresolved_flaws}
    for solved in ("relationship_blindness", "context_amnesia", "temporal_ignorance",
                   "reasoning_paralysis"):
        if solved in mid_unresolved:
            failures.append(f"mid state should have solved {solved}")
    if "tool_chaos" not in mid_unresolved:
        failures.append("mid state (tool_orchestration partial) should leave tool_chaos open")
    if mid.next_pillar != "tool_orchestration":
        failures.append("mid state should recommend tool_orchestration next")

    # 5. Violation state: reasoning + self_evolution present while KR/memory missing.
    viol = lib.assess(systems["violation"])
    if not viol.dependency_violations:
        failures.append("violation state must report dependency violations")
    violated = {v["pillar"] for v in viol.dependency_violations}
    if not ({"reasoning", "self_evolution"} <= violated):
        failures.append("violation state should flag reasoning AND self_evolution")

    # 6. Readiness monotonic: initial < mid.
    if not (init.readiness_pct < mid.readiness_pct):
        failures.append("mid readiness should exceed initial readiness")

    # 7. All-present system: 100%, no violations, no unresolved flaws, next None.
    full = lib.assess({k: "present" for k in lib.PILLAR_ORDER})
    if full.readiness_pct != 100.0:
        failures.append(f"all-present should be 100%, got {full.readiness_pct}")
    if full.next_pillar is not None or full.dependency_violations or full.unresolved_flaws:
        failures.append("all-present should have no next pillar / violations / unresolved flaws")

    # 8. Invalid status rejected.
    try:
        lib.assess({"memory": "kinda"})
        failures.append("invalid status should raise ValueError")
    except ValueError:
        pass

    total = 12
    passed = total - len(failures)
    print("=" * 70)
    print(f"eight-pillar-readiness-map benchmark — {passed}/{total} passed")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All gates passed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eight-pillar-readiness-map",
        description=_skill_description(),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_assess = sub.add_parser("assess", help="Map a system across the eight pillars")
    p_assess.add_argument("--system", type=str, default=None,
                          help="Named sample system: initial | mid | violation")
    for key in lib.PILLAR_ORDER:
        p_assess.add_argument(f"--{key.replace('_', '-')}", dest=key,
                              choices=lib.STATUSES, default=None,
                              help=f"status of the {key} pillar")
    p_assess.add_argument("--json", action="store_true")
    p_assess.set_defaults(func=cmd_assess)

    p_pillars = sub.add_parser("pillars", help="Print the eight pillars, order, and dependencies")
    p_pillars.set_defaults(func=cmd_pillars)

    p_bench = sub.add_parser("benchmark", help="Run the readiness-map gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
