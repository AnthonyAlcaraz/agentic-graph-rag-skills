#!/usr/bin/env python3
"""
bi-temporal-edge CLI — multi-harness invocation surface.

Per Agentic GraphRAG Ch4 (Temporal Awareness) + HINDSIGHT (Latimer et al. 2025).
SKILL.md description is printed on --help (so any harness can discover the skill from --help).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    TemporalEdge,
    create_edge,
    invalidate,
    supersede,
    as_of,
    history,
    ingestion_lag,
    weighted_traverse,
    save_edges,
    load_edges,
    DEFAULT_WEIGHTS,
    LINK_TYPES,
)

SKILL_MD = HERE / "SKILL.md"
SAMPLE = HERE / "sample-config-timeline.json"


# ---------------------------------------------------------------------------
# Help — print SKILL.md description block on --help (multi-harness invariant)
# ---------------------------------------------------------------------------

def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "bi-temporal-edge — see SKILL.md (not found)"
    text = SKILL_MD.read_text(encoding="utf-8")
    # extract the description: block from frontmatter
    desc = []
    in_desc = False
    in_frontmatter = False
    fm_count = 0
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
    return " ".join(d for d in desc if d) or "bi-temporal-edge primitive (Ch4)."


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_create(args):
    e = create_edge(
        source=args.source,
        target=args.target,
        relationship=args.relationship,
        value=args.value,
        link_type=args.link_type,
        weight=args.weight,
    )
    print(json.dumps(e.to_dict(), indent=2))


def cmd_as_of(args):
    edges = load_edges(args.edges_path)
    ts = datetime.fromisoformat(args.timestamp)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    try:
        result = as_of(args.source, args.relationship, ts, edges)
    except ValueError as exc:
        # More than one edge valid at ts for (source, rel). For a genuinely
        # single-valued config field this is the corruption the Red Flags
        # section warns about; for a multi-valued relationship (e.g. depends_on
        # with several targets) it is expected — point-in-time on a set needs
        # `history` / `traverse`, not `as-of`. Surface cleanly, never a traceback.
        print(json.dumps({
            "error": "multiple_valid_edges",
            "detail": str(exc),
            "hint": "as-of returns a single value; for multi-valued relationships "
                    "use `history` or `traverse --at-time` to list all valid edges.",
            "queried_at": ts.isoformat(),
        }, indent=2), file=sys.stderr)
        sys.exit(1)
    if result is None:
        print(json.dumps({"valid_edge": None, "queried_at": ts.isoformat()}, indent=2))
        sys.exit(0)
    print(json.dumps({"valid_edge": result.to_dict(), "queried_at": ts.isoformat()}, indent=2))


def cmd_history(args):
    edges = load_edges(args.edges_path)
    h = history(args.node, edges, relationship=args.relationship)
    print(json.dumps([e.to_dict() for e in h], indent=2))


def cmd_lag(args):
    edges = load_edges(args.edges_path)
    rows = []
    for e in edges:
        lag = e.ingestion_lag()
        rows.append({
            "edge_id": e.id,
            "source": e.source,
            "relationship": e.relationship,
            "value": e.value,
            "lag_seconds": lag.total_seconds(),
            "lag_human": str(lag),
        })
    rows.sort(key=lambda r: r["lag_seconds"], reverse=True)
    print(json.dumps(rows, indent=2))


def cmd_traverse(args):
    edges = load_edges(args.edges_path)
    at_time = None
    if args.at_time:
        at_time = datetime.fromisoformat(args.at_time)
        if at_time.tzinfo is None:
            at_time = at_time.replace(tzinfo=timezone.utc)
    result = weighted_traverse(args.start, edges, depth=1, at_time=at_time)
    print(json.dumps(result, indent=2))


def cmd_scenario(args):
    """DevOps incident-reconstruction running example (Ch5/6 anchor)."""
    if args.name != "incident-reconstruction":
        print(f"unknown scenario: {args.name}; available: incident-reconstruction", file=sys.stderr)
        sys.exit(1)
    edges = load_edges(str(SAMPLE))
    outage_ts = datetime.fromisoformat("2026-03-15T08:00:00+00:00")
    print("=" * 70)
    print("DevOps Incident Reconstruction — fictional AWS account 123456789012")
    print(f"Outage timestamp: {outage_ts.isoformat()}")
    print("=" * 70)
    # Q1: what was the EC2 instance type for service-checkout-api at outage time?
    e = as_of("service-checkout-api", "instance_type", outage_ts, edges)
    print(f"\nQ1: EC2 instance_type at outage time")
    print(f"    answer: {e.value if e else 'unknown'}")
    if e:
        print(f"    valid_from={e.valid_from.isoformat()}")
        print(f"    ingestion_lag={e.ingestion_lag()}")
    # Q2: what was the deployment version?
    e = as_of("service-checkout-api", "deployment_version", outage_ts, edges)
    print(f"\nQ2: Deployment version at outage time")
    print(f"    answer: {e.value if e else 'unknown'}")
    # Q3: what was the immediately-preceding change? (5 minutes before)
    preceding = outage_ts - timedelta(minutes=5)
    print(f"\nQ3: What change happened in the 24h before the outage?")
    h_all = history("service-checkout-api", edges)
    window_start = outage_ts - timedelta(hours=24)
    in_window = [x for x in h_all if window_start <= x.valid_from < outage_ts]
    for x in in_window:
        print(f"    [{x.valid_from.isoformat()}] {x.relationship} -> {x.value}"
              + (f" (supersedes {x.metadata.get('supersedes', '?')[:8]}...)"
                 if x.metadata.get("supersedes") else ""))
    # Q4: what is currently true?
    print(f"\nQ4: What is service-checkout-api running now?")
    now_ts = datetime.now(timezone.utc)
    for rel in ("instance_type", "deployment_version", "region"):
        e = as_of("service-checkout-api", rel, now_ts, edges)
        print(f"    {rel}: {e.value if e else 'unknown'}")
    # Q5: full audit trail
    print(f"\nQ5: Full edit history (most recent first):")
    h_all.sort(key=lambda x: x.valid_from, reverse=True)
    for x in h_all:
        valid_until = x.valid_until.isoformat() if x.valid_until else "now"
        reason = f" — {x.invalidation_reason}" if x.invalidation_reason else ""
        print(f"    [{x.valid_from.isoformat()} -> {valid_until}] {x.relationship}={x.value}{reason}")
    print("\n" + "=" * 70)
    print("Reconstruction complete. Bi-temporal edges answered all 5 audit questions.")
    print("=" * 70)


def cmd_benchmark(args):
    """Verification gate battery — must pass before shipping."""
    failures = []

    # Test 1: create-then-was_valid_at
    e = create_edge("a", "b", "rel", value="v1")
    now = datetime.now(timezone.utc)
    if not e.was_valid_at(now):
        failures.append("create_edge produced an edge invalid at creation time")
    if not e.is_currently_valid():
        failures.append("freshly-created edge reports not currently valid")

    # Test 2: invalidate-then-was_valid_at
    invalidate(e, "test invalidation")
    after = datetime.now(timezone.utc) + timedelta(seconds=1)
    if e.was_valid_at(after):
        failures.append("invalidated edge still valid after invalidation time")
    if e.invalidation_reason != "test invalidation":
        failures.append("invalidation reason not preserved")

    # Test 3: invalidate-twice rejected
    try:
        invalidate(e, "second attempt")
        failures.append("double-invalidation should have raised ValueError")
    except ValueError:
        pass

    # Test 4: empty reason rejected
    e2 = create_edge("a", "b", "rel", value="v2")
    try:
        invalidate(e2, "")
        failures.append("empty invalidation reason should have raised ValueError")
    except ValueError:
        pass
    try:
        invalidate(e2, "   ")
        failures.append("whitespace-only invalidation reason should have raised ValueError")
    except ValueError:
        pass

    # Test 5: supersede produces correct history
    edges = []
    e3 = create_edge("svc", "config", "instance_type", value="t3.medium")
    edges.append(e3)
    time.sleep(0.01)  # ensure timestamp diverges
    e4 = supersede(e3, "t3.large", reason="scaling up", edges=edges)
    time.sleep(0.01)
    e5 = supersede(e4, "m5.xlarge", reason="next-gen", edges=edges)
    h = history("svc", edges)
    if len(h) != 3:
        failures.append(f"history length expected 3, got {len(h)}")
    if h[0].value != "t3.medium" or h[-1].value != "m5.xlarge":
        failures.append("history not in chronological order")

    # Test 6: as_of at intermediate point returns the middle edge
    mid_ts = e4.valid_from + (e5.valid_from - e4.valid_from) / 2
    middle = as_of("svc", "instance_type", mid_ts, edges)
    if middle is None or middle.value != "t3.large":
        failures.append(f"as_of at mid_ts returned wrong edge: {middle.value if middle else None}")

    # Test 7: as_of returns None before the first edge
    before = e3.valid_from - timedelta(seconds=10)
    if as_of("svc", "instance_type", before, edges) is not None:
        failures.append("as_of before-first should return None")

    # Test 8: ingestion lag is non-negative
    backfill = create_edge(
        "svc", "config", "region", value="us-east-1",
        valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ingested_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    lag = backfill.ingestion_lag()
    if lag.total_seconds() <= 0:
        failures.append(f"backfilled edge should have positive ingestion lag, got {lag}")
    if lag < timedelta(days=58):
        failures.append(f"backfilled lag should be ~59 days, got {lag}")

    # Test 9: weighted_traverse prefers causal over semantic at equal hop
    edges_t = []
    edges_t.append(create_edge("X", "Y", "rel-causal", value=None, link_type="causal"))
    edges_t.append(create_edge("X", "Z", "rel-semantic", value=None, link_type="semantic"))
    neighbors = weighted_traverse("X", edges_t, depth=1)
    if not neighbors or neighbors[0]["link_type"] != "causal":
        failures.append("weighted_traverse should rank causal above semantic at equal hop")

    # Test 10: round-trip serialize / deserialize
    save_edges(edges, str(HERE / "_test_roundtrip.json"))
    loaded = load_edges(str(HERE / "_test_roundtrip.json"))
    if len(loaded) != len(edges):
        failures.append(f"round-trip edge count differs: {len(edges)} -> {len(loaded)}")
    for orig, recovered in zip(edges, loaded):
        if orig.valid_from.isoformat() != recovered.valid_from.isoformat():
            failures.append("round-trip valid_from drift")
            break
        if orig.value != recovered.value:
            failures.append("round-trip value drift")
            break
    os.remove(str(HERE / "_test_roundtrip.json"))

    # Test 11: 1000-edge as_of performance < 10ms.
    # Build a realistic timeline: each of 100 nodes has 10 sequential
    # supersedes — non-overlapping validity windows per (source, rel).
    big_edges = []
    base_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for n in range(100):
        for i in range(10):
            valid_from = base_ts + timedelta(days=n, hours=i)
            valid_until = base_ts + timedelta(days=n, hours=i + 1) if i < 9 else None
            big_edges.append(TemporalEdge(
                source=f"node-{n}",
                target="x",
                relationship="field",
                value=f"v{n}-{i}",
                valid_from=valid_from,
                valid_until=valid_until,
                ingested_at=valid_from,
            ))
    target_ts = base_ts + timedelta(days=50, hours=4, minutes=30)
    t0 = time.perf_counter()
    for _ in range(10):
        as_of("node-50", "field", target_ts, big_edges)
    dt_ms = (time.perf_counter() - t0) / 10 * 1000
    if dt_ms > 10.0:
        failures.append(f"as_of perf: {dt_ms:.2f}ms > 10ms target (1000 edges)")

    # Summary
    print("=" * 70)
    print(f"bi-temporal-edge benchmark — {11 - len(failures)}/11 passed")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print(f"as_of performance (1000 edges): {dt_ms:.2f}ms / query")
    print("All gates passed. Skill is ready for downstream use.")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Argparse wiring
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=_skill_description(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="Create a new bi-temporal edge (prints JSON)")
    p_create.add_argument("--source", required=True)
    p_create.add_argument("--target", required=True)
    p_create.add_argument("--relationship", required=True)
    p_create.add_argument("--value", default=None)
    p_create.add_argument("--link-type", default="entity", choices=LINK_TYPES)
    p_create.add_argument("--weight", type=float, default=1.0)
    p_create.set_defaults(func=cmd_create)

    p_asof = sub.add_parser("as-of", help="Point-in-time query")
    p_asof.add_argument("--edges-path", required=True)
    p_asof.add_argument("--source", required=True)
    p_asof.add_argument("--relationship", required=True)
    p_asof.add_argument("--timestamp", required=True, help="ISO-8601 timestamp")
    p_asof.set_defaults(func=cmd_as_of)

    p_hist = sub.add_parser("history", help="Full evolution of a node's edges")
    p_hist.add_argument("--edges-path", required=True)
    p_hist.add_argument("--node", required=True)
    p_hist.add_argument("--relationship", default=None)
    p_hist.set_defaults(func=cmd_history)

    p_lag = sub.add_parser("lag", help="Ingestion lag for all edges (descending)")
    p_lag.add_argument("--edges-path", required=True)
    p_lag.set_defaults(func=cmd_lag)

    p_trav = sub.add_parser("traverse", help="HINDSIGHT-weighted one-hop traversal")
    p_trav.add_argument("--edges-path", required=True)
    p_trav.add_argument("--start", required=True)
    p_trav.add_argument("--at-time", default=None)
    p_trav.set_defaults(func=cmd_traverse)

    p_scen = sub.add_parser("scenario", help="Run the DevOps incident-reconstruction scenario")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Run verification gate battery (must pass)")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
