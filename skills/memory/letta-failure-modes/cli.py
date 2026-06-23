#!/usr/bin/env python3
"""letta-failure-modes CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import MemorySnapshot, diagnose, total_score, format_text, format_json

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "letta-failure-modes diagnostic (Ch4)"
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
    return " ".join(d for d in desc if d) or "letta-failure-modes diagnostic"


def _clean_snapshot() -> MemorySnapshot:
    return MemorySnapshot(
        core_size=8, core_limit=10, core_durable_count=6, core_short_lived_count=2,
        recall_size=42, archival_size=15, archival_durable_count=2,
        node_count=100, edge_count=180, disconnected_components=3, avg_degree=3.6,
        uses_bi_temporal_edges=True, facts_without_created_at=0,
        facts_without_invalidation_reason_when_invalidated=0,
        retrieval_method="hybrid", retrieval_complexity_class="O(log n)",
        has_query_log=True, extract_fn_present=True, size_stress_test_passed=True,
    )


def _broken_snapshot() -> MemorySnapshot:
    return MemorySnapshot(
        core_size=10, core_limit=10, core_durable_count=2, core_short_lived_count=8,
        recall_size=0, archival_size=200, archival_durable_count=15,
        node_count=50, edge_count=10, disconnected_components=30, avg_degree=0.4,
        uses_bi_temporal_edges=False, facts_without_created_at=100,
        facts_without_invalidation_reason_when_invalidated=20,
        retrieval_method="linear-scan", retrieval_complexity_class="O(n)",
        has_query_log=False, extract_fn_present=False, size_stress_test_passed=False,
    )


def cmd_diagnose(args):
    with open(args.snapshot) as f:
        d = json.load(f)
    snap = MemorySnapshot.from_dict(d)
    report = diagnose(snap)
    if args.format == "json":
        print(format_json(report))
    else:
        print(format_text(report))


def cmd_scenario(args):
    if args.name != "broken-vs-clean":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    print("=" * 70)
    print("Broken memory architecture (anti-pattern showcase)")
    print("=" * 70)
    report_broken = diagnose(_broken_snapshot())
    print(format_text(report_broken))
    print()
    print("=" * 70)
    print("Clean memory architecture (Ch4 best-practice composition)")
    print("=" * 70)
    report_clean = diagnose(_clean_snapshot())
    print(format_text(report_clean))


def cmd_benchmark(args):
    failures = []

    # Test 1: all 8 modes present
    report = diagnose(_broken_snapshot())
    if len(report.modes) != 8:
        failures.append(f"expected 8 modes, got {len(report.modes)}")

    # Test 2: broken snapshot triggers at least 6 failure modes (some may be warning)
    triggered = [m for m in report.modes if m.status == "present"]
    if len(triggered) < 6:
        failures.append(f"broken snapshot should trigger >= 6 modes, got {len(triggered)}")

    # Test 3: clean snapshot triggers 0 failure modes
    clean_report = diagnose(_clean_snapshot())
    clean_triggered = [m for m in clean_report.modes if m.status == "present"]
    if len(clean_triggered) > 0:
        failures.append(f"clean snapshot triggered {len(clean_triggered)} modes: {[m.name for m in clean_triggered]}")

    # Test 4: scoring — broken total > clean total
    if total_score(report) <= total_score(clean_report):
        failures.append(f"broken score {total_score(report)} should exceed clean {total_score(clean_report)}")

    # Test 5: severity 0 means ok
    for m in clean_report.modes:
        if m.status == "ok" and m.severity != 0:
            failures.append(f"ok mode {m.name} should have severity 0, got {m.severity}")

    # Test 6: each present mode has non-empty fix
    for m in report.modes:
        if m.status == "present" and not m.fix:
            failures.append(f"present mode {m.name} has empty fix")

    # Test 7: round-trip
    j = format_json(report)
    parsed = json.loads(j)
    if len(parsed["modes"]) != 8:
        failures.append("round-trip lost modes")
    if parsed["total_score"] != total_score(report):
        failures.append(f"round-trip total_score differs")

    # Test 8: unknown snapshot — all modes report 'unknown' not false-positive
    empty = MemorySnapshot()
    empty_report = diagnose(empty)
    unknowns = [m for m in empty_report.modes if m.status == "unknown"]
    if len(unknowns) != 8:
        failures.append(f"empty snapshot should yield 8 unknowns, got {len(unknowns)}")

    # Test 9: silent-overwrite is critical (severity 3) when not using bi-temporal
    silent = next(m for m in report.modes if m.name == "silent-overwrite")
    if silent.status != "present" or silent.severity != 3:
        failures.append(f"silent-overwrite should be present/3 in broken snapshot, got {silent.status}/{silent.severity}")

    # Test 10: in-conversation-misses fires on extract_fn missing
    silent_extract = MemorySnapshot(
        core_size=0, core_limit=10, core_durable_count=0, core_short_lived_count=0,
        recall_size=100, extract_fn_present=False,
    )
    rep = diagnose(silent_extract)
    icm = next(m for m in rep.modes if m.name == "in-conversation-misses")
    if icm.status != "present":
        failures.append(f"in-conversation-misses should fire when extract_fn missing, got {icm.status}")

    print("=" * 70)
    print(f"letta-failure-modes benchmark - {10 - len(failures)}/10 passed")
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
    p_diag = sub.add_parser("diagnose", help="Diagnose a memory snapshot")
    p_diag.add_argument("--snapshot", required=True, help="path to snapshot JSON")
    p_diag.add_argument("--format", choices=["text", "json"], default="text")
    p_diag.set_defaults(func=cmd_diagnose)
    p_scen = sub.add_parser("scenario", help="Run showcase scenario")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)
    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
