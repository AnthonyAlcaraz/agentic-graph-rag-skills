"""
Schema evolution, node/edge lifecycle, incremental updates, and staged-rollout
deployment for a production knowledge graph — distilled from Agentic Graph RAG
(O'Reilly), Chapter 8 — Optimization, "Production Systems and Maintenance".

A knowledge graph in production is not static. New data arrives continuously,
schemas evolve, stale nodes accumulate. Without lifecycle management the graph
grows stale, queries slow, and the agent's reasoning degrades — not because the
agent changed but because the knowledge it depends on did.

Four operational concerns, all covered here:
  schema evolution   — Neo4j-Migrations (Flyway/Liquibase for graphs); migration
      history stored as a subgraph; N-1 backward compatibility (Example 8-7).
  lifecycle          — append-only + TTL (CrowdStrike Threat Graph: 40+ PB,
      trillions of events/day, 70M req/s, never update only add) and temporal
      invalidation (Graphiti/Zep bitemporal t_valid/t_invalid; Example 8-8).
  incremental update — LightRAG-style MERGE ON CREATE / ON MATCH; update cost
      proportional to the new data, not the existing graph (Example 8-9).
  deployment         — staged rollout coordinating schema + data + agent code,
      N-1 compatible, canary-gated (Example 8-10).

Pure Python, stdlib only. Emits Cypher + a structured deployment manifest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# --- Schema evolution (Example 8-7) -----------------------------------------

@dataclass
class Migration:
    """A versioned graph schema migration (Neo4j-Migrations shape).

    n1_compatible: True when the previous application version keeps working
    after the migration applies (the critical discipline for zero-downtime).
    """
    version: str
    description: str
    cypher: str
    rollback: str
    n1_compatible: bool


def monitored_by_migration() -> Migration:
    """The book's V003 migration (Example 8-7): add MONITORED_BY between Service
    and AlertRule, plus a uniqueness constraint. N-1 compatible: old code
    ignores the new edge type."""
    cypher = (
        "// V003__add_monitored_by_relationship.cypher\n"
        "MATCH (s:Service)\n"
        "WHERE s.alert_config IS NOT NULL\n"
        "WITH s, s.alert_config AS config\n"
        "MERGE (ar:AlertRule {name: config})\n"
        "MERGE (s)-[:MONITORED_BY]->(ar);\n\n"
        "CREATE CONSTRAINT alertrule_name_unique IF NOT EXISTS\n"
        "FOR (ar:AlertRule) REQUIRE ar.name IS UNIQUE;"
    )
    rollback = (
        "// V003__rollback.cypher\n"
        "MATCH (:Service)-[r:MONITORED_BY]->(:AlertRule) DELETE r;\n"
        "DROP CONSTRAINT alertrule_name_unique IF EXISTS;"
    )
    return Migration("V003", "add MONITORED_BY between Service and AlertRule",
                     cypher, rollback, n1_compatible=True)


# --- Lifecycle: temporal invalidation (Example 8-8) --------------------------

def temporal_invalidate_cypher(service: str, library: str,
                               old_version: str, new_version: str,
                               source: str = "deployment-event") -> str:
    """Invalidate an old dependency edge (set t_invalid) and merge the new one,
    rather than deleting (Graphiti bitemporal model, Example 8-8). Historical
    queries can still traverse the old edge by filtering on validity windows."""
    return (
        f'MATCH (a:Service {{name: "{service}"}})\n'
        f'      -[old:DEPENDS_ON]->(b:Library {{name: "{library}"}})\n'
        f'WHERE old.version = "{old_version}" AND old.t_invalid IS NULL\n'
        f'SET old.t_invalid = datetime()\n'
        f'WITH a\n'
        f'MERGE (new_lib:Library {{name: "{library}", version: "{new_version}"}})\n'
        f'MERGE (a)-[:DEPENDS_ON {{\n'
        f'    version: "{new_version}",\n'
        f'    t_valid: datetime(),\n'
        f'    t_invalid: null,\n'
        f'    source: "{source}"\n'
        f'}}]->(new_lib);'
    )


def snapshot_growth_per_day(n_resources: int, interval_minutes: int) -> int:
    """Estimate snapshot-node growth (Fischer, Ch8): sampling infrastructure
    resources at a fixed interval. 200 resources at 5-minute intervals produce
    57,600 new nodes per day for a single small cluster."""
    samples_per_day = 24 * 60 // interval_minutes
    return n_resources * samples_per_day


# Retention policy per node class (Fischer, Ch8): aggressive TTL for temporal
# snapshots, permanent retention for hub nodes. Also the Common Pitfalls
# "overpruning" fix: incident records retained far longer than op snapshots.
RETENTION_POLICY: dict[str, str] = {
    "snapshot": "30_days_full_then_hourly_then_daily_downsample",
    "incident": "retain_long (training signal for failure prediction)",
    "hub": "permanent (accounts, regions, top-level services — query anchors)",
}


# --- Incremental update (LightRAG, Example 8-9) ------------------------------

def incremental_merge_cypher(event: dict[str, Any]) -> list[str]:
    """Emit the three-statement incremental merge for a deployment event
    (Example 8-9): upsert the service, upsert library dependencies with temporal
    timestamps, invalidate dependencies that no longer appear. Update cost is
    proportional to the new data, not the whole graph (vs GraphRAG rebuild)."""
    stmts = []
    # 1. Upsert the service node (create if new, enrich if existing).
    stmts.append(
        "MERGE (s:Service {name: $service_name})\n"
        "ON CREATE SET s.first_seen = datetime(), s.environment = $env\n"
        "ON MATCH SET  s.last_updated = datetime()\n"
        "SET s.current_version = $new_version, s.last_deployment = datetime()"
    )
    # 2. Upsert library dependencies from the manifest.
    stmts.append(
        "MERGE (l:Library {name: $lib_name, version: $lib_version})\n"
        "WITH l\n"
        "MATCH (s:Service {name: $service_name})\n"
        "MERGE (s)-[d:DEPENDS_ON]->(l)\n"
        "ON CREATE SET d.t_valid = datetime(), d.t_invalid = null"
    )
    # 3. Invalidate old dependency edges that no longer appear.
    stmts.append(
        "MATCH (s:Service {name: $service_name})-[d:DEPENDS_ON]->(l:Library)\n"
        "WHERE d.t_invalid IS NULL AND NOT l.name IN $current_libs\n"
        "SET d.t_invalid = datetime()"
    )
    return stmts


# --- Deployment: staged rollout (Example 8-10) -------------------------------

@dataclass
class Phase:
    name: str
    artifact: str
    depends_on: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def staged_rollout_manifest(release: str) -> dict[str, Any]:
    """Build the four-phase staged-rollout manifest coordinating schema, data,
    and agent code (Example 8-10). depends_on enforces ordering; the agent-code
    phase carries the canary + promotion criteria; schema cleanup waits until no
    code references the deprecated element."""
    phases = [
        Phase("schema_migration",
              "migrations/V003__add_monitored_by_relationship.cypher",
              extra={"validation": "CALL db.schema.visualization()",
                     "rollback": "migrations/V003__rollback.cypher",
                     "note": "N-1 compatible: old code ignores MONITORED_BY edges"}),
        Phase("data_backfill", "scripts/backfill_monitored_by.py",
              depends_on="schema_migration",
              extra={"validation": "MATCH (s:Service)-[:MONITORED_BY]->(a:AlertRule) "
                                   "RETURN count(s) > 0 AS backfill_complete"}),
        Phase("agent_code", "agent/causal_attribution_node_v2.py",
              depends_on="data_backfill",
              extra={"canary_percent": 5, "canary_duration": "2h",
                     "promotion_criteria": {"regression_suite_pass": True,
                                            "p95_latency_ms": "<500",
                                            "prediction_accuracy_delta": ">=-0.02"}}),
        Phase("schema_cleanup",
              "migrations/V004__drop_legacy_alert_config_property.cypher",
              depends_on="agent_code",
              extra={"delay": "7d",
                     "note": "Remove s.alert_config after all code uses MONITORED_BY"}),
    ]
    return {
        "release": release,
        "phases": [
            {"name": p.name, "artifact": p.artifact,
             **({"depends_on": p.depends_on} if p.depends_on else {}), **p.extra}
            for p in phases
        ],
    }


_EXPECTED_ORDER = ["schema_migration", "data_backfill", "agent_code", "schema_cleanup"]


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate the staged-rollout discipline: phases in the correct order, each
    non-first phase depends on the prior one, schema migration declares N-1
    compatibility, and the agent-code phase has canary + promotion criteria."""
    problems = []
    names = [p["name"] for p in manifest.get("phases", [])]
    if names != _EXPECTED_ORDER:
        problems.append(f"phase order {names} != {_EXPECTED_ORDER}")

    by_name = {p["name"]: p for p in manifest.get("phases", [])}
    for i, name in enumerate(names):
        p = by_name[name]
        if i == 0:
            if "depends_on" in p:
                problems.append(f"{name} (first phase) should have no depends_on")
        else:
            if p.get("depends_on") != names[i - 1]:
                problems.append(f"{name} must depend on {names[i - 1]}")

    sm = by_name.get("schema_migration", {})
    if "N-1" not in sm.get("note", ""):
        problems.append("schema_migration must declare N-1 compatibility")

    ac = by_name.get("agent_code", {})
    if "canary_percent" not in ac or "promotion_criteria" not in ac:
        problems.append("agent_code must carry canary + promotion_criteria")

    cleanup = by_name.get("schema_cleanup", {})
    if not cleanup.get("delay"):
        problems.append("schema_cleanup must wait (delay) before dropping legacy schema")

    return {"valid": not problems, "problems": problems}
