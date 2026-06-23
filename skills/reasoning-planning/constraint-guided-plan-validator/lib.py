"""
Constraint-guided plan validator (Ch5 — Constraint-guided planning +
capability-model filter + ontological grounding).

Validates a generated plan against (a) extracted domain constraints and
(b) the agent's capability model (which actions it is authorized to perform,
at what privilege level), producing a 0..1 conformance score. If the score is
below threshold, it returns structured feedback so the plan can be refined
(Example 5-14). It also filters out steps the agent cannot execute -- the
capability-model check from the DevOps hypothesis-formation node.

Pure Python, stdlib only.

Production swap: `ConstraintExtractor` here parses a small constraint DSL.
In production an LLM extracts constraints from the natural-language request
(Example 5-14 `ConstraintExtractor`), and the capability model is a set of
graph nodes (Ch3). The verify/score/filter logic below is exact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

THRESHOLD = 0.8   # Example 5-14: refine when validation_result.score < THRESHOLD


@dataclass
class PlanStep:
    action: str                  # e.g. "query_metrics", "modify_db", "read_logs"
    privilege: str = "read"      # required privilege: "read" | "write" | "admin"
    params: Dict[str, object] = field(default_factory=dict)


@dataclass
class Constraint:
    kind: str                    # "max_steps" | "deadline_days" | "forbidden_action" | "required_action"
    value: object


@dataclass
class CapabilityModel:
    """Operational boundaries as queryable data (Ch3 capability-model pattern)."""
    allowed_actions: Set[str]
    max_privilege: str = "read"          # highest privilege the agent holds

    _PRIV_ORDER = {"read": 0, "write": 1, "admin": 2}

    def authorizes(self, step: PlanStep) -> bool:
        if step.action not in self.allowed_actions:
            return False
        return self._PRIV_ORDER.get(step.privilege, 99) <= self._PRIV_ORDER.get(self.max_privilege, -1)


@dataclass
class Violation:
    step_index: Optional[int]    # None for plan-level violations
    constraint_kind: str
    message: str


@dataclass
class ValidationResult:
    score: float                 # 0..1 conformance
    violations: List[Violation]
    passed: bool                 # score >= threshold AND no hard violations

    @property
    def feedback(self) -> List[str]:
        return [f"[{v.constraint_kind}] step={v.step_index}: {v.message}" for v in self.violations]


# -- constraint extraction (DSL stand-in) ---------------------------------

def extract_constraints(spec: Dict[str, object]) -> List[Constraint]:
    """Parse a constraint spec dict into Constraint objects.

    Production: LLM extracts these from the user request (Example 5-14
    ConstraintExtractor.extract). Supported keys: max_steps, deadline_days,
    forbidden_actions (list), required_actions (list).
    """
    out: List[Constraint] = []
    if "max_steps" in spec:
        out.append(Constraint("max_steps", int(spec["max_steps"])))
    if "deadline_days" in spec:
        out.append(Constraint("deadline_days", int(spec["deadline_days"])))
    for a in spec.get("forbidden_actions", []):
        out.append(Constraint("forbidden_action", a))
    for a in spec.get("required_actions", []):
        out.append(Constraint("required_action", a))
    return out


# -- validation -----------------------------------------------------------

def filter_executable_steps(
    plan: List[PlanStep], capability: CapabilityModel
) -> List[Violation]:
    """Capability-model filter (DevOps hypothesis-formation node).

    A step requiring an action/privilege the agent lacks is a violation:
    "a hypothesis requiring direct database access gets filtered if the agent
    only has read-only monitoring permissions."
    """
    violations: List[Violation] = []
    for i, step in enumerate(plan):
        if not capability.authorizes(step):
            violations.append(Violation(
                i, "capability",
                f"action {step.action!r} (priv {step.privilege!r}) exceeds "
                f"agent capability (max priv {capability.max_privilege!r})"
            ))
    return violations


def verify(
    plan: List[PlanStep],
    constraints: List[Constraint],
    capability: Optional[CapabilityModel] = None,
    threshold: float = THRESHOLD,
) -> ValidationResult:
    """Validate plan against constraints + capability model -> scored result.

    Score = 1 - (violations / total_checks). Capability violations and
    forbidden-action violations are HARD: any one forces passed=False
    regardless of score (a plan the agent cannot legally execute is not
    'mostly fine').
    """
    violations: List[Violation] = []
    checks = 0
    hard = False

    for c in constraints:
        checks += 1
        if c.kind == "max_steps":
            if len(plan) > int(c.value):
                violations.append(Violation(None, "max_steps",
                    f"plan has {len(plan)} steps, max is {c.value}"))
        elif c.kind == "deadline_days":
            # plan-level: any step carrying eta_days beyond deadline violates
            over = [i for i, s in enumerate(plan)
                    if isinstance(s.params.get("eta_days"), (int, float))
                    and s.params["eta_days"] > int(c.value)]
            for i in over:
                violations.append(Violation(i, "deadline_days",
                    f"step eta {plan[i].params['eta_days']}d exceeds {c.value}d deadline"))
        elif c.kind == "forbidden_action":
            for i, s in enumerate(plan):
                if s.action == c.value:
                    violations.append(Violation(i, "forbidden_action",
                        f"action {c.value!r} is forbidden"))
                    hard = True
        elif c.kind == "required_action":
            if not any(s.action == c.value for s in plan):
                violations.append(Violation(None, "required_action",
                    f"required action {c.value!r} missing from plan"))

    if capability is not None:
        cap_viol = filter_executable_steps(plan, capability)
        checks += len(plan)  # one capability check per step
        if cap_viol:
            hard = True
        violations.extend(cap_viol)

    checks = max(checks, 1)
    score = max(0.0, 1.0 - len(violations) / checks)
    passed = (score >= threshold) and not hard
    return ValidationResult(score=round(score, 4), violations=violations, passed=passed)


def steps_from_dicts(rows: List[dict]) -> List[PlanStep]:
    return [PlanStep(action=r["action"],
                     privilege=r.get("privilege", "read"),
                     params=r.get("params", {})) for r in rows]
