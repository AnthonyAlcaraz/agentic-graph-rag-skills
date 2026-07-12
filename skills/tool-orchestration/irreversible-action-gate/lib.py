"""Irreversible-action gate: reversibility classification, delivery-guarantee
prescription, and saga/point-of-no-return analysis for agent tool calls.

The book carries this primitive in pieces: Ch5 names "action irreversibility"
as a first-class risk and requires plans with explicit preconditions and
rollback procedures; Ch3 gates RollbackDeployment behind SHACL preconditions
(:rollbackApproved, :lastKnownGoodVersion); Ch4 escalates memory consistency
to strong before decision points that trigger irreversible actions; Ch7 ranks
interventions by reversibility. This skill packages those pieces into one
deterministic gate at the execution boundary.

Pure standard library. TODO production swaps at the seams: the precondition
gate should query a real knowledge graph (SPARQL/Cypher) instead of a fact
dict, and idempotency keys should be persisted in a store with TTL, not
returned to the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Reversibility classes (Ch7 hierarchy, applied at the tool boundary)
# ---------------------------------------------------------------------------

REVERSIBLE = "REVERSIBLE"            # read-only or idempotent-and-undoable
SEMI_REVERSIBLE = "SEMI_REVERSIBLE"  # compensable: a named inverse action exists
IRREVERSIBLE = "IRREVERSIBLE"        # no inverse: deletion, external message, money

CLASSES = (REVERSIBLE, SEMI_REVERSIBLE, IRREVERSIBLE)

# Side-effect scopes, ordered by containment.
SCOPES = ("none", "internal", "external")


@dataclass
class Action:
    """A tool call the agent proposes to execute.

    side_effect_scope: none (pure read), internal (mutates state the agent's
      own system controls), external (crosses a boundary you do not control:
      emails, pages, payments, third-party APIs).
    """

    name: str
    side_effect_scope: str = "none"
    idempotent: bool = False
    data_destructive: bool = False
    compensating_action: Optional[str] = None
    supports_dry_run: bool = False
    preconditions: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.side_effect_scope not in SCOPES:
            raise ValueError(
                f"unknown side_effect_scope {self.side_effect_scope!r}; "
                f"expected one of {SCOPES}"
            )


def action_from_spec(spec: Dict) -> Action:
    return Action(
        name=spec["name"],
        side_effect_scope=spec.get("side_effect_scope", "none"),
        idempotent=bool(spec.get("idempotent", False)),
        data_destructive=bool(spec.get("data_destructive", False)),
        compensating_action=spec.get("compensating_action"),
        supports_dry_run=bool(spec.get("supports_dry_run", False)),
        preconditions=list(spec.get("preconditions", [])),
    )


# ---------------------------------------------------------------------------
# Step 1 — classify reversibility
# ---------------------------------------------------------------------------

def classify(action: Action) -> Dict:
    """Classify an action's reversibility from its declared properties.

    Rules (checked in order):
    - no side effects            -> REVERSIBLE (a read cannot need undoing)
    - data-destructive           -> IRREVERSIBLE unless a compensating action
                                    exists AND the scope is internal (you can
                                    restore your own backup; you cannot unsend
                                    an external deletion request)
    - external side effects      -> IRREVERSIBLE unless compensable (an unsend/
                                    cancel API), because the world saw it
    - internal + compensable     -> SEMI_REVERSIBLE
    - internal, no compensation  -> IRREVERSIBLE (mutation with no inverse)
    """
    reasons: List[str] = []
    if action.side_effect_scope == "none":
        cls = REVERSIBLE
        reasons.append("no side effects: pure read, nothing to undo")
    elif action.data_destructive:
        if action.compensating_action and action.side_effect_scope == "internal":
            cls = SEMI_REVERSIBLE
            reasons.append(
                f"destructive but internally compensable via "
                f"'{action.compensating_action}' (restore path exists)"
            )
        else:
            cls = IRREVERSIBLE
            reasons.append(
                "data-destructive with no internal restore path"
                + (" (external scope: the deletion left your system)"
                   if action.side_effect_scope == "external" else "")
            )
    elif action.side_effect_scope == "external":
        if action.compensating_action:
            cls = SEMI_REVERSIBLE
            reasons.append(
                f"external but compensable via '{action.compensating_action}'"
            )
        else:
            cls = IRREVERSIBLE
            reasons.append(
                "external side effect with no compensation: "
                "the world already observed it"
            )
    elif action.compensating_action:
        cls = SEMI_REVERSIBLE
        reasons.append(
            f"internal mutation compensable via '{action.compensating_action}'"
        )
    else:
        cls = IRREVERSIBLE
        reasons.append("internal mutation with no declared inverse")
    return {"action": action.name, "class": cls, "reasons": reasons}


# ---------------------------------------------------------------------------
# Step 2 — prescribe delivery guarantees
# ---------------------------------------------------------------------------

def prescribe(action: Action) -> Dict:
    """Prescribe the execution contract for an action.

    retry_policy:
      - safe_retry       reads: retry freely
      - at_least_once    idempotent mutations, or mutations WITH an
                         idempotency key (duplicates collapse)
      - at_most_once     non-idempotent mutation without a key: never
                         auto-retry; a timeout is NOT a failure receipt
    """
    cls = classify(action)["class"]
    mutating = action.side_effect_scope != "none"
    needs_key = mutating and not action.idempotent
    if not mutating:
        retry = "safe_retry"
    elif action.idempotent or needs_key:
        # With a key the executor may retry; without idempotency AND without
        # a key we would be at_most_once, but the prescription REQUIRES the
        # key, so the resulting contract is at_least_once-with-key.
        retry = "at_least_once_with_idempotency_key" if needs_key else "at_least_once"
    else:
        retry = "at_most_once"

    dry_run_first = cls == IRREVERSIBLE and action.supports_dry_run
    human_approval = cls == IRREVERSIBLE and not action.supports_dry_run

    return {
        "action": action.name,
        "class": cls,
        "idempotency_key_required": needs_key,
        "retry_policy": retry,
        "dry_run_first": dry_run_first,
        "human_approval_required": human_approval,
        "register_compensation_before_execute": cls == SEMI_REVERSIBLE,
        "precondition_gate": list(action.preconditions),
        "consistency_note": (
            "read decision inputs under STRONG consistency before executing"
            if cls == IRREVERSIBLE else
            "causal consistency sufficient for decision inputs"
        ),
    }


# ---------------------------------------------------------------------------
# Step 3 — deterministic precondition gate (Ch3 SHACL discipline)
# ---------------------------------------------------------------------------

def gate(action: Action, facts: Dict[str, bool]) -> Dict:
    """Check every declared precondition against known graph facts.

    Fails closed: a precondition missing from `facts` blocks execution.
    """
    missing = [p for p in action.preconditions if not facts.get(p, False)]
    return {
        "action": action.name,
        "allowed": not missing,
        "checked": list(action.preconditions),
        "blocking": missing,
        "verdict": (
            "EXECUTE" if not missing
            else f"BLOCKED: {len(missing)} precondition(s) unmet"
        ),
    }


# ---------------------------------------------------------------------------
# Step 4 — saga analysis: compensation stack + point of no return
# ---------------------------------------------------------------------------

def saga(actions: List[Action]) -> Dict:
    """Analyze an ordered multi-step plan as a saga.

    - Builds the compensation stack (reverse order of semi-reversible steps).
    - Finds the point of no return (PONR): the first IRREVERSIBLE step.
      Before the PONR, failure recovery = run the compensation stack
      (backward recovery). At and after the PONR, backward recovery is
      impossible: every later step must support forward recovery (retry to
      completion), so any REVERSIBLE/SEMI_REVERSIBLE step placed after the
      PONR is flagged: if it can run before, it should.
    """
    steps = []
    ponr_index: Optional[int] = None
    for i, a in enumerate(actions):
        cls = classify(a)["class"]
        steps.append({"index": i, "action": a.name, "class": cls})
        if cls == IRREVERSIBLE and ponr_index is None:
            ponr_index = i

    compensation_stack = [
        a.compensating_action
        for a in reversed(actions[: ponr_index if ponr_index is not None else len(actions)])
        if a.compensating_action
    ]

    reorder_flags = []
    if ponr_index is not None:
        for i in range(ponr_index + 1, len(actions)):
            if steps[i]["class"] != IRREVERSIBLE:
                reorder_flags.append(
                    f"step {i} '{actions[i].name}' ({steps[i]['class']}) runs "
                    f"after the point of no return; move it before step "
                    f"{ponr_index} '{actions[ponr_index].name}' if it can run earlier"
                )

    return {
        "steps": steps,
        "point_of_no_return": (
            {"index": ponr_index, "action": actions[ponr_index].name}
            if ponr_index is not None else None
        ),
        "compensation_stack": compensation_stack,
        "recovery_before_ponr": "backward (run compensation stack)",
        "recovery_at_or_after_ponr": "forward only (retry to completion)",
        "reorder_flags": reorder_flags,
    }


# TODO production — persist idempotency keys in a store with TTL and scope
# them per (action, target, parameters-hash); wire `gate` to the live
# knowledge graph (SPARQL ASK / Cypher EXISTS) instead of a fact dict; emit
# the compensation stack into the execution graph (Ch7) so the rollback path
# is an auditable node, not tribal knowledge.
