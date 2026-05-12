#!/usr/bin/env python3
"""
mcp-gateway-two-meta-tools — multi-harness CLI wrapper.

    mcp-gateway --help
    mcp-gateway search "why is checkout slow"
    mcp-gateway search "why is checkout slow" --role devops
    mcp-gateway execute cloudwatch_logs_insights_query --param logGroupNames=/aws/ecs/checkout-api
    mcp-gateway prompt-budget --registry path/to/tools.json

The gateway exposes exactly two tools to the agent: search and execute.
This CLI mirrors them step-by-step plus a budget-check command that
verifies the constant-prompt-size invariant.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lib  # noqa: E402

SIBLING_REGISTRY = HERE.parent / "rag-mcp-tool-selection" / "sample-aws-tools.json"
SKILL_DESCRIPTION = (
    "Two-meta-tool MCP gateway: search(query) returns ranked tool names, "
    "execute(name, **params) invokes one. Tool descriptions stay outside the "
    "agent's prompt. Use when registry > 30 tools or multi-tenant segmentation matters."
)

ROLE_FILTERS = {
    "devops": lib.example_access_filter_devops,
    "all": None,
}


def _load_gateway(args: argparse.Namespace) -> lib.Gateway:
    access_filter = ROLE_FILTERS.get(args.role)
    return lib.Gateway.from_registry_file(args.registry, access_filter=access_filter)


def cmd_search(args: argparse.Namespace) -> int:
    gw = _load_gateway(args)
    hits = gw.search(args.query, top_k=args.top_k)
    if args.json:
        print(json.dumps(hits, indent=2))
        return 0
    print(f"role={args.role!r}  visible={len(gw._visible())}/{len(gw.registry)} tools")
    if not hits:
        print("(no matches — try a different query or broaden the role)")
        return 0
    for h in hits:
        print(f"  [{h['score']:.3f}] {h['name']}")
    return 0


def cmd_execute(args: argparse.Namespace) -> int:
    gw = _load_gateway(args)
    params = dict(p.split("=", 1) for p in args.params)
    try:
        result = gw.execute(args.tool_name, **params)
    except PermissionError as e:
        print(f"PermissionError: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"tool: {result['tool']}")
        print(f"params: {result['params']}")
        print(f"result: {result['result']}")
    return 0


def cmd_prompt_budget(args: argparse.Namespace) -> int:
    """Verify the constant-prompt invariant: agent_prompt length should not depend on registry size."""
    gw = _load_gateway(args)
    full_len = len(gw.agent_prompt(args.query))
    print(f"Registry size:        {len(gw.registry)} tools")
    print(f"Visible (role={args.role!r}): {len(gw._visible())} tools")
    print(f"Agent prompt chars:   {full_len}")
    print(f"Agent prompt tokens:  ~{int(full_len / 4)}  (rough)")
    print()
    print("Constant-prompt invariant: the agent prompt length should NOT scale")
    print("with the registry. Re-run with a larger registry to verify.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mcp-gateway", description=SKILL_DESCRIPTION)
    parser.add_argument("--registry", type=str, default=str(SIBLING_REGISTRY))
    parser.add_argument(
        "--role",
        type=str,
        default="all",
        choices=list(ROLE_FILTERS.keys()),
        help="Apply a built-in access filter. 'devops' restricts to ops-relevant tools.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="Search the gateway (meta-tool 1)")
    p_search.add_argument("query", type=str)
    p_search.add_argument("--top-k", type=int, default=5)
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

    p_exec = sub.add_parser("execute", help="Execute a tool by name (meta-tool 2)")
    p_exec.add_argument("tool_name", type=str)
    p_exec.add_argument(
        "--param",
        dest="params",
        action="append",
        default=[],
        help="Tool parameter as key=value (repeatable)",
    )
    p_exec.add_argument("--json", action="store_true")
    p_exec.set_defaults(func=cmd_execute)

    p_pb = sub.add_parser("prompt-budget", help="Inspect the constant-prompt invariant")
    p_pb.add_argument("--query", type=str, default="why is the checkout api slow")
    p_pb.set_defaults(func=cmd_prompt_budget)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
