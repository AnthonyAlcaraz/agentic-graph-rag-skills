"""
Capability Model authorization gate (Ch3 "Capability Model Pattern").

Self-aware agents must understand their own capabilities and limitations. The
Capability Model represents operational parameters as queryable structure:
each capability declares what it requires, an authorization level, and optional
quantitative limits. At PLANNING time the agent checks whether it has the
access, authorization, and operational headroom to fulfill a request BEFORE
attempting it -- and routes/escalates when it does not.

Worked example from the chapter: a Customer-Support-Agent can Answer-Product-
Question (Public) but Process-Refund requires Supervisor authorization and a
500-USD limit. A 600-USD refund request must be recognized as exceeding
authority and routed appropriately, not attempted.

DevOps manifestation (Ch3 DevOps section): agent capabilities are queryable
nodes (read metrics, query logs, describe infrastructure) each with an
authorization level -- the queryable authority model that gates tool
orchestration in Ch6.

Pure Python, stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Authorization levels, ordered low -> high. The actor's granted level must be
# >= the capability's required level.
AUTH_ORDER = ["Public", "User", "Supervisor", "Admin"]


@dataclass
class Capability:
    """A single declared capability with its requirements and bounds."""
    type: str
    authorization_level: str = "Public"
    requires: List[str] = field(default_factory=list)   # required grants/resources
    limit: Optional[float] = None                        # quantitative cap (e.g. 500 USD)
    limit_unit: Optional[str] = None

    def __post_init__(self):
        if self.authorization_level not in AUTH_ORDER:
            raise ValueError(
                f"unknown authorization level '{self.authorization_level}'; "
                f"expected one of {AUTH_ORDER}"
            )


@dataclass
class Agent:
    """An agent with declared capabilities and granted authority/resources."""
    id: str
    capabilities: Dict[str, Capability] = field(default_factory=dict)
    granted_level: str = "Public"
    granted_resources: List[str] = field(default_factory=list)

    def add_capability(self, cap: Capability) -> None:
        self.capabilities[cap.type] = cap


def _level_rank(level: str) -> int:
    return AUTH_ORDER.index(level)


def authorize(
    agent: Agent,
    capability_type: str,
    amount: Optional[float] = None,
) -> Dict[str, Any]:
    """Decide whether the agent may perform a capability for an optional amount.

    Returns a decision dict:
      {decision: "allow" | "escalate" | "deny",
       capability, reasons: [...], required_level, granted_level}

    decision semantics (Ch3):
      allow    -- capability exists, auth level met, resources present, within limit
      escalate -- the agent CANNOT do it itself but a higher authority could
                  (auth level too low, or amount over limit) -> route appropriately
      deny     -- the capability is undeclared (the agent has no such ability)
    """
    reasons: List[str] = []

    cap = agent.capabilities.get(capability_type)
    if cap is None:
        return {
            "decision": "deny",
            "capability": capability_type,
            "reasons": [f"agent '{agent.id}' has no declared capability "
                        f"'{capability_type}'"],
            "required_level": None,
            "granted_level": agent.granted_level,
        }

    escalate = False

    # Authorization level check.
    if _level_rank(agent.granted_level) < _level_rank(cap.authorization_level):
        reasons.append(
            f"authorization too low: requires {cap.authorization_level}, "
            f"agent granted {agent.granted_level}"
        )
        escalate = True
    else:
        reasons.append(f"authorization level met ({cap.authorization_level})")

    # Required resources/grants check.
    missing = [r for r in cap.requires if r not in agent.granted_resources]
    if missing:
        reasons.append(f"missing required resources/grants: {missing}")
        escalate = True
    elif cap.requires:
        reasons.append(f"required resources present: {cap.requires}")

    # Quantitative limit check.
    if cap.limit is not None and amount is not None:
        if amount > cap.limit:
            reasons.append(
                f"amount {amount} exceeds limit {cap.limit}"
                + (f" {cap.limit_unit}" if cap.limit_unit else "")
            )
            escalate = True
        else:
            reasons.append(f"amount {amount} within limit {cap.limit}")
    elif cap.limit is not None and amount is None:
        reasons.append(f"WARNING: capability has a {cap.limit} limit but no amount "
                       "was supplied to check against")

    decision = "escalate" if escalate else "allow"
    return {
        "decision": decision,
        "capability": capability_type,
        "reasons": reasons,
        "required_level": cap.authorization_level,
        "granted_level": agent.granted_level,
    }


def can_do(agent: Agent, capability_type: str, amount: Optional[float] = None) -> bool:
    """Convenience boolean: True only if the decision is 'allow'."""
    return authorize(agent, capability_type, amount)["decision"] == "allow"


def agent_from_spec(spec: Dict[str, Any]) -> Agent:
    """Build an Agent from a JSON-friendly spec.

    spec: {id, granted_level, granted_resources: [...],
           capabilities: [{type, authorization_level, requires, limit, limit_unit}, ...]}
    """
    agent = Agent(
        id=spec["id"],
        granted_level=spec.get("granted_level", "Public"),
        granted_resources=list(spec.get("granted_resources", [])),
    )
    for c in spec.get("capabilities", []):
        agent.add_capability(Capability(
            type=c["type"],
            authorization_level=c.get("authorization_level", "Public"),
            requires=list(c.get("requires", [])),
            limit=c.get("limit"),
            limit_unit=c.get("limit_unit"),
        ))
    return agent
