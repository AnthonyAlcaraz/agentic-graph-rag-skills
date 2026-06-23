#!/usr/bin/env python3
"""investigation-dag-planner CLI."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (
    Task,
    tasks_from_dicts,
    topological_phases,
    build_investigation_dag,
    execute_with_early_termination,
    CycleError,
)

SKILL_MD = HERE / "SKILL.md"


def _skill_description() -> str:
    if not SKILL_MD.exists():
        return "investigation-dag-planner (Ch5)"
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
    return " ".join(d for d in desc if d) or "investigation-dag-planner"


def _load_tasks(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data["tasks"] if isinstance(data, dict) else data
    return tasks_from_dicts(rows)


def cmd_plan(args):
    tasks = _load_tasks(args.tasks_path)
    dag = build_investigation_dag(tasks)
    out = {
        "phases": [asdict(p) for p in dag.phases],
        "parallelism_factor": dag.parallelism_factor,
        "total_estimated_duration_s": dag.total_estimated_duration_s,
        "critical_path_len": dag.critical_path_len,
    }
    print(json.dumps(out, indent=2))


def cmd_phases(args):
    tasks = _load_tasks(args.tasks_path)
    print(json.dumps(topological_phases(tasks), indent=2))


def cmd_scenario(args):
    if args.name != "latency-investigation":
        print(f"unknown scenario: {args.name}", file=sys.stderr)
        sys.exit(1)
    tasks = _load_tasks(HERE / "hypotheses.json")
    dag = build_investigation_dag(tasks)
    print("=" * 70)
    print("DevOps investigation DAG (account 123456789012)")
    print("=" * 70)
    for p in dag.phases:
        kind = "PARALLEL" if len(p.task_ids) > 1 else "single"
        print(f"\nPhase {p.index} [{kind}] est={p.estimated_duration_s}s")
        for tid in p.task_ids:
            print(f"  - {tid}: {tasks[tid].description}")
    print(f"\nparallelism_factor={dag.parallelism_factor}  "
          f"total_est={dag.total_estimated_duration_s}s  "
          f"critical_path={dag.critical_path_len} phases")

    # Simulate execution: h1 (pool exhaustion) confirms in phase 0.
    print("\n--- execution with early termination (h1 confirms) ---")
    def test_fn(task):
        if task.id == "h1_db_pool_exhaustion":
            return True, "pool at 100% utilization, 47 waiting threads"
        return False, "metrics nominal"
    trace = execute_with_early_termination(dag, tasks, test_fn)
    print(json.dumps(trace, indent=2))


def cmd_benchmark(args):
    failures = []

    # Test 1: independent tasks share the first phase
    tasks = tasks_from_dicts([
        {"id": "a", "depends_on": []},
        {"id": "b", "depends_on": []},
        {"id": "c", "depends_on": ["a", "b"]},
    ])
    phases = topological_phases(tasks)
    if set(phases[0]) != {"a", "b"}:
        failures.append(f"a,b should be in first phase, got {phases[0]}")

    # Test 2: dependent task lands strictly after its deps
    if "c" not in phases[1]:
        failures.append(f"c should be in second phase, got {phases}")

    # Test 3: every task appears exactly once
    flat = [t for ph in phases for t in ph]
    if sorted(flat) != ["a", "b", "c"]:
        failures.append(f"task coverage broken: {flat}")

    # Test 4: parallel-phase duration == max of its tasks
    tasks = tasks_from_dicts([
        {"id": "x", "depends_on": [], "duration_s": 8.0},
        {"id": "y", "depends_on": [], "duration_s": 6.0},
    ])
    dag = build_investigation_dag(tasks)
    if dag.phases[0].estimated_duration_s != 8.0:
        failures.append(f"parallel-phase duration should be max(8,6)=8, got {dag.phases[0].estimated_duration_s}")

    # Test 5: total == sum of phase maxima
    tasks = tasks_from_dicts([
        {"id": "x", "depends_on": [], "duration_s": 8.0},
        {"id": "y", "depends_on": [], "duration_s": 6.0},
        {"id": "z", "depends_on": ["x"], "duration_s": 4.0},
    ])
    dag = build_investigation_dag(tasks)
    # phase0 max(8,6)=8 ; phase1 max(4)=4 -> total 12
    if dag.total_estimated_duration_s != 12.0:
        failures.append(f"total should be 8+4=12, got {dag.total_estimated_duration_s}")

    # Test 6: cycle raises CycleError
    try:
        topological_phases(tasks_from_dicts([
            {"id": "a", "depends_on": ["b"]},
            {"id": "b", "depends_on": ["a"]},
        ]))
        failures.append("cycle should raise CycleError")
    except CycleError:
        pass

    # Test 7: unknown dependency raises
    try:
        topological_phases(tasks_from_dicts([{"id": "a", "depends_on": ["ghost"]}]))
        failures.append("unknown dep should raise ValueError")
    except ValueError:
        pass

    # Test 8: within-phase ordering respects priority (higher first)
    tasks = tasks_from_dicts([
        {"id": "low", "depends_on": [], "priority": 0.1},
        {"id": "high", "depends_on": [], "priority": 0.9},
    ])
    phases = topological_phases(tasks)
    if phases[0][0] != "high":
        failures.append(f"higher priority should come first within a phase, got {phases[0]}")

    # Test 9: parallelism_factor counts multi-task phases
    tasks = tasks_from_dicts([
        {"id": "a", "depends_on": []},
        {"id": "b", "depends_on": []},
        {"id": "c", "depends_on": ["a", "b"]},
    ])
    dag = build_investigation_dag(tasks)
    if dag.parallelism_factor != 1:  # only phase 0 has >1 task
        failures.append(f"parallelism_factor should be 1, got {dag.parallelism_factor}")

    # Test 10: early termination skips phases after confirmation
    tasks = _load_scenario_tasks()
    dag = build_investigation_dag(tasks)
    def test_fn(task):
        return (task.id == "h1_db_pool_exhaustion"), "ev"
    trace = execute_with_early_termination(dag, tasks, test_fn)
    if trace["confirmed"] != "h1_db_pool_exhaustion":
        failures.append(f"h1 should be confirmed, got {trace['confirmed']}")
    if trace["phases_skipped"] < 1:
        failures.append(f"early termination should skip >=1 phase, skipped {trace['phases_skipped']}")

    # Test 11: no confirmation runs all phases, skips none
    trace = execute_with_early_termination(dag, tasks, lambda t: (False, "no"))
    if trace["confirmed"] is not None or trace["phases_skipped"] != 0:
        failures.append(f"no confirmation should run all phases: {trace}")

    n = 11
    print("=" * 70)
    print(f"investigation-dag-planner benchmark - {n - len(failures)}/{n} passed")
    print("=" * 70)
    if failures:
        print("FAILURES:")
        for x in failures:
            print(f"  - {x}")
        sys.exit(1)
    print("All gates passed.")
    sys.exit(0)


def _load_scenario_tasks():
    data = json.loads((HERE / "hypotheses.json").read_text(encoding="utf-8"))
    return tasks_from_dicts(data["tasks"])


def main():
    parser = argparse.ArgumentParser(description=_skill_description())
    sub = parser.add_subparsers(dest="cmd")

    p_plan = sub.add_parser("plan", help="Build the investigation DAG from a tasks JSON")
    p_plan.add_argument("--tasks-path", required=True)
    p_plan.set_defaults(func=cmd_plan)

    p_phases = sub.add_parser("phases", help="Print topological phases from a tasks JSON")
    p_phases.add_argument("--tasks-path", required=True)
    p_phases.set_defaults(func=cmd_phases)

    p_scen = sub.add_parser("scenario", help="DevOps latency-investigation scenario")
    p_scen.add_argument("name")
    p_scen.set_defaults(func=cmd_scenario)

    p_bench = sub.add_parser("benchmark", help="Verification gate battery")
    p_bench.set_defaults(func=cmd_benchmark)

    args = parser.parse_args()
    if not getattr(args, "cmd", None):
        print(_skill_description())
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
