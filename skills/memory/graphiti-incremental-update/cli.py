#!/usr/bin/env python3
"""graphiti-incremental-update CLI."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    Graph, add_episode, extract_entities, entity_resolution,
    incremental_update, verify_locality, save_graph, load_graph,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "graphiti-incremental-update primitive (Ch4)"
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
    return " ".join(d for d in desc if d) or "graphiti-incremental-update primitive (Ch4)"


def cmd_add_episode(args):
    g = load_graph(args.graph_path) if Path(args.graph_path).exists() else Graph()
    before = g.snapshot()
    log = add_episode(args.episode, g, episode_id=args.episode_id)
    after = g.snapshot()
    save_graph(g, args.graph_path)
    log["locality"] = verify_locality(before, after)
    print(json.dumps(log, indent=2))


def cmd_scenario(args):
    if args.name != "incident-stream":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps Incident Stream - 20 episodes, locality verification per episode")
    print("=" * 70)
    g = Graph()
    episodes = [
        "person:Sarah(s.chen) opened incident:INC-1042 affecting service:checkout-api in region:us-east-1",
        "person:Marcus joined incident:INC-1042 as secondary on-call",
        "service:checkout-api depends on service:payments and service:inventory",
        "deployment:v3.5.0 of service:checkout-api went live at 22:30 UTC",
        "deployment:v3.5.0 introduced 504 timeouts on service:payments calls",
        "person:Sarah triggered rollback to deployment:v3.4.1 of service:checkout-api",
        "incident:INC-1042 closed by person:Sarah after rollback succeeded",
        "person:Sarah opened incident:INC-1043 for service:inventory in region:us-east-1",
        "incident:INC-1043 traced to deployment:v2.1.0 of service:inventory",
        "team:platform owns service:checkout-api and service:payments",
        "team:fulfillment owns service:inventory",
        "person:Marcus opened incident:INC-1044 for service:payments in region:us-west-2",
        "incident:INC-1044 was a region-specific failover test, not a real outage",
        "person:Sarah(s.chen) approved deployment:v3.6.0 of service:checkout-api",
        "deployment:v3.6.0 fixes the payments-timeout regression from deployment:v3.5.0",
        "service:checkout-api now has region:us-east-1 and region:us-west-2 deployed",
        "team:platform added service:fraud-detection as a dependency for service:checkout-api",
        "incident:INC-1045 opened for service:fraud-detection in region:us-east-1",
        "person:Sarah(s.chen) closed incident:INC-1045",
        "team:platform completed Q1 reliability review covering service:checkout-api and service:payments",
    ]
    for i, ep in enumerate(episodes, 1):
        before = g.snapshot()
        log = add_episode(ep, g, episode_id=f"ep-{i:03d}")
        after = g.snapshot()
        loc = verify_locality(before, after)
        print(f"\nepisode {i:02d}: touched={log['touched_nodes']:2d}, "
              f"changed%={loc['percent_changed']:5.1f}, "
              f"methods={log['resolution_method_counts']}")
    print(f"\n{'=' * 70}")
    print(f"Final graph: {len(g.nodes)} nodes, {len(g.edges)} edges")
    print(f"{'=' * 70}")


def cmd_benchmark(args):
    failures = []

    # Test 1: extract simple episode
    extracted = extract_entities("person:Alice opened incident:INC-1")
    if len(extracted) != 2:
        failures.append(f"extracted count: expected 2, got {len(extracted)}")
    if not any(e.type == "person" and e.name.lower() == "alice" for e in extracted):
        failures.append("did not extract person:Alice")
    if not any(e.type == "incident" and e.name == "INC-1" for e in extracted):
        failures.append("did not extract incident:INC-1")

    # Test 2: entity resolution canonical match (re-encounter same name)
    g = Graph()
    g.add_node("Alice", "person")
    resolved = entity_resolution(extract_entities("person:Alice opened incident:INC-2"), g)
    method = next((r.resolution_method for r in resolved if r.extracted.type == "person"), None)
    if method != "canonical":
        failures.append(f"canonical resolution failed: {method}")

    # Test 3: entity resolution alias
    g2 = Graph()
    g2.add_node("Alice Cooper", "person", aliases=["acooper"])
    resolved = entity_resolution([
        ExtractedEntity(name="acooper", type="person")
    ] if False else extract_entities("person:acooper opened incident:INC-3"), g2)
    method = next((r.resolution_method for r in resolved if r.extracted.type == "person"), None)
    if method != "alias":
        failures.append(f"alias resolution failed: {method}")

    # Test 4: entity resolution fuzzy
    g3 = Graph()
    g3.add_node("Marcus Chen Wang", "person")
    # Construct extracted entity directly to avoid regex limitations
    from lib import ExtractedEntity as EE
    fuzzy_input = [EE(name="Marcus Chen", type="person")]
    resolved = entity_resolution(fuzzy_input, g3)
    method = next((r.resolution_method for r in resolved if r.extracted.type == "person"), None)
    if method != "fuzzy":
        failures.append(f"fuzzy resolution failed: {method}")

    # Test 5: entity resolution new
    g4 = Graph()
    resolved = entity_resolution(extract_entities("person:Bob opened incident:INC-4"), g4)
    method = next((r.resolution_method for r in resolved if r.extracted.type == "person"), None)
    if method != "new":
        failures.append(f"new resolution failed: {method}")

    # Test 6: locality invariant — touched_nodes independent of graph size
    g_small = Graph()
    for i in range(5):
        g_small.add_node(f"existing-{i}", "service")
    log_small = add_episode("person:Eve opened incident:INC-5", g_small)
    g_big = Graph()
    for i in range(500):
        g_big.add_node(f"existing-{i}", "service")
    log_big = add_episode("person:Eve opened incident:INC-5", g_big)
    if log_small["touched_nodes"] != log_big["touched_nodes"]:
        failures.append(
            f"locality violated: small touched={log_small['touched_nodes']}, "
            f"big touched={log_big['touched_nodes']}"
        )

    # Test 7: locality % changed is small for mature-graph add
    g_mature = Graph()
    for i in range(100):
        g_mature.add_node(f"existing-{i}", "service")
    before = g_mature.snapshot()
    add_episode("person:Alice opened incident:INC-6", g_mature)
    after = g_mature.snapshot()
    loc = verify_locality(before, after)
    if loc["percent_changed"] > 10.0:
        failures.append(f"locality % changed too high: {loc['percent_changed']:.1f}%")

    # Test 8: round-trip
    snap = g_mature.snapshot()
    g_loaded = Graph.from_snapshot(snap)
    if len(g_loaded.nodes) != len(g_mature.nodes):
        failures.append(f"round-trip nodes count differs: {len(g_mature.nodes)} -> {len(g_loaded.nodes)}")
    if len(g_loaded.edges) != len(g_mature.edges):
        failures.append(f"round-trip edges count differs: {len(g_mature.edges)} -> {len(g_loaded.edges)}")

    # Test 9: dedup across episodes — re-encountering same entity uses canonical
    g_dedup = Graph()
    log1 = add_episode("person:Diana opened incident:INC-7", g_dedup)
    log2 = add_episode("person:Diana joined incident:INC-7", g_dedup)
    if log2["resolution_method_counts"]["canonical"] != 2:
        failures.append(f"second episode should canonical-resolve both entities: {log2['resolution_method_counts']}")

    # Test 10: co-occurrence edges added — at least one per episode-with-≥2-entities
    g_edges = Graph()
    log = add_episode("person:Eve opened incident:INC-8 in region:us-east-1", g_edges)
    if len(g_edges.edges) < 3:  # 3 entities = C(3,2)=3 pairwise edges
        failures.append(f"co-occurrence edges missing: expected >= 3, got {len(g_edges.edges)}")

    print("=" * 70)
    print(f"graphiti-incremental-update benchmark - {10 - len(failures)}/10 passed")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All gates passed.")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description=_skill_description())
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("add-episode", help="Add a new episode to a graph (creates if not exists)")
    p_add.add_argument("--graph-path", required=True)
    p_add.add_argument("--episode", required=True)
    p_add.add_argument("--episode-id", default=None)
    p_add.set_defaults(func=cmd_add_episode)
    p_scen = sub.add_parser("scenario", help="Run DevOps incident-stream scenario")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)
    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
