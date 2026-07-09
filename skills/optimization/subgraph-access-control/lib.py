"""
Subgraph-level access control, PII handling, and the execution graph as a
compliance artifact — distilled from Agentic Graph RAG (O'Reilly), Chapter 8 —
Optimization, "Data Governance and Access Control".

An agent with unrestricted access to your knowledge graph is a liability. The
dense relationships that make agentic reasoning powerful also mean a single
unscoped query can traverse from a public service catalog to internal cost data
to employee records. In a graph, everything is reachable from everything else —
that is the point, and it is the governance problem.

Three concerns, all covered here:
  1. Subgraph-level access control — which node labels / relationship types /
     properties a persona role can traverse and read (Neo4j Enterprise
     primitives, Example 8-5 / 8-15). Security transparency: a node the role
     cannot see is INVISIBLE, not access-denied — the agent cannot distinguish
     "does not exist" from "not allowed", which blocks boundary-probing.
  2. PII and retention — Rehmer's "Privacy by Architecture": the graph stores
     only UUIDs + semantic relationships; PII lives in a separate Identity
     Store; the UUID is the join key. GDPR Article 17 erasure is soft (mask the
     mapping, orphan the UUID node) or hard (DETACH DELETE the UUID node).
  3. Execution graph as compliance artifact — KG.GOV: the Chapter-7 execution
     graph, extended with governance metadata (Example 8-6), answers auditor
     questions ("which decisions accessed PII last quarter") as a graph query.

Pure Python, stdlib only. Emits Neo4j Cypher policy text; runs no database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# --- The infrastructure graph shape (Ch8 Example 8-5 / 8-15) ----------------
NODE_LABELS = ("Service", "Deployment", "Library", "AlertRule", "Metric",
               "Employee", "Compensation")
RELATIONSHIP_TYPES = ("DEPENDS_ON", "CALLS", "MONITORED_BY", "DEPLOYED_TO")
SERVICE_PROPERTIES = ("name", "status", "version", "team",
                      "cost_per_hour", "budget_code", "billing_account")


@dataclass
class Role:
    """A persona role bound at connection time (Ch8).

    traverse_labels / traverse_rels: what the role can follow to and read the
        existence of. A label NOT in traverse_labels is invisible.
    read_props: {label: {property, ...}} the role may read. A property not
        listed is masked.
    deny_traverse_labels / deny_read_props: explicit denials (documented in the
        emitted policy for auditability; a label is invisible if it is either
        not granted or explicitly denied).
    """
    name: str
    traverse_labels: frozenset[str]
    traverse_rels: frozenset[str]
    read_props: dict[str, frozenset[str]]
    deny_traverse_labels: frozenset[str] = frozenset()
    deny_read_props: dict[str, frozenset[str]] = field(default_factory=dict)


GRAPH = "infrastructure"

ROLES: dict[str, Role] = {
    # SRE: full infrastructure visibility, no cost data (Example 8-15).
    "sre_oncall": Role(
        name="sre_oncall",
        traverse_labels=frozenset({"Service", "Deployment", "Library", "AlertRule", "Metric"}),
        traverse_rels=frozenset({"DEPENDS_ON", "CALLS", "MONITORED_BY", "DEPLOYED_TO"}),
        read_props={"Service": frozenset({"name", "status", "version", "team"})},
        deny_traverse_labels=frozenset({"Employee", "Compensation"}),
        deny_read_props={"Service": frozenset({"cost_per_hour", "budget_code", "billing_account"})},
    ),
    # Finance: cost visibility, no deployment details (Example 8-15).
    "finance_analyst": Role(
        name="finance_analyst",
        traverse_labels=frozenset({"Service"}),
        traverse_rels=frozenset(),
        read_props={"Service": frozenset({"name", "cost_per_hour", "budget_code",
                                          "billing_account", "team"})},
        deny_traverse_labels=frozenset({"Deployment", "Library", "AlertRule",
                                        "Employee", "Compensation"}),
    ),
    # infra_analyst from Example 8-5.
    "infra_analyst": Role(
        name="infra_analyst",
        traverse_labels=frozenset({"Service", "Deployment"}),
        traverse_rels=frozenset({"DEPENDS_ON"}),
        read_props={"Service": frozenset({"name", "status", "version"})},
        deny_traverse_labels=frozenset({"Employee", "Compensation"}),
        deny_read_props={"Service": frozenset({"cost_per_hour", "budget_code"})},
    ),
}


def generate_policy(role_name: str) -> str:
    """Emit Neo4j Cypher GRANT/DENY statements for a role (Example 8-5 shape)."""
    role = ROLES[role_name]
    lines = [f"CREATE ROLE {role.name};"]
    if role.traverse_labels:
        labels = ", ".join(sorted(role.traverse_labels))
        lines.append(f"GRANT TRAVERSE ON GRAPH {GRAPH} NODES {labels} TO {role.name};")
    if role.traverse_rels:
        rels = ", ".join(sorted(role.traverse_rels))
        lines.append(f"GRANT TRAVERSE ON GRAPH {GRAPH} RELATIONSHIPS {rels} TO {role.name};")
    for label, props in sorted(role.read_props.items()):
        pl = ", ".join(sorted(props))
        lines.append(f"GRANT READ {{{pl}}} ON GRAPH {GRAPH} NODES {label} TO {role.name};")
    for label, props in sorted(role.deny_read_props.items()):
        pl = ", ".join(sorted(props))
        lines.append(f"DENY READ {{{pl}}} ON GRAPH {GRAPH} NODES {label} TO {role.name};")
    if role.deny_traverse_labels:
        labels = ", ".join(sorted(role.deny_traverse_labels))
        lines.append(f"DENY TRAVERSE ON GRAPH {GRAPH} NODES {labels} TO {role.name};")
    return "\n".join(lines)


def can_traverse(role_name: str, label: str) -> bool:
    """Whether the role can reach a node of this label. Security transparency:
    a False here means the node is INVISIBLE to the agent, not access-denied."""
    role = ROLES[role_name]
    if label in role.deny_traverse_labels:
        return False
    return label in role.traverse_labels


def can_read(role_name: str, label: str, prop: str) -> bool:
    """Whether the role can read a property. False -> the property is masked."""
    role = ROLES[role_name]
    if prop in role.deny_read_props.get(label, frozenset()):
        return False
    return prop in role.read_props.get(label, frozenset())


def audit_access(role_name: str, needed_labels: list[str],
                 needed_props: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Test a policy against an agent's actual query pattern (Ch8 Common
    Pitfalls: "governance policies that block the agent's reasoning"). Returns
    which labels are reachable vs invisible and which properties are masked, plus
    whether the investigation is functionally complete.
    """
    needed_props = needed_props or {}
    reachable = [l for l in needed_labels if can_traverse(role_name, l)]
    invisible = [l for l in needed_labels if not can_traverse(role_name, l)]
    masked = {}
    for label, props in needed_props.items():
        m = [p for p in props if not can_read(role_name, label, p)]
        if m:
            masked[label] = m
    return {
        "role": role_name,
        "reachable_labels": reachable,
        "invisible_labels": invisible,
        "masked_properties": masked,
        # Functionally complete = every label the agent needs to TRAVERSE is
        # reachable. Masked properties do not break traversal-based reasoning.
        "functionally_complete": len(invisible) == 0,
    }


