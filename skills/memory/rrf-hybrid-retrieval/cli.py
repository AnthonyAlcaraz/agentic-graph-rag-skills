#!/usr/bin/env python3
"""rrf-hybrid-retrieval CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import rrf_fuse, cross_encoder_rerank, token_budget_filter, hybrid_retrieve, DEFAULT_K

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "rrf-hybrid-retrieval (Ch4)"
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
    return " ".join(d for d in desc if d) or "rrf-hybrid-retrieval"


def cmd_fuse(args):
    with open(args.channels_path) as f:
        channels = json.load(f)
    try:
        fused = rrf_fuse(channels, k=args.k)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        sys.exit(1)
    print(json.dumps([{"doc_id": d, "fusion_score": s} for d, s in fused], indent=2))


def cmd_scenario(args):
    if args.name != "incident-search":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps Incident Search - 4-channel RRF + rerank + budget")
    print("=" * 70)
    # Simulated rankings from 4 channels
    channels = {
        "semantic": ["INC-1043", "INC-1042", "INC-2024-11-23", "INC-1044", "INC-2025-02-14"],
        "keyword":  ["INC-1042", "INC-1043", "INC-1044", "INC-1045"],
        "graph":    ["INC-1042", "deploy-v3.5.0", "service-payments-outage", "INC-1043"],
        "temporal": ["INC-1045", "deploy-v3.5.0", "INC-1044", "INC-1043", "INC-1042"],
    }
    metadata = {
        "INC-1042": "Checkout API 503 errors caused by v3.5.0 deploy timeouts on payments",
        "INC-1043": "Inventory service degradation traced to v2.1.0 deploy",
        "INC-1044": "Payments region-specific failover test",
        "INC-1045": "Fraud-detection service introduced as checkout dependency",
        "INC-2024-11-23": "Historical checkout latency incident from last year",
        "INC-2025-02-14": "Older deploy correlation case study",
        "deploy-v3.5.0": "Deployment v3.5.0 of checkout-api 22:30 UTC",
        "service-payments-outage": "Payments dependency outage entry",
    }
    print("\nFusion (top 8):")
    fused = rrf_fuse(channels)
    for doc_id, score in fused[:8]:
        in_channels = sum(1 for c in channels.values() if doc_id in c)
        print(f"  {score:.5f}  {doc_id:30s} (in {in_channels}/4 channels)")
    print("\nCross-encoder rerank (top 5):")
    reranked = cross_encoder_rerank(
        fused[:8], query="checkout latency caused by recent deploy", metadata=metadata,
    )
    for doc_id, fs, rs in reranked[:5]:
        print(f"  fusion={fs:.5f} rerank={rs:.3f}  {doc_id}")
    print("\nToken-budget filtered (budget=500):")
    final = token_budget_filter(reranked[:5], get_tokens=lambda d: len(metadata.get(d, d)), budget=500)
    print(json.dumps(final, indent=2))


def cmd_benchmark(args):
    failures = []

    # Test 1: RRF formula correctness
    channels = {
        "A": ["doc1", "doc2", "doc3"],
        "B": ["doc1", "doc3", "doc2"],
    }
    fused = rrf_fuse(channels, k=60)
    # doc1: 1/61 + 1/61 = 2/61
    expected = 2.0 / 61.0
    actual = next(s for d, s in fused if d == "doc1")
    if abs(actual - expected) > 1e-9:
        failures.append(f"doc1 score: expected {expected}, got {actual}")

    # Test 2: items in more channels rank higher
    channels = {
        "A": ["common", "A_only", "shared"],
        "B": ["common", "B_only", "shared"],
        "C": ["common", "shared"],
    }
    fused = rrf_fuse(channels)
    fused_order = [d for d, _ in fused]
    if fused_order[0] != "common":
        failures.append(f"item in 3 channels should rank first, got {fused_order[0]}")
    common_score = next(s for d, s in fused if d == "common")
    a_only_score = next(s for d, s in fused if d == "A_only")
    if common_score <= a_only_score:
        failures.append("item in 3 channels should score higher than item in 1")

    # Test 3: missing item contributes 0
    channels = {"A": ["x"], "B": ["y"]}
    fused = rrf_fuse(channels)
    x_score = next(s for d, s in fused if d == "x")
    y_score = next(s for d, s in fused if d == "y")
    if abs(x_score - y_score) > 1e-9:
        failures.append("items in single channels with same rank should have equal scores")

    # Test 4: rank within channel matters
    channels = {"A": ["first", "second", "third"]}
    fused = dict(rrf_fuse(channels))
    if fused["first"] <= fused["second"] or fused["second"] <= fused["third"]:
        failures.append("RRF score should decrease with rank")

    # Test 5: cross_encoder_rerank does not introduce or drop items
    fused = [("a", 0.5), ("b", 0.3), ("c", 0.1)]
    reranked = cross_encoder_rerank(fused, "query", metadata={"a": "alpha query", "b": "beta", "c": "gamma"})
    if len(reranked) != 3:
        failures.append(f"rerank changed item count: {len(reranked)}")
    ids = sorted([r[0] for r in reranked])
    if ids != ["a", "b", "c"]:
        failures.append(f"rerank dropped/added items: {ids}")

    # Test 6: token_budget_filter respects budget
    items = [("a", 0.5, 0.9), ("b", 0.3, 0.7), ("c", 0.1, 0.5)]
    sizes = {"a": 100, "b": 200, "c": 250}
    filtered = token_budget_filter(items, get_tokens=lambda d: sizes[d], budget=300)
    total = sum(x["token_count"] for x in filtered)
    if total > 300:
        failures.append(f"budget violated: {total} > 300")
    if len(filtered) != 2:  # 100 + 200 fits, 250 doesn't
        failures.append(f"expected 2 items under budget, got {len(filtered)}")

    # Test 7: token_budget_filter walks items in order (greedy first-fit, not LP)
    items = [("a", 0.5, 0.9), ("b", 0.3, 0.7)]
    sizes = {"a": 500, "b": 100}
    filtered = token_budget_filter(items, get_tokens=lambda d: sizes[d], budget=400)
    # 'a' is 500, exceeds budget, skip; 'b' fits, take.
    if len(filtered) != 1 or filtered[0]["doc_id"] != "b":
        failures.append(f"greedy filter should skip oversize and take 'b', got {filtered}")

    # Test 8: hybrid_retrieve full pipeline
    metadata = {f"d{i}": f"document {i} contains topic {i % 3}" for i in range(10)}
    def ch_semantic(q): return ["d0", "d1", "d2", "d3", "d4"]
    def ch_keyword(q): return ["d2", "d0", "d5"]
    def ch_graph(q): return ["d0", "d2", "d6"]
    def ch_temporal(q): return ["d7", "d8", "d0", "d2"]
    result = hybrid_retrieve(
        "topic 0",
        {"semantic": ch_semantic, "keyword": ch_keyword, "graph": ch_graph, "temporal": ch_temporal},
        get_tokens=lambda d: 250,
        final_budget=1000,
        metadata=metadata,
    )
    if not result:
        failures.append("hybrid_retrieve returned empty result")
    # d0 + d2 are in all 4 channels → must appear in top
    top_ids = {r["doc_id"] for r in result[:4]}
    if "d0" not in top_ids and "d2" not in top_ids:
        failures.append(f"d0 or d2 expected in top-4 (both in 4 channels), got {top_ids}")
    # Every result has the 4 score fields
    for r in result:
        if "fusion_score" not in r or "rerank_score" not in r or "token_count" not in r:
            failures.append("result item missing required fields")
            break

    # Test 9: k parameter affects sharpness
    channels = {"A": ["a", "b", "c", "d", "e"]}
    fused_k1 = dict(rrf_fuse(channels, k=1))
    fused_k1000 = dict(rrf_fuse(channels, k=1000))
    # With k=1: scores are very different across ranks; with k=1000: scores
    # are very close. Specifically, ratio of top to bottom should be larger
    # at small k.
    ratio_k1 = fused_k1["a"] / fused_k1["e"]
    ratio_k1000 = fused_k1000["a"] / fused_k1000["e"]
    if ratio_k1 <= ratio_k1000:
        failures.append(f"k=1 should produce sharper distribution: ratio_k1={ratio_k1}, ratio_k1000={ratio_k1000}")

    # Test 10: empty channels produce empty result
    fused = rrf_fuse({})
    if fused != []:
        failures.append(f"empty channels should produce empty fusion, got {fused}")

    print("=" * 70)
    print(f"rrf-hybrid-retrieval benchmark - {10 - len(failures)}/10 passed")
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
    p_fuse = sub.add_parser("fuse", help="RRF fuse from channels JSON")
    p_fuse.add_argument("--channels-path", required=True)
    p_fuse.add_argument("--k", type=int, default=DEFAULT_K)
    p_fuse.set_defaults(func=cmd_fuse)
    p_scen = sub.add_parser("scenario", help="DevOps incident-search scenario")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)
    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
