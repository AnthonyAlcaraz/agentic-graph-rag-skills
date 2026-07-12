---
name: graphiti-incremental-update
description: |
  Graphiti (Zep) incremental-update pattern (Ch4). When new content arrives,
  process only the new content — never re-process the entire graph. Pipeline:
  (1) extract entities from new episode, (2) entity-resolve against existing
  graph (dedupe by canonical name + alias + fuzzy match), (3) incremental-
  update — touch only the affected neighborhood, leave the rest of the graph
  unchanged. Keeps update latency O(new content) instead of O(full graph),
  enabling sub-second latency at millions-of-nodes scale. Use when memory
  graph grows continuously and full-graph re-embedding is impossibly
  expensive. NOT for one-shot batch ingestion (just process it once), NOT
  for static knowledge bases (no updates means no incremental anything).
osmani-pattern: Pipeline
ghosh-layer: Workflow
chapter-source: "Agentic GraphRAG (O'Reilly) Ch4 — Memory — Graphiti Pattern + Example 4-8"
references:
  - "Graphiti / Zep (production anchor — sub-second retrieval at millions-of-nodes)"
  - "Composes with bi-temporal-edge (every incremental update gets bi-temporal timestamps)"
---

# Graphiti Incremental-Update

## Overview

A naive add-to-graph implementation re-extracts entities across the whole
corpus, re-computes embeddings, and re-clusters everything every time new
content arrives. At millions-of-nodes scale this is fatal: update latency
grows with graph size, and the agent ends up waiting for re-indexing
instead of reasoning.

Graphiti (Zep) ships a different pattern (Ch4 Example 4-8):

1. **Extract** entities and relationships *only from the new episode*.
   No backfill, no full-corpus re-pass.
2. **Entity-resolve**: match each extracted entity against existing graph
   nodes by canonical name, then alias, then fuzzy/embedding similarity.
   If matched, reuse the existing node id. If not, create new.
3. **Incremental-update**: modify only the touched neighborhood. New
   edges, possibly updated node metadata, no global re-clustering.

The chapter quote: "incremental_update modifies only the impacted
neighborhood: the few nodes and edges touched by the new entities and
relationships. The rest of the graph stays untouched, which keeps write
operations predictably fast."

The retrieval side mirrors this: instead of one big query over everything,
run parallel partial queries (vector / graph walk / keyword) targeting
recent / specific / textual subsets, then merge. Production-grade
Reciprocal Rank Fusion lives in a sibling skill; this skill is the
ingestion side.

## When to Use

- Memory graph that grows continuously (every interaction adds nodes)
- DevOps incident streams: new alerts, new deployments, new comments
  arriving every few seconds
- Customer-support agents where each ticket is an "episode" — entities
  (customer, product, issue type) resolve to existing nodes, new edges
  are added
- Multi-agent systems where each agent contributes new content to a
  shared graph and no agent should block on full-graph re-processing

Phrases: "incremental update", "don't re-process the whole graph", "entity
resolution", "deduplicate against existing nodes", "Graphiti pattern",
"add an episode".

## When NOT to Use

- **One-shot batch ingestion.** Process the corpus once, build the graph,
  done. Incremental pattern is overhead.
- **Static knowledge base.** No updates means no incremental anything.
- **Adversarial entity resolution (bot accounts, evasion).** Default
  fuzzy-match heuristic is too permissive; use a hardened resolver with
  domain rules.
- **Very small graph (< 1000 nodes).** Full re-process is cheap; the
  incremental dispatch overhead exceeds the savings.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | new episode (text or structured) | `lib.extract_entities(episode)` | list of `ExtractedEntity` (name, type, aliases, metadata) | each extracted entity has non-empty `name` and `type` |
