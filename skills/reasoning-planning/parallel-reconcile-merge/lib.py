"""
Parallel reconcile-merge (Ch5 — Tree Pipeline + controlled parallelism +
state reducers).

Dispatches independent branches, isolates errors per-branch so one branch's
failure does not cascade or corrupt shared state, then reconciles the surviving
results with a reducer-style merge and decides all-or-nothing vs
partial-coverage completion (Examples 5-7, 5-8, 5-16; "The architecture of
controlled parallelism").

Pure Python, stdlib only. Branches run sequentially here (no threads) because
the architectural primitive is the ISOLATION + RECONCILIATION contract, not
the concurrency mechanism. Each branch is a pure function of its own inputs and
writes to a separate channel; only the merge node combines them.

Production swap: run `branch_fns` concurrently (asyncio / threads / Send API).
The independence requirement and the merge contract below are unchanged.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class BranchResult:
    name: str
    ok: bool
    value: Any = None
    error: Optional[str] = None
    flags: List[str] = field(default_factory=list)   # red flags a branch raises


# -- reducers (Example 5-8: deterministic merge regardless of order) --------

def add_messages(a: List[Any], b: List[Any]) -> List[Any]:
    """Append reducer (operator.add over lists), order-stable."""
    return list(a) + list(b)


REDUCERS: Dict[str, Callable[[Any, Any], Any]] = {
    "add": operator.add,
    "extend": add_messages,
    "union": lambda a, b: sorted(set(a) | set(b)),
    "max": max,
    "min": min,
}


def reduce_field(values: List[Any], reducer: Callable[[Any, Any], Any]) -> Any:
    """Fold a reducer over branch values. Empty -> None."""
    if not values:
        return None
    acc = values[0]
    for v in values[1:]:
        acc = reducer(acc, v)
    return acc


# -- branch execution with per-branch error isolation ----------------------

def execute_branches(
    branch_fns: Dict[str, Callable[[Dict[str, Any]], Any]],
    context: Dict[str, Any],
) -> List[BranchResult]:
    """Run each branch in isolation. An exception in one branch is caught and
    recorded in that branch's own result -- it does not abort siblings or touch
    shared state (Ch5 tree-pipeline error aggregation).
    """
    results: List[BranchResult] = []
    for name, fn in branch_fns.items():
        try:
            value = fn(dict(context))   # branch gets a copy; no shared-state writes
            flags = []
            if isinstance(value, dict):
                flags = list(value.get("flags", []))
            results.append(BranchResult(name=name, ok=True, value=value, flags=flags))
        except Exception as exc:          # isolate: record, do not propagate
            results.append(BranchResult(name=name, ok=False, error=f"{type(exc).__name__}: {exc}"))
    return results


# -- reconciliation / merge -------------------------------------------------

@dataclass
class MergeOutcome:
    completed: bool
    mode: str                          # "all_or_nothing" | "partial_coverage"
    succeeded: List[str]
    failed: List[str]
    flags: List[str]                   # union of all branch flags
    merged_value: Any
    rationale: str


def reconcile(
    results: List[BranchResult],
    mode: str = "partial_coverage",
    min_success: Optional[int] = None,
    merge_reducer: Optional[Callable[[Any, Any], Any]] = None,
) -> MergeOutcome:
    """Reconcile branch results (the merge node).

    mode:
      - "all_or_nothing": completed only if every branch succeeded
      - "partial_coverage": completed if >= min_success branches succeeded
        (default min_success = ceil(n/2)... here: majority, at least 1)

    Any red flag from any branch is surfaced (union). The merge combines
    successful branch values via merge_reducer if provided (else returns a
    name->value dict). One branch's failure never silently drops a flag.
    """
    succeeded = [r.name for r in results if r.ok]
    failed = [r.name for r in results if not r.ok]
    flags = sorted({f for r in results for f in r.flags})

    n = len(results)
    if mode == "all_or_nothing":
        completed = (len(failed) == 0 and n > 0)
        need = n
    elif mode == "partial_coverage":
        if min_success is None:
            min_success = max(1, (n // 2) + (1 if n % 2 else 0))  # majority
        completed = len(succeeded) >= min_success and n > 0
        need = min_success
    else:
        raise ValueError(f"unknown mode: {mode!r}")

    ok_values = [r.value for r in results if r.ok]
    if merge_reducer is not None:
        merged = reduce_field(ok_values, merge_reducer)
    else:
        merged = {r.name: r.value for r in results if r.ok}

    rationale = (f"mode={mode}: {len(succeeded)}/{n} branches succeeded "
                 f"(need {need}); flags={flags or 'none'}")
    return MergeOutcome(
        completed=completed,
        mode=mode,
        succeeded=succeeded,
        failed=failed,
        flags=flags,
        merged_value=merged,
        rationale=rationale,
    )


def run_parallel_window(
    branch_fns: Dict[str, Callable[[Dict[str, Any]], Any]],
    context: Dict[str, Any],
    mode: str = "partial_coverage",
    min_success: Optional[int] = None,
    merge_reducer: Optional[Callable[[Any, Any], Any]] = None,
) -> MergeOutcome:
    """End-to-end controlled-parallelism window: dispatch isolated branches,
    then reconcile. Planning must have verified branch independence upstream.
    """
    results = execute_branches(branch_fns, context)
    return reconcile(results, mode=mode, min_success=min_success, merge_reducer=merge_reducer)
