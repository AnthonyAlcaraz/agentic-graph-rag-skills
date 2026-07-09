---
name: schema-evolution-migrator
description: |
  Keep a production knowledge graph healthy across schema evolution, node/edge
  lifecycle, incremental updates, and coordinated deployment. Emits N-1
  compatible Neo4j-Migrations-style schema migrations, temporal-invalidation
  Cypher (bitemporal t_valid/t_invalid, invalidate-not-delete), LightRAG-style
  incremental merge from a deployment event, TTL/retention policy per node class,
  and a four-phase staged-rollout manifest coordinating schema + data + agent
  code with canary gates. Use when a graph-backed agent must ship changes to the
  graph and the code together without downtime. NOT for one-time graph creation,
  NOT for relational migrations (Flyway/Liquibase), NOT for model routing.
osmani-pattern: Pipeline
ghosh-layer: Orchestration
chapter-source: "Agentic Graph RAG (O'Reilly) Ch8 — Optimization"
---

# Schema Evolution Migrator

## Overview

A knowledge graph in production is not a static artifact. New data arrives
continuously, schemas evolve, and nodes accumulate that no longer represent
current reality. Without deliberate lifecycle management the graph grows stale,
queries slow down, and the agent's reasoning degrades — not because the agent
changed but because the knowledge it depends on did.

Graph databases have no `ALTER TABLE`, and the schema-optional nature of property
graphs means schema drift happens silently. This skill packages the four
operational concerns from the chapter:

- **Schema evolution** — Neo4j-Migrations (Flyway/Liquibase for graphs); the
  migration history is itself a subgraph. Every change must be **N-1
  compatible**: the previous application version keeps working until it is
  replaced (Example 8-7).
- **Lifecycle** — append-only with TTL (CrowdStrike's Threat Graph never
  updates, only adds: 40+ PB, trillions of events/day, 70M req/s) and temporal
  invalidation (Graphiti/Zep bitemporal: invalidate the old edge, do not delete
  it, so historical queries still traverse it — Example 8-8).
- **Incremental updates** — LightRAG-style `MERGE ON CREATE / ON MATCH`; update
  cost is proportional to the new data, not the whole graph, so a deployment
  event is reflected within seconds instead of a nightly rebuild (Example 8-9).
- **Deployment** — a staged rollout coordinating three independently versioned
  components (schema, data, agent code) with `depends_on` ordering and a canary
  gate (Example 8-10).

## When to Use

- A production graph needs a schema change (new relationship type, new
  constraint) deployed alongside agent-code changes.
- A dependency changed and you must record the new fact without losing the old
  one for causal reasoning.
- Snapshot nodes are accumulating and you need a retention policy.
- You are coordinating a release across graph schema, data backfill, and agent
  code and want a manifest that enforces the ordering.

Phrases that should invoke this skill: "migrate the graph schema", "temporal
invalidation", "incremental graph update", "deployment manifest", "N-1
compatibility", "staged rollout", "TTL the knowledge graph".

## When NOT to Use

- **One-time graph construction.** Initial build is not evolution; use the
  Chapter-3 construction pattern.
- **Relational migrations.** Flyway/Liquibase handle SQL; this is graph-native
  (MERGE, DETACH, constraints).
- **Splitting/merging node types.** As of the book no graph DB natively supports
  these; Nautilus/Geo-X compile them to Cypher/APOC externally. Plan the schema
  carefully upfront and budget engineering time.
- **Model routing / cost / latency.** Those are the other Ch8 skills.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | (design) | `lib.monitored_by_migration()` | V003 migration + rollback | N-1 compatible; rollback present |
| 2 | Dependency change | `lib.temporal_invalidate_cypher(...)` | SET t_invalid + MERGE new edge | Sets t_invalid, never DELETE |
| 3 | Deployment event JSON | `lib.incremental_merge_cypher(event)` | 3-statement merge | Uses ON CREATE/ON MATCH; invalidates gone deps |
| 4 | resources + interval | `lib.snapshot_growth_per_day(n, m)` | Nodes/day estimate | 200 @ 5-min = 57,600 |
| 5 | node class | `lib.RETENTION_POLICY[class]` | Retention rule | hub = permanent; snapshot = aggressive TTL |
| 6 | release name | `lib.staged_rollout_manifest(release)` | 4-phase manifest | depends_on ordering enforced |
| 7 | manifest | `lib.validate_manifest(manifest)` | valid + problems | Fails on mis-ordering or missing canary |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|-----------------------|---------------------|
| "Just delete the old dependency edge." | Delete destroys the historical record the agent needs for causal reasoning ("what did the infra look like before the change"). Invalidate with t_invalid; historical queries filter on validity windows (Example 8-8). |
| "Deploy the schema migration and the code together." | If the code deploys before the migration it references relationship types that do not exist; if the migration renames an edge before the old code is gone, the old code breaks. Stage it: migration first with N-1 compatibility, then code, then cleanup (Example 8-10). |
| "Rebuild the graph nightly to stay current." | A full rebuild is expensive and creates a stale-or-inconsistent window. LightRAG incremental merge costs in proportion to the new data, not the graph size — the event lands in seconds (Example 8-9). |
| "Aggressive TTL everywhere keeps the graph small." | Overpruning deletes the incident history the failure-prediction agent trains on. TTL snapshots aggressively; retain incident and hub nodes long (RETENTION_POLICY; Ch8 pitfall). |
| "Drop the legacy property as soon as the new code ships." | A code path may still reference it. The manifest delays schema cleanup (7 days) until no code references the deprecated element (Example 8-10). |

