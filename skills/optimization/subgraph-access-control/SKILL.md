---
name: subgraph-access-control
description: |
  Scope what each agent persona can see in a knowledge graph. Generates Neo4j
  fine-grained GRANT/DENY policy (traverse on node labels + relationship types,
  read on properties) per persona role, enforces security transparency
  (out-of-scope nodes are invisible, not access-denied), handles PII via the
  UUID-separation pattern with GDPR soft/hard erasure, and turns the Chapter-7
  execution graph into a compliance artifact via governance metadata. Use for
  graph-backed agents where one unscoped query could traverse from a public
  catalog to employee records. NOT for relational row/table permissions, NOT for
  network/IAM policy, NOT for prompt-level guardrails (this governs graph reach).
osmani-pattern: Generator
ghosh-layer: Primitive
chapter-source: "Agentic GraphRAG (O'Reilly) Ch8 — Optimization"
---

# Subgraph Access Control

## Overview

An agent with unrestricted access to your knowledge graph is a liability. The
dense relationships that make agentic reasoning powerful also mean a single
unscoped query can traverse from a public product catalog to internal cost data
to employee records. In a graph, everything is reachable from everything else.

Graph databases have mature access-control primitives. Neo4j Enterprise supports
privileges at the node-label, relationship-type, and property level: you GRANT
traverse rights on specific labels, DENY read access to specific properties, and
combine them into role-based policies. A critical design feature is **security
transparency** — when a role lacks permission to see a node, the node is
invisible, not access-denied. The agent cannot distinguish data that does not
exist from data it is not allowed to see, which blocks an autonomous agent from
probing access boundaries as part of its reasoning.

