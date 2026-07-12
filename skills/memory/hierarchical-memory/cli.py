#!/usr/bin/env python3
"""hierarchical-memory CLI — multi-harness invocation surface.

Per Agentic GraphRAG Ch4 (Letta / MemGPT Approach + Example 4-6 + CPU
Architecture of Agent Memory).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    HierarchicalMemory,
    Fact,
    Interaction,
    default_extract_fn,
    save_memory,
    load_memory,
    DURABILITY_DURABLE,
    DURABILITY_SHORT_LIVED,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "hierarchical-memory primitive (Ch4)"
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
    return " ".join(d for d in desc if d) or "hierarchical-memory primitive (Ch4)."


def cmd_add_fact(args):
    """Load-or-create a memory at --path, add a fact, persist it.

    This is the CLI surface for Process-table Step 3 (`mem.add_fact`). Without
    it, `query` / `diagnostics` (which require a snapshot at --path) are
    unreachable end-to-end from the CLI.
    """
    mem = load_memory(args.path) if Path(args.path).exists() else HierarchicalMemory(core_limit=args.core_limit)
    mem.add_fact(args.content, args.durability)
    save_memory(mem, args.path)
    print(json.dumps({
        "added": args.content,
        "durability": args.durability,
        "core_size": len(mem.core),
        "core_limit": mem.core_limit,
        "archival_size": len(mem.archival),
    }, indent=2))


def cmd_diagnostics(args):
    mem = load_memory(args.path)
    print(json.dumps(mem.diagnostics(), indent=2))


def cmd_query(args):
    mem = load_memory(args.path)
    result = mem.query(args.query, top_k_per_tier=args.top_k)
    print(json.dumps(result, indent=2))


def cmd_scenario(args):
    if args.name != "long-running-incident":
        print(f"unknown scenario: {args.name}; available: long-running-incident", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("DevOps Long-Running Incident Investigation (5 days, core_limit=10)")
    print("=" * 70)
    mem = HierarchicalMemory(core_limit=10)
    # Day 1: durable facts
    durables = [
        ("Production AWS account is 123456789012", DURABILITY_DURABLE),
        ("Primary region is us-east-1", DURABILITY_DURABLE),
        ("On-call rotation: Sarah (primary), Marcus (secondary)", DURABILITY_DURABLE),
        ("Checkout API uses synchronous HTTP to payments service", DURABILITY_DURABLE),
    ]
    for content, dur in durables:
        mem.add_fact(content, dur)
    # Days 2-5: short-lived shell commands + log tails
    short_lived_pool = [
        "Running: aws ec2 describe-instances", "Tail: 2026-03-15T07:59 timeout", "Running: kubectl get pods",
        "Tail: 2026-03-15T08:00 504 gateway", "Running: gh pr view 1234", "Tail: 2026-03-15T08:01 503",
        "Running: terraform plan", "Tail: 2026-03-15T08:02 retry-storm", "Running: aws logs filter-log-events",
        "Tail: 2026-03-15T08:03 circuit-breaker", "Running: psql -c 'SELECT count(*)'",
        "Tail: 2026-03-15T08:04 db-connection-pool full", "Running: redis-cli ping",
        "Tail: 2026-03-15T08:05 latency p99 8200ms", "Running: aws sts get-caller-identity",
        "Tail: 2026-03-15T08:06 oncall-page-fired",
    ]
    for short in short_lived_pool:
        mem.add_fact(short, DURABILITY_SHORT_LIVED)
    # Query: ask about durable facts — should still find them in core
    print("\nQuery: 'production'")
    print(json.dumps(mem.query("production"), indent=2))
    print("\nQuery: 'on-call'")
    print(json.dumps(mem.query("on-call"), indent=2))
    print("\nQuery: 'circuit-breaker' (evicted short-lived fact)")
    print(json.dumps(mem.query("circuit-breaker"), indent=2))
    print("\nDiagnostics:")
    print(json.dumps(mem.diagnostics(), indent=2))


def cmd_benchmark(args):
    failures = []

    # Test 1: core_limit honored across many interactions
    mem = HierarchicalMemory(core_limit=10)
    for i in range(100):
        mem.add_fact(f"fact-{i}", DURABILITY_SHORT_LIVED)
    if len(mem.core) > 10:
        failures.append(f"core_limit violated: {len(mem.core)} > 10")

    # Test 2: evicted facts findable in archival
    mem2 = HierarchicalMemory(core_limit=5)
    for i in range(10):
        mem2.add_fact(f"item-{i}", DURABILITY_SHORT_LIVED)
    if len(mem2.archival) != 5:
        failures.append(f"archival size expected 5, got {len(mem2.archival)}")
    # All evicted facts are flagged was_in_core
    if not all(f.was_in_core for f in mem2.archival):
        failures.append("evicted facts should have was_in_core=True")
    if not all(f.evicted_at is not None for f in mem2.archival):
        failures.append("evicted facts should have evicted_at set")
    if not all(f.eviction_reason for f in mem2.archival):
        failures.append("evicted facts should have non-empty eviction_reason")

    # Test 3: durable facts resist eviction
    mem3 = HierarchicalMemory(core_limit=5)
    durable_contents = [f"durable-{i}" for i in range(5)]
    for c in durable_contents:
        mem3.add_fact(c, DURABILITY_DURABLE)
    # Now flood with short-lived; durable should stay
    for i in range(20):
        mem3.add_fact(f"short-{i}", DURABILITY_SHORT_LIVED)
    durable_in_core = [c for c in durable_contents if c in mem3.core]
    if len(durable_in_core) < 4:  # at least 4/5 should survive
        failures.append(f"durable facts evicted too aggressively: {len(durable_in_core)}/5 survived")

    # Test 4: query returns hits from all three tiers
    mem4 = HierarchicalMemory(core_limit=3)
    mem4.add_fact("production database is postgres", DURABILITY_DURABLE)
    mem4.add_fact("production region is us-east-1", DURABILITY_DURABLE)
    mem4.add_fact("production cluster has 12 nodes", DURABILITY_DURABLE)
    # Add interaction with the word "production"
    mem4.recall.append(Interaction("what is the production deployment?", "checkout-api v3.5.0", datetime.now(timezone.utc)))
    # Force an eviction via overflow
    mem4.add_fact("short fact about production", DURABILITY_SHORT_LIVED)
    result = mem4.query("production")
    if not result["core"]:
        failures.append("query missed core hits for 'production'")
    if not result["recall"]:
        failures.append("query missed recall hits for 'production'")
    if not result["archival"]:
        failures.append("query missed archival hits for 'production' (eviction may not have produced an archive entry)")

    # Test 5: dedup — same fact added twice doesn't double up
    mem5 = HierarchicalMemory(core_limit=5)
    mem5.add_fact("dup-fact", DURABILITY_SHORT_LIVED)
    initial_count = mem5.core["dup-fact"].access_count
    mem5.add_fact("dup-fact", DURABILITY_SHORT_LIVED)
    if mem5.core["dup-fact"].access_count != initial_count + 1:
        failures.append("re-adding existing fact should bump access_count, not duplicate")
    if len(mem5.core) != 1:
        failures.append(f"dedup failed: core has {len(mem5.core)} entries for one unique fact")

    # Test 6: snapshot round-trip
    snap = mem3.snapshot()
    mem3_loaded = HierarchicalMemory.from_snapshot(snap)
    if len(mem3_loaded.core) != len(mem3.core):
        failures.append(f"snapshot core size differs: {len(mem3.core)} -> {len(mem3_loaded.core)}")
    if len(mem3_loaded.archival) != len(mem3.archival):
        failures.append(f"snapshot archival size differs: {len(mem3.archival)} -> {len(mem3_loaded.archival)}")

    # Test 7: diagnostics flag pathological pattern (>50% short-lived in core)
    mem6 = HierarchicalMemory(core_limit=10)
    for i in range(8):
        mem6.add_fact(f"short-{i}", DURABILITY_SHORT_LIVED)
    mem6.add_fact("d1", DURABILITY_DURABLE)
    mem6.add_fact("d2", DURABILITY_DURABLE)
    diag = mem6.diagnostics()
    if not any("short-lived" in w for w in diag["warnings"]):
        failures.append("diagnostics should warn when >50% short-lived in core")

    # Test 8: invalid core_limit rejected
    try:
        HierarchicalMemory(core_limit=0)
        failures.append("core_limit=0 should raise ValueError")
    except ValueError:
        pass
    try:
        HierarchicalMemory(core_limit=-1)
        failures.append("core_limit=-1 should raise ValueError")
    except ValueError:
        pass

    # Test 9: invalid durability rejected
    mem7 = HierarchicalMemory(core_limit=5)
    try:
        mem7.add_fact("test", "permanent")  # not in DURABILITY_TYPES
        failures.append("invalid durability should raise ValueError")
    except ValueError:
        pass

    # Test 10: default_extract_fn picks up durable triggers
    mem8 = HierarchicalMemory(core_limit=10)
    mem8.process_interaction(
        "I'm allergic to peanuts, please remember",
        "Got it — I'll note your peanut allergy.",
        extract_fn=default_extract_fn,
    )
    if not any(f.durability == DURABILITY_DURABLE for f in mem8.core.values()):
        failures.append("default extract_fn should mark 'allergic' fact as DURABLE")

    # Summary
    print("=" * 70)
    print(f"hierarchical-memory benchmark - {10 - len(failures)}/10 passed")
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
    p_add = sub.add_parser("add-fact", help="Add a fact to a memory (creates the snapshot if absent)")
    p_add.add_argument("--path", required=True)
    p_add.add_argument("--content", required=True)
    p_add.add_argument("--durability", default=DURABILITY_SHORT_LIVED,
                       choices=(DURABILITY_DURABLE, DURABILITY_SHORT_LIVED))
    p_add.add_argument("--core-limit", type=int, default=50,
                       help="core_limit used only when creating a new memory")
    p_add.set_defaults(func=cmd_add_fact)
    p_diag = sub.add_parser("diagnostics", help="Print health report")
    p_diag.add_argument("--path", required=True)
    p_diag.set_defaults(func=cmd_diagnostics)
    p_query = sub.add_parser("query", help="Search across all three tiers")
    p_query.add_argument("--path", required=True)
    p_query.add_argument("--query", required=True)
    p_query.add_argument("--top-k", type=int, default=3)
    p_query.set_defaults(func=cmd_query)
    p_scen = sub.add_parser("scenario", help="Run DevOps long-running incident scenario")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)
    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
