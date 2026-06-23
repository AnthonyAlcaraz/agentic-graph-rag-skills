"""
Loop-pipeline router (Ch5 — Loop Pipeline + Error-handling strategies).

The conditional-edge logic that turns a validate node into a self-correcting
loop (Examples 5-6, 5-9). Routes to one of: proceed, refine (bounded retry),
fallback (alternative strategy), or terminate-with-partial — based on
validation result, error severity, and a retry budget. The recursion_limit /
max_retries bound prevents infinite loops.

Pure Python, stdlib only.

Production swap: the validation result + error severity are produced upstream
by a validator node (e.g. PlanValidator, an LLM judge, or a deterministic
schema check). This module is the routing decision that consumes them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Routing outcomes (Examples 5-6, 5-9).
PROCEED = "proceed"                       # validation passed -> execute
REFINE = "refine"                         # correctable + retries left -> loop back
FALLBACK = "fallback_strategy"            # correctable + retries exhausted -> alt planner
TERMINATE_PARTIAL = "terminate_with_partial"  # fundamental error -> stop with partial result

DEFAULT_MAX_RETRIES = 3   # Example 5-6 uses retry_count < 3
SEVERITY_CORRECTABLE = "correctable"
SEVERITY_FUNDAMENTAL = "fundamental"


@dataclass
class ValidationError:
    severity: str            # SEVERITY_CORRECTABLE or SEVERITY_FUNDAMENTAL
    message: str = ""


@dataclass
class RouteResult:
    decision: str
    retry_count: int
    rationale: str


def route_after_validation(
    is_valid: bool,
    error: Optional[ValidationError],
    retry_count: int,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> RouteResult:
    """Loop-pipeline routing (Examples 5-6 + 5-9 unified).

    Decision table:
      - valid                                  -> proceed
      - correctable + retries remaining        -> refine (loop back)
      - correctable + retries exhausted        -> fallback_strategy
      - fundamental (any retries)              -> terminate_with_partial

    The retry budget is the explicit bound that prevents infinite loops
    (the chapter's recursion_limit). A missing error on an invalid result is
    treated as a fundamental defect, not silently retried.
    """
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")
    if retry_count < 0:
        raise ValueError("retry_count must be >= 0")

    if is_valid:
        return RouteResult(PROCEED, retry_count, "validation passed")

    if error is None:
        # Invalid but no diagnostic: cannot safely refine; stop with partial.
        return RouteResult(
            TERMINATE_PARTIAL, retry_count,
            "invalid result with no error diagnostic -> cannot refine safely"
        )

    if error.severity == SEVERITY_FUNDAMENTAL:
        return RouteResult(
            TERMINATE_PARTIAL, retry_count,
            f"fundamental error: {error.message}"
        )

    if error.severity == SEVERITY_CORRECTABLE:
        if retry_count < max_retries:
            return RouteResult(
                REFINE, retry_count + 1,
                f"correctable error, retry {retry_count + 1}/{max_retries}: {error.message}"
            )
        return RouteResult(
            FALLBACK, retry_count,
            f"correctable error but retries exhausted ({retry_count}/{max_retries}) -> fallback"
        )

    raise ValueError(f"unknown severity: {error.severity!r}")


def run_loop(
    attempt_fn,
    validate_fn,
    max_retries: int = DEFAULT_MAX_RETRIES,
    fallback_fn=None,
):
    """Drive a bounded refine loop.

    `attempt_fn(retry_count) -> candidate`
    `validate_fn(candidate) -> (is_valid: bool, error: Optional[ValidationError])`
    `fallback_fn(candidate) -> result` (optional; called on FALLBACK).

    Returns a dict with the terminal decision, the candidate, the number of
    refine iterations, and the full routing trace. Guaranteed to terminate:
    refine increments retry_count and the budget is finite.
    """
    trace = []
    retry_count = 0
    candidate = attempt_fn(retry_count)
    while True:
        is_valid, error = validate_fn(candidate)
        result = route_after_validation(is_valid, error, retry_count, max_retries)
        trace.append({"decision": result.decision, "retry_count": result.retry_count,
                      "rationale": result.rationale})
        if result.decision == PROCEED:
            return {"decision": PROCEED, "candidate": candidate,
                    "iterations": retry_count, "trace": trace}
        if result.decision == REFINE:
            retry_count = result.retry_count
            candidate = attempt_fn(retry_count)
            continue
        if result.decision == FALLBACK:
            fb = fallback_fn(candidate) if fallback_fn else None
            return {"decision": FALLBACK, "candidate": fb if fb is not None else candidate,
                    "iterations": retry_count, "trace": trace}
        # TERMINATE_PARTIAL
        return {"decision": TERMINATE_PARTIAL, "candidate": candidate,
                "iterations": retry_count, "trace": trace}