| 2 | extracted entities + existing graph | `lib.entity_resolution(extracted, graph)` | list of `ResolvedEntity` (`existing_node_id` or None) + resolution-method log | resolution-method ∈ {canonical, alias, fuzzy, new}; method distribution should be heavily {canonical, alias} for mature graphs |
| 3 | resolved entities + episode metadata | `lib.incremental_update(resolved, graph, episode_id)` | updated graph (in-place); touched-nodes list | touched_nodes count == size of impacted neighborhood (not full graph); rest of graph unchanged (checksum) |
| 4 | full pipeline | `lib.add_episode(episode, graph)` | episode_id + touched_nodes + resolution_log | end-to-end latency scales with episode size, not graph size |
| 5 | graph + before/after snapshots | `lib.verify_locality(before, after)` | "X nodes changed of Y total — Z%" | Z% should be small (< 5%) for typical mature-graph incremental adds |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "I'll just re-extract everything every time — disk is cheap." | Disk is cheap; latency is not. The Ch4 anchor explicitly notes Graphiti maintains "sub-second response times even as the number of nodes and edges climbs into the millions." Re-extracting at that scale defeats the architecture. |
| "Entity resolution is too brittle — I'll create a new node every time." | Then the graph bloats: 50 different ids for "Sarah" across 50 interactions. The Ch4 quote: "this step ensures they resolve to the same entity rather than creating duplicates." Without resolution, `manages` edges scatter across duplicate Sarah-nodes and the agent can't aggregate. |
| "Fuzzy match is good enough — I'll skip canonical + alias." | Order matters. Canonical match is O(1) dictionary lookup; alias is O(1); fuzzy is O(n) or worse. Resolution should try cheap-and-exact first, fall back to expensive-and-approximate. Skipping the cheap path is a perf regression hiding as a correctness "improvement." |
| "Incremental update sounds like premature optimization — start with full re-extract." | At small scale it doesn't matter. At any production scale (Zep target: millions of nodes), full re-extract is impossible. Building the architecture incremental-from-day-one means migration day never comes. |
| "Touched-nodes verification is overkill — trust the algorithm." | The locality invariant is the property everything else rests on. A bug that silently touches every node looks identical to a correct incremental update at the call site. The verify_locality step is the falsifier — without it, regressions land silently. |

## Red Flags

- **touched_nodes count grows with graph size.** The incremental property
  is broken; something is doing a full scan. Inspect entity_resolution
  and incremental_update for accidental full-graph passes.
- **Resolution method distribution is > 80% "new" on a mature graph.**
  Either the graph is bootstrapping (early days, expected) or canonical/
  alias resolution is broken (mature, anomalous).
- **Fuzzy match rate > 30% on a mature graph.** Aliases are missing.
  Add the canonical aliases as exact matches; reserve fuzzy for genuinely
  unknown variants.
- **Entity-resolved-to-existing but the existing node's type doesn't match.**
  Resolution is confusing person-named-Apple with company-named-Apple. Add
  type-aware resolution; never collapse across types.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report:
   - touched_nodes count is independent of graph size (10-node graph and
     1000-node graph produce the same touched_nodes for the same episode)
   - canonical / alias / fuzzy / new resolution methods all exercised
   - locality invariant: % nodes changed < 10% for the test workload
   - round-trip serialize/deserialize preserves graph state
2. **Run the DevOps scenario.** `python cli.py scenario incident-stream`
   must process 20 incident-update episodes, with touched_nodes per
   episode << total graph size.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints SKILL.md.

## Security Posture

- **Prompt injection.** Episodes are untrusted input (chat turns, incident
  feeds). Extraction and resolution treat episode text as data - nothing is
  executed - but an adversarial episode can plant false entities or alias
  itself onto an existing node to corrupt what the graph "knows". Type-aware
  resolution and the resolution-method log are the audit surface; review
  high-impact merges.
- **Data exfiltration.** Episode content is persisted into the durable graph -
  sensitive facts mentioned once stay retrievable indefinitely. No network
  calls or file writes in the skill itself; apply retention policy at the
  graph store.
- **Privilege escalation.** No shell invocation, no eval. The escalation path
  is graph poisoning: a crafted episode that resolves onto a trusted node
  inherits that node's standing in downstream reasoning. Keep the locality
  check (touched_nodes) as a blast-radius bound and gate bulk merges.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien),
Chapter 4 — Graphiti Pattern section + Example 4-8. Production anchor: Zep
Graphiti.
