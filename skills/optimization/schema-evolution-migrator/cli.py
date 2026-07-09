#!/usr/bin/env python3
"""schema-evolution-migrator CLI — migrations, lifecycle, incremental, rollout.

Invocations:
    schema-evolution-migrator --help
    schema-evolution-migrator migration
    schema-evolution-migrator invalidate --service checkout-service --library stripe-python --old 3.2.1 --new 3.3.0
    schema-evolution-migrator ingest
    schema-evolution-migrator growth --resources 200 --interval 5
    schema-evolution-migrator manifest --release 2024-03-18-causal-attribution-v2
    schema-evolution-migrator validate
    schema-evolution-migrator benchmark

Every Process step in SKILL.md maps to a subcommand.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lib  # noqa: E402

SKILL_MD = HERE / "SKILL.md"
DEFAULT_EVENT = HERE / "sample-deployment-event.json"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "schema-evolution-migrator (Ch8 — Production Systems and Maintenance)"
    text = SKILL_MD.read_text(encoding="utf-8")
    desc, in_desc, fm, in_fm = [], False, 0, False
    for line in text.splitlines():
        if line.strip() == "---":
            fm += 1
            in_fm = fm == 1
            if fm == 2:
                break
            continue
        if not in_fm:
            continue
        if line.startswith("description:"):
            in_desc = True
            continue
        if in_desc:
            if line and not line[0].isspace():
                in_desc = False
                continue
            desc.append(line.strip())
    return " ".join(d for d in desc if d) or "schema-evolution-migrator"


def cmd_migration(args):
    m = lib.monitored_by_migration()
    print(f"# {m.version}: {m.description}  (N-1 compatible: {m.n1_compatible})\n")
    print("# --- forward ---")
    print(m.cypher)
    print("\n# --- rollback ---")
    print(m.rollback)


def cmd_invalidate(args):
    print(lib.temporal_invalidate_cypher(args.service, args.library, args.old, args.new))


def cmd_ingest(args):
    event = json.loads(Path(args.event).read_text(encoding="utf-8"))
    stmts = lib.incremental_merge_cypher(event)
    current_libs = [d["name"] for d in event.get("dependencies", [])]
    print(f"# Incremental merge for {event['service']} "
          f"(deps: {', '.join(current_libs)})\n")
    for i, s in enumerate(stmts, 1):
        print(f"# --- statement {i} ---")
        print(s)
        print()


def cmd_growth(args):
    n = lib.snapshot_growth_per_day(args.resources, args.interval)
    print(json.dumps({
        "resources": args.resources,
        "interval_minutes": args.interval,
        "snapshot_nodes_per_day": n,
        "retention_policy": lib.RETENTION_POLICY,
        "note": "Fischer (Ch8): 200 resources @ 5-min = 57,600 nodes/day for one "
                "small cluster. Without lifecycle management the graph becomes "
                "unqueryable within months.",
    }, indent=2))


def cmd_manifest(args):
    print(json.dumps(lib.staged_rollout_manifest(args.release), indent=2))


def cmd_validate(args):
    manifest = (json.loads(Path(args.manifest).read_text())
                if args.manifest else lib.staged_rollout_manifest("release-under-test"))
    print(json.dumps(lib.validate_manifest(manifest), indent=2))


def cmd_benchmark(args):
    failures = []

    # 1: the MONITORED_BY migration is N-1 compatible and has a rollback.
    m = lib.monitored_by_migration()
    if not m.n1_compatible:
        failures.append("V003 must be N-1 compatible")
    if "MONITORED_BY" not in m.cypher or "rollback" not in m.rollback.lower():
        failures.append("V003 migration/rollback malformed")

    # 2: temporal invalidation sets t_invalid, does not delete.
    cy = lib.temporal_invalidate_cypher("checkout-service", "stripe-python", "3.2.1", "3.3.0")
    if "t_invalid = datetime()" not in cy or "DELETE" in cy.upper():
        failures.append("invalidation must SET t_invalid, never DELETE")

    # 3: Fischer growth math — 200 @ 5-min = 57,600/day.
    if lib.snapshot_growth_per_day(200, 5) != 57600:
        failures.append(f"growth math wrong: {lib.snapshot_growth_per_day(200, 5)} != 57600")

    # 4: hub nodes are retained permanently (overpruning-pitfall fix).
    if "permanent" not in lib.RETENTION_POLICY["hub"]:
        failures.append("hub nodes must be retained permanently")

    # 5: incremental merge uses MERGE ON CREATE/ON MATCH and invalidates gone deps.
    event = json.loads(DEFAULT_EVENT.read_text())
    stmts = lib.incremental_merge_cypher(event)
    joined = "\n".join(stmts)
    if "ON CREATE SET" not in joined or "ON MATCH SET" not in joined:
        failures.append("incremental merge must use ON CREATE / ON MATCH")
    if "NOT l.name IN $current_libs" not in joined:
        failures.append("incremental merge must invalidate dependencies no longer present")

    # 6: valid manifest passes validation.
    manifest = lib.staged_rollout_manifest("r1")
    v = lib.validate_manifest(manifest)
    if not v["valid"]:
        failures.append(f"canonical manifest should validate: {v['problems']}")

    # 7: reordered manifest (code before schema) fails validation.
    bad = lib.staged_rollout_manifest("r2")
    bad["phases"][0], bad["phases"][2] = bad["phases"][2], bad["phases"][0]
    if lib.validate_manifest(bad)["valid"]:
        failures.append("a mis-ordered manifest must fail validation")

    # 8: agent-code phase carries canary + promotion criteria.
    ac = next(p for p in manifest["phases"] if p["name"] == "agent_code")
    if ac.get("canary_percent") != 5 or "promotion_criteria" not in ac:
        failures.append("agent_code phase must carry canary 5% + promotion_criteria")

    total = 8
    print("=" * 70)
    print(f"schema-evolution-migrator benchmark — {total - len(failures)}/{total} passed")
    print(f"  Fischer growth: 200 resources @ 5-min = {lib.snapshot_growth_per_day(200, 5)} nodes/day")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All gates passed.")
    sys.exit(0)


def main():
    p = argparse.ArgumentParser(prog="schema-evolution-migrator", description=_skill_description())
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("migration", help="Emit the V003 MONITORED_BY migration + rollback").set_defaults(func=cmd_migration)

    pi = sub.add_parser("invalidate", help="Emit temporal-invalidation Cypher for a dependency change")
    pi.add_argument("--service", default="checkout-service")
    pi.add_argument("--library", default="stripe-python")
    pi.add_argument("--old", default="3.2.1")
    pi.add_argument("--new", default="3.3.0")
    pi.set_defaults(func=cmd_invalidate)

    pg = sub.add_parser("ingest", help="Emit incremental-merge Cypher for a deployment event")
    pg.add_argument("--event", type=Path, default=DEFAULT_EVENT)
    pg.set_defaults(func=cmd_ingest)

    pw = sub.add_parser("growth", help="Estimate snapshot-node growth per day")
    pw.add_argument("--resources", type=int, default=200)
    pw.add_argument("--interval", type=int, default=5)
    pw.set_defaults(func=cmd_growth)

    pm = sub.add_parser("manifest", help="Emit the staged-rollout deployment manifest")
    pm.add_argument("--release", default="2024-03-18-causal-attribution-v2")
    pm.set_defaults(func=cmd_manifest)

    pv = sub.add_parser("validate", help="Validate a staged-rollout manifest")
    pv.add_argument("--manifest", type=Path, default=None)
    pv.set_defaults(func=cmd_validate)

    sub.add_parser("benchmark", help="Verification gate battery").set_defaults(func=cmd_benchmark)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
