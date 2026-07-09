#!/usr/bin/env python3
"""
harness-node-splitter — multi-harness CLI wrapper.

Invocations:
    harness-node-splitter --help
    harness-node-splitter split --workflow sample-workflow.json
    harness-node-splitter split --workflow sample-workflow.json --json
    harness-node-splitter scope --workflow sample-workflow.json
    harness-node-splitter overlap --a filesystem --b browser_driver network_stack
    harness-node-splitter benchmark

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
DEFAULT_WORKFLOW = HERE / "sample-workflow.json"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "harness-node-splitter (Ch2)"
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
    return " ".join(d for d in desc if d) or "harness-node-splitter"


def _load_ops(path: str) -> list[lib.Operation]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data["operations"] if isinstance(data, dict) else data
    return lib.operations_from_dicts(rows)


def cmd_split(args: argparse.Namespace) -> int:
    ops = _load_ops(args.workflow)
    result = lib.split_nodes(ops, threshold=args.threshold)
    if args.json:
        out = {
            "threshold": result.threshold,
            "operation_count": len(ops),
            "node_count": len(result.nodes),
            "nodes": [lib.node_scope(n) for n in result.nodes],
            "decisions": result.decisions,
        }
        print(json.dumps(out, indent=2))
        return 0
    print(f"{len(ops)} candidate operations -> {len(result.nodes)} nodes "
          f"(overlap threshold {result.threshold})")
    print("-" * 78)
    for n in result.nodes:
        tag = " [MERGED]" if n.is_merged else ""
        print(f"  {n.id:<18}{n.node_type:<12}tools={n.tools}{tag}")
        if n.is_merged:
            print(f"    merged_from: {n.merged_from}")
            print(f"    prompt variants: {n.tasks}")
    return 0


def cmd_scope(args: argparse.Namespace) -> int:
    ops = _load_ops(args.workflow)
    result = lib.split_nodes(ops, threshold=args.threshold)
    print(json.dumps([lib.node_scope(n) for n in result.nodes], indent=2))
    return 0


def cmd_overlap(args: argparse.Namespace) -> int:
    ov = lib.tool_overlap(set(args.a), set(args.b))
    verdict = "merge (prompt variation)" if ov >= args.threshold else "split (distinct role)"
    print(json.dumps({
        "a": sorted(set(args.a)),
        "b": sorted(set(args.b)),
        "overlap": round(ov, 3),
        "threshold": args.threshold,
        "verdict": verdict,
    }, indent=2))
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    failures: list[str] = []
    ops = _load_ops(str(DEFAULT_WORKFLOW))
    result = lib.split_nodes(ops)

    # 1. 9 operations -> 8 nodes (get_cpu merges into get_metrics).
    if len(ops) != 9:
        failures.append(f"expected 9 sample operations, got {len(ops)}")
    if len(result.nodes) != 8:
        failures.append(f"expected 8 nodes after split, got {len(result.nodes)}")

    # 2. Exactly one merged node, and it fuses get_metrics + get_cpu.
    merged = [n for n in result.nodes if n.is_merged]
    if len(merged) != 1:
        failures.append(f"expected exactly 1 merged node, got {len(merged)}")
    elif set(merged[0].merged_from) != {"get_metrics", "get_cpu"}:
        failures.append(f"merge should fuse get_metrics+get_cpu, got {merged[0].merged_from}")
    elif len(merged[0].tasks) != 2:
        failures.append("merged node should carry 2 prompt variants")

    # 3. RedAI scanner vs validator: disjoint tools -> stay split.
    ov_redai = lib.tool_overlap({"filesystem"},
                                {"browser_driver", "ios_simulator", "network_stack", "scripting_runtime"})
    if ov_redai != 0.0:
        failures.append(f"RedAI scanner/validator overlap should be 0.0, got {ov_redai}")
    ids = {n.id for n in result.nodes}
    if not ({"scan_code", "validate_finding"} <= ids):
        failures.append("scan_code and validate_finding must remain separate nodes")

    # 4. Tool-less reasoning nodes classify + analyze stay split.
    if lib.tool_overlap(set(), set()) != 0.0:
        failures.append("two tool-less nodes should overlap 0.0 (role in prompt/position)")
    if not ({"classify", "analyze"} <= ids):
        failures.append("classify and analyze must remain separate reasoning nodes")

    # 5. Identical tool surface -> overlap 1.0 (merge).
    if lib.tool_overlap({"cloudwatch_get_metric_data"}, {"cloudwatch_get_metric_data"}) != 1.0:
        failures.append("identical tool surface should overlap 1.0")

    # 6. audit_operation Tip gate: same-surface op -> merge; new-surface op -> split.
    verdict_merge = lib.audit_operation(
        lib.Operation(id="get_p99", node_type="execution", tools=["cloudwatch_get_metric_data"]),
        result.nodes,
    )
    if verdict_merge["verdict"] != "merge":
        failures.append("same-tool-surface execution op should audit as merge")
    verdict_split = lib.audit_operation(
        lib.Operation(id="page_oncall", node_type="execution", tools=["pagerduty_api"]),
        result.nodes,
    )
    if verdict_split["verdict"] != "split":
        failures.append("distinct-tool-surface op should audit as split")

    # 7. Every node scope exposes its constrained context surfaces.
    for n in result.nodes:
        scope = lib.node_scope(n)
        if "tool_surface" not in scope or "memory_reads" not in scope or "output_schema" not in scope:
            failures.append(f"node {n.id} scope missing a required surface field")
            break

    total = 12
    passed = total - len(failures)
    print("=" * 70)
    print(f"harness-node-splitter benchmark — {passed}/{total} passed")
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
        prog="harness-node-splitter",
        description=_skill_description(),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_split = sub.add_parser("split", help="Split candidate operations into constrained nodes")
    p_split.add_argument("--workflow", type=str, default=str(DEFAULT_WORKFLOW),
                         help="Path to workflow JSON (default: bundled sample)")
    p_split.add_argument("--threshold", type=float, default=lib.DEFAULT_OVERLAP_THRESHOLD,
                         help="Tool-overlap merge threshold (default 0.8)")
    p_split.add_argument("--json", action="store_true")
    p_split.set_defaults(func=cmd_split)

    p_scope = sub.add_parser("scope", help="Emit the per-node constrained context scope")
    p_scope.add_argument("--workflow", type=str, default=str(DEFAULT_WORKFLOW))
    p_scope.add_argument("--threshold", type=float, default=lib.DEFAULT_OVERLAP_THRESHOLD)
    p_scope.set_defaults(func=cmd_scope)

    p_ov = sub.add_parser("overlap", help="Compute tool-surface overlap for two tool lists")
    p_ov.add_argument("--a", nargs="*", default=[], help="Tool names for node A")
    p_ov.add_argument("--b", nargs="*", default=[], help="Tool names for node B")
    p_ov.add_argument("--threshold", type=float, default=lib.DEFAULT_OVERLAP_THRESHOLD)
    p_ov.set_defaults(func=cmd_overlap)

    p_bench = sub.add_parser("benchmark", help="Run the split/merge gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