## Red Flags

- **A migration that is not N-1 compatible ships without a two-phase plan.**
  The previous app version will break the moment the migration lands.
- **Invalidation uses DELETE.** The historical edge is gone; causal reasoning
  over past states silently loses data.
- **Incremental merge without ON CREATE/ON MATCH.** Either duplicates nodes or
  overwrites enrichment; the upsert semantics are the point.
- **Manifest with agent_code before schema_migration.** The staged-rollout
  ordering is inverted; `validate_manifest` must fail it.
- **Schema cleanup with no delay.** Legacy schema dropped while code still
  references it. CLI `--help` exiting non-zero is the same class of seam break.

## Non-Negotiable Verification

Before shipping a graph change built on this skill:

1. **Run the benchmark battery.**
   ```
   python cli.py benchmark
   ```
   Confirms N-1 compatibility, invalidate-not-delete, the Fischer growth math
   (200 @ 5-min = 57,600), incremental upsert semantics, and that a mis-ordered
   manifest fails validation.

2. **Read the migration and its rollback.**
   ```
   python cli.py migration
   ```
   Confirm the forward migration adds MONITORED_BY + the uniqueness constraint
   and the rollback removes both.

3. **Validate the deployment manifest.**
   ```
   python cli.py manifest --release r1 | python cli.py validate --manifest /dev/stdin
   ```
   (or `python cli.py validate`) — confirm valid=true and the phases are
   schema -> data -> code -> cleanup with a canary on the code phase.

4. **Domain test in the notebook.** Run `notebooks/ch8-optimization.ipynb`;
   confirm the schema-evolution section generates the MONITORED_BY migration and
   ingests the checkout-service stripe-python 3.2.1 -> 3.3.0 deployment event.

## Security Posture

- **Emits Cypher; runs nothing.** `lib.py` builds migration/merge text and a
  manifest dict. Apply migrations through Neo4j-Migrations with review, not by
  piping generated Cypher straight into a production database.
- **Parameterized incremental merge.** The Example 8-9 statements use `$params`,
  not string interpolation of event data — keep it that way; a deployment event
  from an untrusted source is an injection surface if interpolated into Cypher.
- **Migrations are irreversible-ish.** Always ship the rollback and take a
  backup/snapshot before applying; a DETACH DELETE in a hard cleanup cannot be
  undone from the graph alone.
- **N-1 discipline is a safety property.** Skipping it risks a production outage
  window where old code meets new schema; treat the N-1 flag as a gate, not a
  hint.

## Composition

- **Feeds** the Chapter-7 canary/staging mechanics: the manifest's
  `promotion_criteria` (p95 < 500ms, accuracy delta >= -0.02) connect to the
  self-evolution deployment gates.
- **Uses** the temporal model shared with `subgraph-access-control` retention:
  invalidated edges carry validity windows the compliance audit can query.
- **Pairs with** `cost-performance-scorer`: the canary promotion criteria are
  the same cost/quality signals scored there.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, AnthonyAlcaraz / forthcoming),
Chapter 8 — Optimization, "Production Systems and Maintenance". Key references:

- Neo4j-Migrations (Michael Simons) — Flyway/Liquibase for graphs; Example 8-7
- Daschner Kubernetes init-container migration pattern; N-1 compatibility
- Hausler & Klettke — Nautilus / Geo-X (2025) evolution language
- CrowdStrike Threat Graph (append-only + TTL; 40+ PB, 70M req/s)
- Graphiti / Zep bitemporal temporal invalidation (Example 8-8)
- Fischer — temporal infrastructure graph on Neo4j (200 @ 5-min = 57,600/day)
- LightRAG incremental update (Example 8-9)
- Example 8-10 deployment manifest (staged rollout)
