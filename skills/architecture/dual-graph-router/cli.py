#!/usr/bin/env python3
"""
dual-graph-router - multi-harness CLI wrapper.

Invocations:
    dual-graph-router --help
    dual-graph-router route "why is the checkout api slow"
    dual-graph-router route "..." --json
    dual-graph-router batch --requests sample-requests.json
    dual-graph-router benchmark

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
DEFAULT_REQUESTS = HERE / "sample-requests.json"


def _skill_description() -> str:
    """Extract the frontmatter `description:` block from SKILL.md verbatim."""
    if not SKILL_MD.exists():
        return "dual-graph-router (Ch2)"
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
    return " ".join(d for d in desc if d) or "dual-graph-router"


def _decision_dict(d: lib.RouteDecision) -> dict:
    out = {
        "request": d.request,
        "target": d.target,
        "vertical_score": d.vertical_score,
        "horizontal_score": d.horizontal_score,
        "matched_vertical": d.matched_vertical,
        "matched_horizontal": d.matched_horizontal,
        "rationale": d.rationale,
        "node_hint": d.node_hint,
    }
    meet = lib.explain_meeting_point(d)
    if meet:
        out["meeting_point"] = meet
    return out


def cmd_route(args: argparse.Namespace) -> int:
    d = lib.route(args.request)
    if args.json:
        print(json.dumps(_decision_dict(d), indent=2))
        return 0
    print(f"Request: {d.request!r}")
    print(f"Route:   {d.target.upper()}  "
          f"(vertical={d.vertical_score}, horizontal={d.horizontal_score})")
    if d.matched_vertical:
        print(f"  vertical signals:   {', '.join(d.matched_vertical)}")
    if d.matched_horizontal:
        print(f"  horizontal signals: {', '.join(d.matched_horizontal)}")
    print(f"  rationale: {d.rationale}")
    print(f"  node hint: {d.node_hint}")
    meet = lib.explain_meeting_point(d)
    if meet:
        print("  where the two graphs meet:")
        for k, v in meet.items():
            print(f"    - {k}: {v}")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.requests).read_text(encoding="utf-8"))
    rows = data["requests"] if isinstance(data, dict) else data
    out = []
    for row in rows:
        req = row["request"] if isinstance(row, dict) else row
        d = lib.route(req)
        rec = {"request": req, "target": d.target}
        if isinstance(row, dict) and "expected" in row:
            rec["expected"] = row["expected"]
            rec["match"] = row["expected"] == d.target
        out.append(rec)
    if args.json:
        print(json.dumps(out, indent=2))
        return 0
    print(f"{'route':<12}{'expected':<12}{'ok':<4}request")
    print("-" * 90)
    for rec in out:
        exp = rec.get("expected", "-")
        ok = "" if "match" not in rec else ("ok" if rec["match"] else "XX")
        print(f"{rec['target']:<12}{exp:<12}{ok:<4}{rec['request']}")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Verification gate battery - labeled sample requests must route correctly."""
    failures: list[str] = []
    data = json.loads(DEFAULT_REQUESTS.read_text(encoding="utf-8"))
    rows = data["requests"]
    correct = 0
    for row in rows:
        d = lib.route(row["request"])
        if d.target == row["expected"]:
            correct += 1
        else:
            failures.append(
                f"{row['request'][:52]!r} -> {d.target} (expected {row['expected']})"
            )

    # Invariant checks beyond the labeled set.
    d = lib.route("Diagnose why checkout depends on payments-db and is slow")
    if d.target != "both":
        failures.append("mixed horizontal+vertical request must route to 'both'")
    if not lib.explain_meeting_point(d):
        failures.append("'both' route must produce a meeting-point explanation")
    if lib.explain_meeting_point(lib.route("list the dependencies")):
        failures.append("non-'both' route must NOT produce a meeting-point explanation")
    if lib.route("").target != "unroutable":
        failures.append("empty request must be unroutable")

    total = len(rows) + 4
    passed = correct + 4 - len(failures)
    print("=" * 70)
    print(f"dual-graph-router benchmark - {passed}/{total} passed "
          f"({correct}/{len(rows)} labeled requests)")
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
        prog="dual-graph-router",
        description=_skill_description(),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_route = sub.add_parser("route", help="Route one request to a graph")
    p_route.add_argument("request", type=str, help="The natural-language request")
    p_route.add_argument("--json", action="store_true", help="Emit JSON output")
    p_route.set_defaults(func=cmd_route)

    p_batch = sub.add_parser("batch", help="Route a JSON file of requests")
    p_batch.add_argument("--requests", type=str, default=str(DEFAULT_REQUESTS),
                         help="Path to requests JSON (default: bundled sample)")
    p_batch.add_argument("--json", action="store_true")
    p_batch.set_defaults(func=cmd_batch)

    p_bench = sub.add_parser("benchmark", help="Run the labeled-request gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