This skill covers the three governance concerns from the chapter: subgraph-level
access control (a role per persona, bound at connection time), PII and retention
(Rehmer's Privacy-by-Architecture UUID separation with GDPR soft/hard erasure),
and the execution graph as a compliance artifact (KG.GOV governance metadata
that answers auditor questions as a graph query).

## When to Use

- A graph-backed agent serves multiple personas (SRE, finance) who need
  different views of the same graph.
- You must prove which role accessed which data for a compliance review.
- The graph holds PII and you need GDPR Article 17 erasure that does not cascade
  across densely connected relationships.
- You are testing that an access policy does not accidentally starve the agent's
  reasoning (the "governance blocks the agent" pitfall).

Phrases that should invoke this skill: "who can see what in the graph",
"subgraph access control", "role-based graph permissions", "GDPR delete from the
graph", "PII in the knowledge graph", "compliance audit of agent decisions".

## When NOT to Use

- **Relational row/table permissions.** This is graph-native (labels, relationship
  types, properties). Use SQL GRANT for tables.
- **Network / cloud IAM.** IAM scopes API calls; this scopes graph traversal.
  They compose (the execution-graph `access_role` ties back to the IAM role) but
  are different layers.
- **Prompt-level guardrails.** A jailbreak-resistant system prompt is not access
  control; this enforces reach at the database, below the model.
- **Single-persona agents.** If every query runs as one role, a static
  connection policy suffices; you do not need per-persona generation.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Persona role name | `lib.generate_policy(role)` | Neo4j GRANT/DENY Cypher | Contains GRANT TRAVERSE + DENY on cost/employee |
| 2 | Role + label (+ property) | `lib.can_traverse` / `lib.can_read` | Boolean | False traverse => invisible, not denied |
| 3 | Role + agent query labels | `lib.audit_access(role, labels)` | reachable / invisible / masked + functionally_complete | Complete only if every needed label is reachable |
| 4 | (design) | `lib.privacy_by_architecture()` | UUID / Identity-Store split | Graph stores only uuid + relationships |
| 5 | UUID + mode | `lib.gdpr_erase(uuid, mode)` | soft (mask+orphan) or hard (DETACH DELETE) | Hard emits DETACH DELETE; soft preserves aggregates |
| 6 | Decision facts | `lib.governance_metadata(...)` | Execution-graph governance record | Carries model_id/version + access_role + pii_accessed |
| 7 | Governance records | `lib.audit_query(records, pii_accessed=True)` | Filtered compliance answer | Returns exactly the PII-accessing decisions |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|-----------------------|---------------------|
| "Return access-denied so the agent knows to stop." | Access-denied leaks the existence of the data. Security transparency makes the node invisible so the agent cannot distinguish "absent" from "forbidden" and cannot probe the boundary (Ch8). |
| "One admin role is simpler than a role per persona." | One role means the agent acting for an SRE can also read finance cost data and employee PII — exactly the cross-domain traversal the chapter opens with. Bind a role per persona at connection time. |
| "Just delete the user node for GDPR." | In a densely connected graph a raw delete cascades into relationships you need to keep. The UUID-separation pattern lets you mask the identity mapping (real-time, single-row) and clean the graph asynchronously (Ch8). |
| "Governance is an external overlay we add later." | KG.GOV makes governance a first-class citizen of the graph: the execution graph already captures data_sources_accessed and access_role, so the audit answer is a graph query, not a log-parsing project (Example 8-6). |
| "Lock the policy down as tight as possible." | Over-restriction starves reasoning: if the SRE role cannot reach Library nodes, dependency analysis breaks. Test the policy against the agent's real query patterns first (`audit_access`; Ch8 pitfall). |

## Red Flags

- **Policy returns access-denied instead of invisibility.** Security
  transparency is broken; the boundary is now probeable.
- **The SRE role can read `cost_per_hour` or traverse `Employee`.** Cross-domain
  leakage — the exact failure the chapter opens with.
- **GDPR "delete" leaves the identity mapping intact.** Erasure is not honoured;
  soft delete must mask the mapping, hard delete must DETACH DELETE.
- **`audit_access` reports functionally_complete for a role missing a required
  label.** The completeness check is wrong; dependency reasoning will silently
  break in production.
- **Governance record omits model_id/version.** In a selective-intelligence
  fleet you cannot attribute a decision to a model. CLI `--help` exits non-zero
  is the same class of failure at the harness seam.

## Non-Negotiable Verification

Before deploying a policy built on this skill:

1. **Run the benchmark battery.**
   ```
   python cli.py benchmark
   ```
   Confirms SRE cannot read cost, finance cannot traverse Library, Employee is
   invisible to every role, soft/hard erasure behave correctly, and the audit
   query filters PII-accessing decisions.

2. **Read a generated policy.**
   ```
   python cli.py policy sre_oncall
   ```
   Confirm it GRANTs traversal on infra labels and DENYs read on cost properties
   and traversal on Employee/Compensation.

3. **Run the pitfall test against a real investigation.**
   ```
   python cli.py audit sre_oncall --labels Service,Library,Metric
   ```
   Confirm `functionally_complete` is true — the SRE dependency workflow is not
   starved by the policy.

4. **Domain test in the notebook.** Run `notebooks/ch8-optimization.ipynb`;
   confirm the governance section generates both roles, proves the SRE cannot
   see cost data, and attaches a governance record to the execution graph.

## Security Posture

- **This IS the security control.** The skill emits policy and answers access
  questions; the actual enforcement is Neo4j Enterprise applying the emitted
  GRANT/DENY at query time. Generating a policy is not enforcing it — apply it to
  the database.
- **Security transparency by construction.** `can_traverse` returning False
  models invisibility; do not "helpfully" surface a denied-node hint to the
  agent, which would re-open the boundary-probing surface.
- **PII stays out of the graph.** Under Privacy-by-Architecture the graph holds
  only UUIDs; never write name/email/PII onto graph nodes. If PII appears on a
  node, the erasure guarantees break.
- **Governance metadata is append-only.** Compliance records must be immutable;
  do not mutate a governance record after the decision it describes.

## Composition

- **Ties into** `model-routing-selector` / `cost-performance-scorer` (Ch8): the
  governance record's `model_id`/`model_version` attribute each decision to the
  model that produced it in a selective-intelligence fleet.
- **Extends** the Chapter-7 execution graph: governance metadata is added to the
  existing execution-graph nodes, so the compliance artifact needs no new store.
- **Composes with** cloud IAM at the `access_role` seam — the graph role maps to
  the IAM role the agent connects under.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien),
Chapter 8 — Optimization, "Data Governance and Access Control". Key references:

- Neo4j Enterprise fine-grained access control (Example 8-5, Example 8-15)
- Security transparency (invisible-not-denied) design principle
- Mohamed et al. survey of property-graph access control (RBAC/ABAC/hybrid;
  plan a policy abstraction layer across engines)
- Rehmer "Privacy by Architecture" (UUID separation, Identity Store join key)
- GDPR Article 17 soft/hard erasure
- KG.GOV governance framework + Example 8-6 governance metadata
