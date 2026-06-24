#!/usr/bin/env python3
"""
memory-consolidation CLI — multi-harness invocation surface.

Per Agentic Graph RAG Ch4 (Consolidation: From Experience to Knowledge,
Example 4-5 + Example 4-13). SKILL.md description is printed on --help.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    Episode,
    ConsolidatedFact,
    cluster_by_topic,
    summarize_cluster,
    consolidate,
    provenance_of,
    precompute_inferences,
    episodes_from_records,
    MIN_CLUSTER_SIZE,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "memory-consolidation (Ch4)"
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
    return " ".join(d for d in desc if d) or "memory-consolidation"


def cmd_consolidate(args):
    with open(args.episodes_path) as f:
        records = json.load(f)
    episodes = episodes_from_records(records)
    facts = consolidate(
        episodes,
        min_cluster_size=args.min_cluster_size,
        threshold=args.threshold,
        knowledge_type=args.knowledge_type,
    )
    print(json.dumps([x.to_dict() for x in facts], indent=2))


def cmd_cluster(args):
    with open(args.episodes_path) as f:
        records = json.load(f)
    episodes = episodes_from_records(records)
    clusters = cluster_by_topic(episodes, threshold=args.threshold)
    out = [[e.id for e in c] for c in clusters]
    print(json.dumps(out, indent=2))


def cmd_scenario(args):
    if args.name != "incident-consolidation":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps Consolidation - cluster repeated incidents into a Pattern")
    print("AWS account 123456789012")
    print("=" * 70)
    raw = [
        {"id": "ep1", "episode_type": "Incident",
         "content": "checkout-api 503 errors after deploy v3.5.0 raised connection pool timeout"},
        {"id": "ep2", "episode_type": "Incident",
         "content": "checkout-api 503 spike following deploy v3.6.1 connection pool exhausted timeout"},
        {"id": "ep3", "episode_type": "Incident",
         "content": "checkout-api 503 errors traced to deploy v3.7.0 connection pool timeout under load"},
        {"id": "ep4", "episode_type": "Deployment",
         "content": "routine deploy of inventory-service v2.1.0 no errors observed"},
        {"id": "ep5", "episode_type": "Conversation",
         "content": "user asked about billing dashboard color scheme preferences"},
    ]
    episodes = episodes_from_records(raw)
    print("\nClusters (single-linkage, threshold=0.25):")
    for i, c in enumerate(cluster_by_topic(episodes)):
        print(f"  cluster {i}: {[e.id for e in c]}")
    facts = consolidate(episodes)
    print(f"\nConsolidated facts (min_cluster_size={MIN_CLUSTER_SIZE}):")
    for fct in facts:
        print(f"  [{fct.knowledge_type}] {fct.summary}")
        print(f"      derived_from (provenance): {fct.derived_from}")
    if facts:
        print("\nProvenance trace for first fact ('how do you know this?'):")
        for ep in provenance_of(facts[0], episodes):
            print(f"  - {ep.id} [{ep.episode_type}]: {ep.content}")
        print("\nSleep-time pre-computed inference (idle-period, not response path):")
        inf = precompute_inferences(
            facts,
            inference_fn=lambda f: ["Risk: future checkout-api deploys may exhaust the connection pool; pre-stage a runbook."],
        )
        print(json.dumps(inf, indent=2))


def cmd_benchmark(args):
    failures = []

    # Test 1: similar episodes cluster together, unrelated ones split out
    raw = [
        {"id": "a1", "content": "checkout api 503 errors after deploy connection pool timeout"},
        {"id": "a2", "content": "checkout api 503 errors after deploy connection pool exhausted"},
        {"id": "a3", "content": "checkout api 503 deploy connection pool timeout under load"},
        {"id": "b1", "content": "user asked about dashboard color preferences"},
    ]
    episodes = episodes_from_records(raw)
    clusters = cluster_by_topic(episodes, threshold=0.25)
    a_cluster = next((c for c in clusters if any(e.id == "a1" for e in c)), [])
    a_ids = {e.id for e in a_cluster}
    if not {"a1", "a2", "a3"}.issubset(a_ids):
        failures.append(f"related incidents should cluster: got {a_ids}")
    if "b1" in a_ids:
        failures.append("unrelated episode b1 should not join the incident cluster")

    # Test 2: clusters below min_cluster_size are skipped
    facts = consolidate(episodes, min_cluster_size=3, threshold=0.25)
    if len(facts) != 1:
        failures.append(f"expected exactly 1 consolidated fact (one cluster >= 3), got {len(facts)}")

    # Test 3: consolidated fact records full provenance
    if facts:
        if sorted(facts[0].derived_from) != ["a1", "a2", "a3"]:
            failures.append(f"provenance should list all 3 sources, got {facts[0].derived_from}")
        if facts[0].confirmations != 3:
            failures.append(f"confirmations should equal cluster size 3, got {facts[0].confirmations}")

    # Test 4: summarize folds in a confirmation count for multi-episode clusters
    summary = summarize_cluster(a_cluster)
    if "confirmed 3 times" not in summary:
        failures.append(f"multi-episode summary should annotate confirmations, got: {summary}")

    # Test 5: single-episode summary has no confirmation annotation
    single = summarize_cluster([episodes_from_records([{"id": "z", "content": "lone fact about widgets"}])[0]])
    if "confirmed" in single:
        failures.append(f"single-episode summary should not annotate confirmations, got: {single}")

    # Test 6: provenance_of round-trips to the source episodes
    if facts:
        sources = provenance_of(facts[0], episodes)
        if {e.id for e in sources} != {"a1", "a2", "a3"}:
            failures.append("provenance_of must return exactly the source episodes")

    # Test 7: dangling provenance raises (corruption detection)
    if facts:
        broken = ConsolidatedFact(id="x", summary="s", derived_from=["a1", "ghost"])
        try:
            provenance_of(broken, episodes)
            failures.append("dangling provenance should raise ValueError")
        except ValueError:
            pass

    # Test 8: empty input produces no facts
    if consolidate(episodes_from_records([])) != []:
        failures.append("empty episodes should yield no consolidated facts")

    # Test 9: clustering is deterministic across runs
    c1 = [[e.id for e in c] for c in cluster_by_topic(episodes, threshold=0.25)]
    c2 = [[e.id for e in c] for c in cluster_by_topic(episodes, threshold=0.25)]
    if c1 != c2:
        failures.append("clustering must be deterministic")

    # Test 10: sleep-time precompute attaches inferences without touching facts
    if facts:
        inf = precompute_inferences(facts, inference_fn=lambda f: ["at-risk: X"])
        if set(inf.keys()) != {f.id for f in facts} or inf[facts[0].id] != ["at-risk: X"]:
            failures.append("precompute_inferences should key by fact id")

    print("=" * 70)
    print(f"memory-consolidation benchmark - {10 - len(failures)}/10 passed")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for x in failures:
            print(f"  - {x}")
        sys.exit(1)
    print("All gates passed.")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description=_skill_description(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_con = sub.add_parser("consolidate", help="Run full consolidation pass over episodes JSON")
    p_con.add_argument("--episodes-path", required=True)
    p_con.add_argument("--min-cluster-size", type=int, default=MIN_CLUSTER_SIZE)
    p_con.add_argument("--threshold", type=float, default=0.25)
    p_con.add_argument("--knowledge-type", default="Pattern")
    p_con.set_defaults(func=cmd_consolidate)

    p_clu = sub.add_parser("cluster", help="Cluster episodes by topic (prints cluster id groups)")
    p_clu.add_argument("--episodes-path", required=True)
    p_clu.add_argument("--threshold", type=float, default=0.25)
    p_clu.set_defaults(func=cmd_cluster)

    p_scen = sub.add_parser("scenario", help="DevOps incident-consolidation scenario")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery (must pass)")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
