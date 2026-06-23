"""
Investigation DAG planner (Ch5 — Dynamic DAG construction + Constructing the
Investigation DAG).

Given a set of hypotheses/tasks with dependency constraints, compute which can
execute concurrently and in what order, then organize them into topological
phases. Each phase is a parallel group; the estimated duration of a parallel
phase is the MAX duration of its concurrent tests (Example 5-15 + the DevOps
"Constructing the Investigation DAG" section). Detects cycles, which signal a
malformed plan.

Pure Python, stdlib only.

Production swap: `_extract_task_dependencies` here consumes an explicit
dependency map. In production a planning-node LLM call extracts dependencies
from the task description (Example 5-15 `_extract_task_dependencies`). The
phase/parallel logic below is exact, not heuristic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class Task:
    id: str
    description: str = ""
    depends_on: List[str] = field(default_factory=list)
    duration_s: float = 0.0
    priority: float = 0.0          # higher = test earlier within a phase


@dataclass
class Phase:
    index: int
    task_ids: List[str]
    estimated_duration_s: float    # max over concurrent tasks


@dataclass
class InvestigationDAG:
    phases: List[Phase]
    parallelism_factor: int        # number of phases that contain >1 task
    total_estimated_duration_s: float
    critical_path_len: int         # number of phases (longest dependency depth)


class CycleError(ValueError):
    """Raised when the dependency graph is not a DAG."""


def _validate(tasks: Dict[str, Task]) -> None:
    for t in tasks.values():
        for dep in t.depends_on:
            if dep not in tasks:
                raise ValueError(f"task {t.id!r} depends on unknown task {dep!r}")
        if t.id in t.depends_on:
            raise CycleError(f"task {t.id!r} depends on itself")


def topological_phases(tasks: Dict[str, Task]) -> List[List[str]]:
    """Kahn-style level decomposition.

    Each returned level is a set of task ids whose predecessors are all in
    earlier levels -- i.e. they can run concurrently. Raises CycleError if the
    graph contains a cycle (a malformed investigation plan).
    """
    _validate(tasks)
    remaining: Dict[str, Set[str]] = {
        tid: set(t.depends_on) for tid, t in tasks.items()
    }
    phases: List[List[str]] = []
    done: Set[str] = set()

    while remaining:
        ready = [tid for tid, deps in remaining.items() if deps <= done]
        if not ready:
            raise CycleError(
                f"dependency cycle among: {sorted(remaining)}"
            )
        # Order within a phase by priority (desc) then id, for determinism.
        ready.sort(key=lambda tid: (-tasks[tid].priority, tid))
        phases.append(ready)
        done.update(ready)
        for tid in ready:
            del remaining[tid]
    return phases


def build_investigation_dag(tasks: Dict[str, Task]) -> InvestigationDAG:
    """Construct phases and compute the parallel-phase duration model.

    Estimated duration of a parallel phase = max duration of its tests, since
    they run concurrently. Total = sum of phase maxima.
    """
    levels = topological_phases(tasks)
    phases: List[Phase] = []
    total = 0.0
    parallel_phase_count = 0
    for i, level in enumerate(levels):
        dur = max((tasks[tid].duration_s for tid in level), default=0.0)
        if len(level) > 1:
            parallel_phase_count += 1
        phases.append(Phase(index=i, task_ids=level, estimated_duration_s=dur))
        total += dur
    return InvestigationDAG(
        phases=phases,
        parallelism_factor=parallel_phase_count,
        total_estimated_duration_s=round(total, 4),
        critical_path_len=len(levels),
    )


def execute_with_early_termination(
    dag: InvestigationDAG,
    tasks: Dict[str, Task],
    test_fn,
) -> Dict[str, object]:
    """Phase-by-phase execution with early termination.

    `test_fn(task) -> (confirmed: bool, evidence: str)`. As soon as a
    hypothesis is confirmed with sufficient corroborating evidence, stop --
    no need to continue testing alternatives (Ch5 "Execution proceeds phase by
    phase with early termination").

    Returns a trace including which phases were skipped.
    """
    trace = {"phase_results": [], "confirmed": None, "phases_run": 0, "phases_skipped": 0}
    confirmed_id = None
    for phase in dag.phases:
        if confirmed_id is not None:
            trace["phases_skipped"] += 1
            continue
        phase_record = {"phase": phase.index, "tests": []}
        for tid in phase.task_ids:
            ok, evidence = test_fn(tasks[tid])
            phase_record["tests"].append({"task": tid, "confirmed": ok, "evidence": evidence})
            if ok and confirmed_id is None:
                confirmed_id = tid
        trace["phase_results"].append(phase_record)
        trace["phases_run"] += 1
    trace["confirmed"] = confirmed_id
    return trace


def tasks_from_dicts(rows: List[dict]) -> Dict[str, Task]:
    """Build a task map from JSON-shaped rows."""
    tasks: Dict[str, Task] = {}
    for r in rows:
        t = Task(
            id=r["id"],
            description=r.get("description", ""),
            depends_on=list(r.get("depends_on", [])),
            duration_s=float(r.get("duration_s", 0.0)),
            priority=float(r.get("priority", 0.0)),
        )
        tasks[t.id] = t
    return tasks