# --- PII and retention (Rehmer Privacy by Architecture, Ch8) -----------------

def privacy_by_architecture() -> dict[str, Any]:
    """Describe the UUID-separation pattern: the graph holds only UUIDs +
    semantic relationships; PII lives in a separate Identity Store; the UUID is
    the join key."""
    return {
        "knowledge_graph_stores": ["uuid", "semantic_relationships"],
        "identity_store_stores": ["name", "email", "phone", "address", "pii"],
        "join_key": "uuid",
        "identity_store_kind": "relational database (separate from the graph)",
    }


def gdpr_erase(uuid: str, mode: str = "soft") -> dict[str, Any]:
    """GDPR Article 17 right-to-erasure (Ch8). Two options over the
    UUID-separation pattern.

    soft: mask the identity mapping in the Identity Store; the UUID node stays in
          the graph as an anonymous orphan (relationships preserved for
          aggregate analysis, no longer tied to a person).
    hard: DETACH DELETE the UUID node in Neo4j — removes it and all its
          relationships (strict erasure).

    The practical advantage is speed: masking the identity mapping is a
    single-row update honoured in real time; graph cleanup runs asynchronously.
    """
    if mode not in ("soft", "hard"):
        raise ValueError("mode must be 'soft' or 'hard'")
    if mode == "soft":
        return {
            "mode": "soft",
            "identity_store_action": f"UPDATE identities SET pii=NULL WHERE uuid='{uuid}'",
            "graph_action": "none (UUID node remains as anonymous orphan)",
            "honoured": "real time (single-row update)",
            "aggregate_analysis_preserved": True,
        }
    return {
        "mode": "hard",
        "identity_store_action": f"DELETE FROM identities WHERE uuid='{uuid}'",
        "graph_action": f"MATCH (u {{uuid: '{uuid}'}}) DETACH DELETE u",
        "honoured": "identity mapping real time; graph cleanup asynchronous",
        "aggregate_analysis_preserved": False,
    }


# --- Execution graph as compliance artifact (KG.GOV, Ch8 Example 8-6) --------

def governance_metadata(
    data_sources_accessed: list[str],
    access_role: str,
    model_id: str,
    model_version: str,
    decision_confidence: float,
    pii_accessed: bool = False,
    human_review_required: bool = False,
    retention_policy: str = "90_days",
) -> dict[str, Any]:
    """Build the governance metadata attached to an execution-graph node
    (Example 8-6). model_id/version matter in a selective-intelligence
    architecture: when many models handle different nodes you must know which
    produced which decision. access_role ties back to the RBAC policy above,
    completing the role -> query -> decision chain.
    """
    return {
        "data_sources_accessed": list(data_sources_accessed),
        "access_role": access_role,
        "pii_accessed": pii_accessed,
        "model_id": model_id,
        "model_version": model_version,
        "decision_confidence": decision_confidence,
        "human_review_required": human_review_required,
        "retention_policy": retention_policy,
    }


def audit_query(records: list[dict[str, Any]], pii_accessed: bool | None = None,
                access_role: str | None = None) -> list[dict[str, Any]]:
    """Answer an auditor's question as a filter over execution-graph governance
    records — "show me every agent decision that accessed customer data last
    quarter" is a graph query on pii_accessed, no log parsing required (Ch8)."""
    out = records
    if pii_accessed is not None:
        out = [r for r in out if r.get("pii_accessed") == pii_accessed]
    if access_role is not None:
        out = [r for r in out if r.get("access_role") == access_role]
    return out
