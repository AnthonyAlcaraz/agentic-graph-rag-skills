#!/usr/bin/env python3
"""
hierarchical-orchestration-router — multi-harness CLI wrapper.

    hierarchical-orchestration-router --help
    hierarchical-orchestration-router route "why did we lose deals last quarter"
    hierarchical-orchestration-router route "how does inventory affect financial projections"
    hierarchical-orchestration-router domains
    hierarchical-orchestration-router cluster
    hierarchical-orchestration-router failover baidu_ai_search
    hierarchical-orchestration-router orchestrate "why is the checkout api slow" --json
    hierarchical-orchestration-router benchmark

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

DEFAULT_CONFIG = HERE / "sample-orchestration-config.json"
SKILL_DESCRIPTION = (
    "Expose one orchestrator instead of thousands of tools. Routes a query to a "
    "domain orchestrator when domain confidence exceeds 0.8, else orchestrates "
    "cross-domain; and clusters tools by function so an overloaded tool fails "
    "over to a functionally-equivalent alternative from the same cluster."
)


def cmd_route(args: argparse.Namespace) -> int:
    config = lib.load_config(args.config)
    result = lib.route_request(args.query, config["domains"], threshold=args.threshold)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"Query: {args.query!r}")
    if result["routing"] == "domain":
        print(f"  -> DOMAIN: {result['domain']}  (confidence {result['confidence']})")
    else:
        print(f"  -> CROSS-DOMAIN across {result['domains']}  "
              f"(confidence {result['confidence']} < {args.threshold})")
    return 0


def cmd_domains(args: argparse.Namespace) -> int:
    config = lib.load_config(args.config)
    if args.json:
        print(json.dumps(config["domains"], indent=2))
        return 0
    for d in config["domains"]:
        print(f"{d['name']}: {len(d.get('tools', []))} tools")
        print(f"  keywords: {', '.join(d.get('keywords', [])[:8])}...")
    return 0


def cmd_cluster(args: argparse.Namespace) -> int:
    config = lib.load_config(args.config)
    clusters = lib.cluster_tools(config["tools"])
    if args.json:
        print(json.dumps(clusters, indent=2))
        return 0
    print(f"{len(clusters)} functional toolkits (clustered by shared function):\n")
    for c in clusters:
        print(f"  cluster {c['cluster_id']}  shared={c['shared_topics']}")
        print(f"    members: {', '.join(c['members'])}")
    return 0


def cmd_failover(args: argparse.Namespace) -> int:
    config = lib.load_config(args.config)
    try:
        result = lib.failover(config["tools"], args.tool)
    except KeyError as e:
        print(str(e), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"{args.tool} overloaded/failed.")
    if result["alternative"]:
        print(f"  -> failover to {result['alternative']}  "
              f"(cluster {result['cluster_id']}, shared {result['shared_topics']})")
        print(f"     {result['reason']}; adapts parameters: {result['adapts_parameters']}")
    else:
        print(f"  -> NO alternative: {result['reason']}")
    return 0


def cmd_orchestrate(args: argparse.Namespace) -> int:
    config = lib.load_config(args.config)
    result = lib.orchestrate(args.query, config, threshold=args.threshold)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"Query: {args.query!r}")
    r = result["routing"]
    if r["routing"] == "domain":
        print(f"  domain: {r['domain']}  (confidence {r['confidence']})")
        for c in result.get("available_clusters", []):
            print(f"    toolkit {c['cluster_id']} {c['shared_topics']}: {', '.join(c['members'])}")
    else:
        print(f"  cross-domain across {r['domains']}  (confidence {r['confidence']})")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    """
    Prove: single-domain queries route with high confidence, cross-domain
    queries fall below threshold, and failover selects a same-cluster alternative.
    """
    config = lib.load_config(args.config)
    domains = config["domains"]
    single = [
        ("why did we lose deals last quarter", "Sales"),
        ("generate the invoice and check compliance", "Finance"),
        ("why is the checkout api slow during the latency spike", "Operations"),
    ]
    cross = "how does inventory affect financial revenue projections"

    rows = []
    single_ok = True
    for q, expected in single:
        r = lib.route_request(q, domains, threshold=args.threshold)
        ok = r["routing"] == "domain" and r["domain"] == expected
        single_ok = single_ok and ok
        rows.append({"query": q, "routing": r["routing"],
                     "domain": r.get("domain"), "confidence": r["confidence"], "ok": ok})
    cross_r = lib.route_request(cross, domains, threshold=args.threshold)
    cross_ok = cross_r["routing"] == "cross_domain"

    fo = lib.failover(config["tools"], "baidu_ai_search")
    # baidu_ai_search is in the search cluster; alternative must also be a search tool.
    search_names = {"arxiv_mcp_search", "perplexity_search", "openai_websearch"}
    failover_ok = fo["alternative"] in search_names

    if args.json:
        print(json.dumps({
            "single_domain_rows": rows,
            "single_domain_all_ok": single_ok,
            "cross_domain_detected": cross_ok,
            "cross_confidence": cross_r["confidence"],
            "failover_alternative": fo["alternative"],
            "failover_same_cluster": failover_ok,
        }, indent=2))
        return 0
    print("Hierarchical orchestration benchmark\n")
    print(f"{'confidence':>10}  {'routing':<13}  {'domain':<12}  query")
    print("-" * 90)
    for r in rows:
        print(f"{r['confidence']:>10}  {r['routing']:<13}  {(r['domain'] or '-'):<12}  {r['query']}")
    print(f"{cross_r['confidence']:>10}  {cross_r['routing']:<13}  "
          f"{'-':<12}  {cross}")
    print("-" * 90)
    print(f"single-domain routing all correct: {single_ok}")
    print(f"cross-domain query detected (< {args.threshold}): {cross_ok}")
    print(f"failover baidu_ai_search -> {fo['alternative']} (same cluster: {failover_ok})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hierarchical-orchestration-router", description=SKILL_DESCRIPTION
    )
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG))
    parser.add_argument("--threshold", type=float, default=lib.DEFAULT_CONFIDENCE_THRESHOLD,
                        help="Domain-confidence routing threshold (default 0.8)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_route = sub.add_parser("route", help="Route a query to a domain or cross-domain")
    p_route.add_argument("query", type=str)
    p_route.add_argument("--json", action="store_true")
    p_route.set_defaults(func=cmd_route)

    p_dom = sub.add_parser("domains", help="List the domain hierarchy")
    p_dom.add_argument("--json", action="store_true")
    p_dom.set_defaults(func=cmd_domains)

    p_cl = sub.add_parser("cluster", help="Show functional toolkits (clusters)")
    p_cl.add_argument("--json", action="store_true")
    p_cl.set_defaults(func=cmd_cluster)

    p_fo = sub.add_parser("failover", help="Failover an overloaded tool to a cluster peer")
    p_fo.add_argument("tool", type=str)
    p_fo.add_argument("--json", action="store_true")
    p_fo.set_defaults(func=cmd_failover)

    p_or = sub.add_parser("orchestrate", help="Single-entry orchestration (Inversion)")
    p_or.add_argument("query", type=str)
    p_or.add_argument("--json", action="store_true")
    p_or.set_defaults(func=cmd_orchestrate)

    p_b = sub.add_parser("benchmark", help="Prove domain routing + cross-domain + failover")
    p_b.add_argument("--json", action="store_true")
    p_b.set_defaults(func=cmd_benchmark)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
