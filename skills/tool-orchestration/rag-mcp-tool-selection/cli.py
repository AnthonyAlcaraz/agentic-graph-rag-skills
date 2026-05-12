#!/usr/bin/env python3
"""
rag-mcp-tool-selection — multi-harness CLI wrapper.

Invocations:
    rag-mcp-tool-selection --help
    rag-mcp-tool-selection select "why is the checkout api slow" --top-k 5
    rag-mcp-tool-selection select "..." --json
    rag-mcp-tool-selection benchmark --top-k 5

The CLI mirrors the SKILL.md Process section step by step so any harness that
runs CLI tools (cron, CI, Claude Code, Cursor, Gemini CLI, Windsurf, OpenCode)
gets the same behavior.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lib  # noqa: E402

DEFAULT_REGISTRY = HERE / "sample-aws-tools.json"
SKILL_DESCRIPTION = (
    "Select the top-K tools from a registry for a given query, replacing "
    "MCP's tools/list dump with a RAG-style filter (50-70% prompt-token "
    "reduction). Three-step pipeline: retrieve / validate / format. Use "
    "when the agent has access to 30+ tools and prompt bloat is real."
)


def cmd_select(args: argparse.Namespace) -> int:
    result = lib.select(
        query=args.query,
        registry_path=args.registry,
        top_k=args.top_k,
    )
    if args.json:
        # Drop the full prompts from --json output to keep it parseable
        out = {k: v for k, v in result.items() if not k.endswith("_prompt")}
        print(json.dumps(out, indent=2))
        return 0
    print(f"Query: {result['query']!r}")
    print(f"Registry size: {result['registry_size']} tools")
    print(f"Selected: {len(result['selected'])}")
    print()
    for s in result["selected"]:
        print(f"  [{s['score']:.3f}] {s['name']}")
        print(f"          {s['description']}")
    print()
    print(
        f"Baseline tokens (all {result['registry_size']} tools in prompt): "
        f"{result['baseline_tokens']}"
    )
    print(f"Filtered tokens (only selected):                {result['filtered_tokens']}")
    print(f"Reduction:                                       {result['reduction_pct']}%")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Run a fixed scenario battery and report the token-reduction distribution."""
    scenarios = [
        "why is my checkout api slow",
        "show me 5xx errors in the last hour",
        "which downstream service is slow during the latency spike",
        "audit who changed the production database",
        "find the latest backup in s3",
        "ssh into the host without ssh",
        "page the on-call engineer about the queue backlog",
        "why is this getting access denied",
    ]
    rows = []
    for query in scenarios:
        result = lib.select(query=query, registry_path=args.registry, top_k=args.top_k)
        rows.append(
            {
                "query": query,
                "selected": len(result["selected"]),
                "top": result["selected"][0]["name"] if result["selected"] else None,
                "baseline_tokens": result["baseline_tokens"],
                "filtered_tokens": result["filtered_tokens"],
                "reduction_pct": result["reduction_pct"],
            }
        )
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    print(f"{'reduction':>10}  {'baseline':>9}  {'filtered':>9}  {'top tool':<32}  query")
    print("-" * 100)
    for row in rows:
        print(
            f"{row['reduction_pct']:>9}%  {row['baseline_tokens']:>9}  "
            f"{row['filtered_tokens']:>9}  {(row['top'] or '-'):<32}  {row['query']}"
        )
    avg_reduction = sum(r["reduction_pct"] for r in rows) / len(rows)
    print("-" * 100)
    print(f"Average reduction across {len(rows)} scenarios: {avg_reduction:.1f}%")
    return 0


def cmd_show_prompt(args: argparse.Namespace) -> int:
    """Print the raw filtered prompt that would go to the LLM."""
    result = lib.select(query=args.query, registry_path=args.registry, top_k=args.top_k)
    print(result["filtered_prompt"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rag-mcp-tool-selection",
        description=SKILL_DESCRIPTION,
    )
    parser.add_argument(
        "--registry",
        type=str,
        default=str(DEFAULT_REGISTRY),
        help="Path to the tool registry JSON (default: bundled sample-aws-tools.json)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_select = sub.add_parser(
        "select",
        help="Select top-K tools for a query and report token reduction",
    )
    p_select.add_argument("query", type=str, help="The natural-language user query")
    p_select.add_argument("--top-k", type=int, default=5, help="Max tools to return (default 5)")
    p_select.add_argument("--json", action="store_true", help="Emit JSON output")
    p_select.set_defaults(func=cmd_select)

    p_bench = sub.add_parser(
        "benchmark",
        help="Run the built-in DevOps scenario battery and report token-reduction distribution",
    )
    p_bench.add_argument("--top-k", type=int, default=5)
    p_bench.add_argument("--json", action="store_true")
    p_bench.set_defaults(func=cmd_benchmark)

    p_prompt = sub.add_parser(
        "show-prompt",
        help="Print the filtered prompt that would be sent to the LLM",
    )
    p_prompt.add_argument("query", type=str)
    p_prompt.add_argument("--top-k", type=int, default=5)
    p_prompt.set_defaults(func=cmd_show_prompt)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
