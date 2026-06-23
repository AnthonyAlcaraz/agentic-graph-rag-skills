#!/usr/bin/env python3
"""execution-graph CLI."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import ExecutionGraph, ExecutionNode, NODE_TYPES

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "execution-graph primitive (Ch7)"
    text = SKILL_MD.read_text(encoding="utf-8")
    desc = []
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
    return " ".join(d for d in desc if d) or "execution-graph (Ch7)"


def cmd_summary(args):
    with open(args.path) as f:
        snap = json.load(f)
    g = ExecutionGraph.from_snapshot(snap)
    print(json.dumps(g.summary(), indent=2))


def cmd_chain(args):
    with open(args.path) as f:
        snap = json.load(f)
    g = ExecutionGraph.from_snapshot(snap)
    chain = g.causal_chain(args.node_id)
    print(json.dumps([n.to_dict() for n in chain], indent=2))


def cmd_scenario(args):
    if args.name != "incident-trace":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps Incident Investigation - execution graph for one query")
    print("=" * 70)
    g = ExecutionGraph()
    # Root: the orchestrator
    root = g.begin_node("Decision_Point", input_payload={"query": "Why is checkout latency spiking?"})
    g.complete_node(root, output_payload={"decided": "investigate dependencies + recent deploys"},
                    latency_ms=12.3, token_count=350, cost_usd=0.001)
    # Retrieval branch
    retr1 = g.begin_node("Retrieval", input_payload={"q": "recent deploys for checkout-api"}, parent_id=root)
    g.complete_node(retr1, output_payload={"docs": ["deploy-v3.5.0", "deploy-v3.4.1"]},
                    latency_ms=145.2, token_count=0, cost_usd=0.0)
    retr2 = g.begin_node("Retrieval", input_payload={"q": "dependencies of checkout-api"}, parent_id=root)
    g.complete_node(retr2, output_payload={"deps": ["payments", "inventory", "fraud-detection"]},
                    latency_ms=98.7, token_count=0, cost_usd=0.0)
    # Tool calls
    tool1 = g.begin_node("Tool_Invocation",
                         input_payload={"tool": "cloudwatch.GetMetricData", "service": "checkout"},
                         parent_id=retr1)
    g.complete_node(tool1, output_payload={"p99_ms": 8200, "p50_ms": 1100},
                    latency_ms=1240.5, token_count=0, cost_usd=0.0)
    # FAILING tool call (5s timeout)
    tool2 = g.begin_node("Tool_Invocation",
                         input_payload={"tool": "cloudwatch.GetMetricData", "service": "payments"},
                         parent_id=retr2)
    g.fail_node(tool2, error="Timeout: CloudWatch API exceeded 5000ms")
    # LLM reasoning
    llm1 = g.begin_node("LLM_Call",
                        input_payload={"prompt": "Given p99 8200ms and missing payments metrics, hypothesize cause"},
                        parent_id=root)
    g.complete_node(llm1, output_payload={"hypothesis": "payments-service backpressure post-v3.5.0 deploy"},
                    latency_ms=2340.8, token_count=1200, cost_usd=0.018)
    # Decision: confirm or further-investigate
    dec1 = g.begin_node("Decision_Point",
                        input_payload={"hypothesis_confidence": 0.65},
                        parent_id=llm1)
    g.complete_node(dec1, output_payload={"decided": "rollback deploy-v3.5.0; further investigation deferred"},
                    latency_ms=8.2, token_count=180, cost_usd=0.0005)
    print(json.dumps(g.summary(), indent=2))
    print("\nFailed nodes:")
    for n in g.failed():
        print(f"  - node {n.id[:8]} type={n.type} error={n.error}")
        print(f"    causal chain to root:")
        chain = g.causal_chain(n.id)
        for c in chain:
            print(f"      <- node {c.id[:8]} type={c.type}")
    print("\nQuery: tool invocations with latency > 1000ms")
    slow_tools = g.query(lambda n: n.type == "Tool_Invocation"
                                   and n.latency_ms is not None
                                   and n.latency_ms > 1000)
    for n in slow_tools:
        print(f"  - {n.id[:8]} latency={n.latency_ms:.1f}ms input={json.dumps(n.input_payload)[:60]}...")


def cmd_benchmark(args):
    failures = []

    # Test 1: two-phase write preserves structure on simulated crash
    g = ExecutionGraph()
    root = g.begin_node("Decision_Point", input_payload={"q": "test"})
    child = g.begin_node("Tool_Invocation", input_payload={"t": "x"}, parent_id=root)
    # Simulate crash — never call complete_node for child
    if g.nodes[child].is_completed():
        failures.append("crashed node should not be reported as completed")
    if g.nodes[child].parent_id != root:
        failures.append("crashed node lost parent link")
    if child not in [n.id for n in g.incomplete()]:
        failures.append("crashed node not in incomplete() list")

    # Test 2: causal_chain traces from any node to root
    g2 = ExecutionGraph()
    r = g2.begin_node("Decision_Point", parent_id=None)
    g2.complete_node(r, output_payload="ok", latency_ms=1.0)
    c1 = g2.begin_node("Retrieval", parent_id=r)
    g2.complete_node(c1, output_payload="ok", latency_ms=1.0)
    c2 = g2.begin_node("LLM_Call", parent_id=c1)
    g2.complete_node(c2, output_payload="ok", latency_ms=1.0)
    chain = g2.causal_chain(c2)
    if [n.id for n in chain] != [r, c1, c2]:
        failures.append(f"causal_chain order wrong: {[n.id[:8] for n in chain]}")

    # Test 3: parallel siblings share parent
    g3 = ExecutionGraph()
    r = g3.begin_node("Decision_Point")
    g3.complete_node(r, output_payload="ok", latency_ms=1.0)
    s1 = g3.begin_node("Retrieval", parent_id=r)
    s2 = g3.begin_node("Retrieval", parent_id=r)
    g3.complete_node(s1, output_payload="ok", latency_ms=1.0)
    g3.complete_node(s2, output_payload="ok", latency_ms=1.0)
    if g3.nodes[s1].parent_id != r or g3.nodes[s2].parent_id != r:
        failures.append("parallel siblings should share parent")
    if s1 == s2:
        failures.append("parallel siblings should have distinct ids")
    children = g3.children(r)
    if len(children) != 2:
        failures.append(f"expected 2 children of root, got {len(children)}")

    # Test 4: query predicate works
    g4 = ExecutionGraph()
    r = g4.begin_node("Decision_Point")
    g4.complete_node(r, output_payload="ok", latency_ms=1.0)
    t1 = g4.begin_node("Tool_Invocation", parent_id=r)
    g4.complete_node(t1, output_payload="ok", latency_ms=4500.0)  # slow
    t2 = g4.begin_node("Tool_Invocation", parent_id=r)
    g4.complete_node(t2, output_payload="ok", latency_ms=120.0)   # fast
    slow = g4.query(lambda n: n.type == "Tool_Invocation"
                              and n.latency_ms is not None
                              and n.latency_ms > 3000)
    if len(slow) != 1 or slow[0].id != t1:
        failures.append(f"query for slow tools should find 1, got {len(slow)}")

    # Test 5: invalid node_type rejected
    g5 = ExecutionGraph()
    try:
        g5.begin_node("not_a_real_type")
        failures.append("invalid node type should raise")
    except ValueError:
        pass

    # Test 6: complete_node on unknown id raises
    g6 = ExecutionGraph()
    try:
        g6.complete_node("not-a-real-id", output_payload="ok", latency_ms=1.0)
        failures.append("complete_node on unknown id should raise KeyError")
    except KeyError:
        pass

    # Test 7: double-complete rejected
    g7 = ExecutionGraph()
    nid = g7.begin_node("Decision_Point")
    g7.complete_node(nid, output_payload="a", latency_ms=1.0)
    try:
        g7.complete_node(nid, output_payload="b", latency_ms=2.0)
        failures.append("double-complete should raise")
    except ValueError:
        pass

    # Test 8: snapshot round-trip
    g8 = ExecutionGraph()
    r = g8.begin_node("Decision_Point")
    g8.complete_node(r, output_payload={"x": 1}, latency_ms=10.0, token_count=100, cost_usd=0.001)
    f = g8.begin_node("Tool_Invocation", parent_id=r)
    g8.fail_node(f, error="boom")
    snap = g8.snapshot()
    g8b = ExecutionGraph.from_snapshot(snap)
    if g8.summary() != g8b.summary():
        failures.append("snapshot round-trip differs")

    # Test 9: summary metrics sum correctly
    g9 = ExecutionGraph()
    r = g9.begin_node("Decision_Point")
    g9.complete_node(r, output_payload="ok", latency_ms=10.0, token_count=100, cost_usd=0.001)
    c = g9.begin_node("LLM_Call", parent_id=r)
    g9.complete_node(c, output_payload="ok", latency_ms=2000.0, token_count=1200, cost_usd=0.020)
    s = g9.summary()
    if abs(s["total_latency_ms"] - 2010.0) > 0.001:
        failures.append(f"total_latency sum wrong: {s['total_latency_ms']}")
    if s["total_token_count"] != 1300:
        failures.append(f"total_token sum wrong: {s['total_token_count']}")
    if abs(s["total_cost_usd"] - 0.021) > 0.001:
        failures.append(f"total_cost sum wrong: {s['total_cost_usd']}")

    # Test 10: causal_chain raises on broken chain
    g10 = ExecutionGraph()
    # Force a broken chain by manually constructing a node with a bad parent_id
    from lib import ExecutionNode
    from datetime import datetime, timezone
    bad = ExecutionNode(
        id="bad-node", type="Decision_Point",
        started_at=datetime.now(timezone.utc),
        parent_id="ghost-parent",
    )
    g10.nodes["bad-node"] = bad
    try:
        g10.causal_chain("bad-node")
        failures.append("causal_chain on broken parent should raise ValueError")
    except ValueError:
        pass

    print("=" * 70)
    print(f"execution-graph benchmark - {10 - len(failures)}/10 passed")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for x in failures:
            print(f"  - {x}")
        sys.exit(1)
    print("All gates passed.")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description=_skill_description())
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_sum = sub.add_parser("summary", help="Summarize a graph snapshot")
    p_sum.add_argument("--path", required=True)
    p_sum.set_defaults(func=cmd_summary)
    p_chain = sub.add_parser("chain", help="Print causal chain of a node")
    p_chain.add_argument("--path", required=True)
    p_chain.add_argument("--node-id", required=True)
    p_chain.set_defaults(func=cmd_chain)
    p_scen = sub.add_parser("scenario", help="DevOps incident-trace scenario")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)
    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
