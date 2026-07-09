#!/usr/bin/env python3
"""vector-vs-graph-retrieval-selector CLI.

Invocations:
    cli.py --help
    cli.py recommend --scope global --type activity --multi-hop --temporal
    cli.py recommend --scope local --type data --latency-critical --json
    cli.py rebuttal
    cli.py quadrants
    cli.py batch --workloads sample-query-workloads.json
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
DEFAULT_WORKLOADS = HERE / "sample-query-workloads.json"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "vector-vs-graph-retrieval-selector (Ch1)"
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
    return " ".join(d for d in desc if d) or "vector-vs-graph-retrieval-selector"


def _print_result(r: dict) -> None:
    print(f"{r['name']}: {r['recommendation']}")
    for reason in r["reasons"]:
        print(f"  - {reason}")
    if r.get("benchmarkqed_quadrant"):
        q = r["benchmarkqed_quadrant"]
        print(f"  quadrant [{q['key']}]: {q['description']}")
        print(f"    vector accuracy: {q['vector_accuracy']}")
    if r.get("scale_note"):
        print(f"  scale: {r['scale_note']}")
    if r.get("larger_context_window_rebuttal"):
        print(f"  rebuttal: {r['larger_context_window_rebuttal']}")
    if r.get("graphrag_costs"):
        print("  GraphRAG costs to weigh:")
        for c in r["graphrag_costs"]:
            print(f"    * {c}")


def cmd_recommend(args: argparse.Namespace) -> int:
    r = lib.recommend(
        query_scope=args.scope,
        query_type=args.type,
        multi_hop=args.multi_hop,
        temporal=args.temporal,
        structured_domain=not args.unstructured,
        dataset_scale_pages=args.pages,
        latency_critical=args.latency_critical,
        agentic=args.agentic,
        larger_context_window=args.larger_window,
        name=args.name,
    )
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        _print_result(r)
    return 0


def cmd_rebuttal(args: argparse.Namespace) -> int:
    print("Won't a larger context window solve this? (Ch1)\n")
    print(lib.larger_context_window_rebuttal())
    return 0


def cmd_quadrants(args: argparse.Namespace) -> int:
    print("BenchmarkQED query quadrants (scope x type) and vector-RAG behavior (Ch1)\n")
    for key, q in lib.BENCHMARKQED_QUADRANTS.items():
        print(f"[{key}] {q['description']}")
        print(f"    vector accuracy: {q['vector_accuracy']}")
        print(f"    verdict: {q['verdict']}\n")
    print("Numeric anchors:")
    for v in lib.ANCHORS.values():
        print(f"  - {v}")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.workloads).read_text(encoding="utf-8"))
    workloads = data["workloads"] if isinstance(data, dict) else data
    out = lib.recommend_batch(workloads)
    if args.json:
        print(json.dumps(out, indent=2))
        return 0
    for r in out["results"]:
        _print_result(r)
        print()
    print(f"Tally: {out['tally']}")
    return 0


def cmd_scenario(args: argparse.Namespace) -> int:
    if args.name != "devops":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        return 1
    print("=" * 70)
    print("DevOps retrieval workloads — account 123456789012")
    print("=" * 70)
    data = json.loads(DEFAULT_WORKLOADS.read_text(encoding="utf-8"))
    for w in data["workloads"]:
        print(f"\n### {w['name']} — {w['note']}")
        _print_result(lib.recommend(**{k: v for k, v in w.items() if k != "note"}))
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    failures: list[str] = []

    # 1. DataLocal simple lookup -> VECTOR.
    r = lib.recommend(query_scope="local", query_type="data", latency_critical=True, structured_domain=False)
    if r["recommendation"] != "VECTOR":
        failures.append(f"DataLocal lookup should be VECTOR, got {r['recommendation']}")

    # 2. ActivityGlobal multi-hop in a structured domain -> GRAPH.
    r = lib.recommend(query_scope="global", query_type="activity", multi_hop=True, structured_domain=True)
    if r["recommendation"] != "GRAPH":
        failures.append(f"ActivityGlobal multi-hop should be GRAPH, got {r['recommendation']}")

    # 3. Agentic workload -> HYBRID (book's recommended default).
    r = lib.recommend(query_scope="mixed", agentic=True, multi_hop=True, temporal=True)
    if r["recommendation"] != "HYBRID":
        failures.append(f"agentic workload should be HYBRID, got {r['recommendation']}")

    # 4. Graph-favoring signals but unstructured domain -> HYBRID, not GRAPH.
    r = lib.recommend(query_scope="global", query_type="activity", multi_hop=True, structured_domain=False)
    if r["recommendation"] != "HYBRID":
        failures.append(f"graph-signals + unstructured should be HYBRID, got {r['recommendation']}")

    # 5. Larger-context-window flag attaches the rebuttal.
    r = lib.recommend(query_scope="global", query_type="activity", multi_hop=True, larger_context_window=True)
    if "larger_context_window_rebuttal" not in r:
        failures.append("larger_context_window should attach the rebuttal")
    if "1-million-token" not in r["larger_context_window_rebuttal"]:
        failures.append("rebuttal should cite the 1-million-token BenchmarkQED test")

    # 6. 100k+ pages attaches the EyeLevel scale note.
    r = lib.recommend(query_scope="global", query_type="activity", multi_hop=True, dataset_scale_pages=100000)
    if "scale_note" not in r or "12%" not in r["scale_note"]:
        failures.append("100k pages should attach the EyeLevel 12%-vs-2% scale note")

    # 7. GRAPH / HYBRID recommendations surface GraphRAG costs; VECTOR does not.
    g = lib.recommend(query_scope="global", query_type="activity", multi_hop=True, structured_domain=True)
    v = lib.recommend(query_scope="local", query_type="data", latency_critical=True, structured_domain=False)
    if "graphrag_costs" not in g:
        failures.append("GRAPH recommendation should list GraphRAG costs")
    if "graphrag_costs" in v:
        failures.append("VECTOR recommendation should NOT list GraphRAG costs")

    # 8. The ActivityGlobal quadrant carries the 20-30% vector-accuracy anchor.
    q = lib.BENCHMARKQED_QUADRANTS["activity_global"]
    if "20-30%" not in q["vector_accuracy"]:
        failures.append("activity_global quadrant should carry the 20-30% anchor")

    total = 8
    print("=" * 70)
    print(f"vector-vs-graph-retrieval-selector benchmark - {total - len(failures)}/{total} passed")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("All gates passed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vector-vs-graph-retrieval-selector", description=_skill_description())
    sub = parser.add_subparsers(dest="command", required=True)

    p_r = sub.add_parser("recommend", help="Recommend VECTOR / GRAPH / HYBRID for a query workload")
    p_r.add_argument("--name", default="workload")
    p_r.add_argument("--scope", choices=["local", "global", "mixed"], default="local")
    p_r.add_argument("--type", choices=["data", "activity"], default="data")
    p_r.add_argument("--multi-hop", action="store_true", help="requires traversing relationships across docs")
    p_r.add_argument("--temporal", action="store_true", help="requires awareness of change over time")
    p_r.add_argument("--unstructured", action="store_true", help="open-domain / no known schema")
    p_r.add_argument("--pages", type=int, default=0, help="corpus size in pages (EyeLevel scale anchor)")
    p_r.add_argument("--latency-critical", action="store_true", help="high-query-rate / low-latency path")
    p_r.add_argument("--agentic", action="store_true", help="agent workload (needs local<->global)")
    p_r.add_argument("--larger-window", action="store_true", help="considering 'just use a bigger context window'")
    p_r.add_argument("--json", action="store_true")
    p_r.set_defaults(func=cmd_recommend)

    p_reb = sub.add_parser("rebuttal", help="Print Ch1's larger-context-window rebuttal")
    p_reb.set_defaults(func=cmd_rebuttal)

    p_q = sub.add_parser("quadrants", help="Print the BenchmarkQED quadrants + numeric anchors")
    p_q.set_defaults(func=cmd_quadrants)

    p_b = sub.add_parser("batch", help="Recommend for a JSON list/{workloads:[...]}")
    p_b.add_argument("--workloads", default=str(DEFAULT_WORKLOADS))
    p_b.add_argument("--json", action="store_true")
    p_b.set_defaults(func=cmd_batch)

    p_scn = sub.add_parser("scenario", help="DevOps workloads worked example")
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
