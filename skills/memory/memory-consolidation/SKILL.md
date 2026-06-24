---
name: memory-consolidation
description: |
  Consolidation pipeline — turn noisy raw episodes into durable knowledge
  (Agentic Graph RAG Ch4, Example 4-5 + Example 4-13). Four steps: cluster
  related episodes by topic, summarize each cluster into one consolidated
  fact, create the consolidated node, and maintain a provenance chain back
  to the source episodes so "how do you know that?" is answerable. Clusters
  below a minimum size (default 3) are skipped — not enough examples to
  generalize. Adds the sleep-time-compute discipline: run consolidation
  during idle periods, never on the synchronous response path, and
  pre-compute inferences that anticipate likely queries. Use when an agent
  accumulates redundant, overlapping experiences that must compress into
  stable, queryable patterns. NOT for one-shot agents (nothing to
  consolidate), NOT for the response hot path (consolidation is a
  background/idle job), NOT for facts that must stay individually
  addressable (consolidation merges them).
osmani-pattern: Pipeline
ghosh-layer: Workflow
chapter-source: "Agentic Graph RAG (O'Reilly) by Anthony Alcaraz & Julien — Ch4: Memory — Consolidation: From Experience to Knowledge (Example 4-5) + Adding Memory to the DevOps Agent (Example 4-13)"
references:
  - "Letta + UC Berkeley sleep-time compute (Ch4): shift heavy computation to idle periods — ~5x lower active inference cost, 13-18% accuracy lift at same budget"
  - "HINDSIGHT narrative-fact extraction (Latimer et al. 2025, cited Ch4): 2-5 comprehensive narrative facts per conversation, not sentence-level fragments"
---

# Memory Consolidation

## Overview

Your agent accumulates many interactions, but most are redundant, overlapping,
or partially inconsistent. Consolidation is the agent's "sleep phase": it
compresses short-term experiences into long-term understanding. Ch4 frames
this as four steps (Example 4-5):

1. **Cluster** related memories (`cluster_by_topic`) — group conversations
   about the same project/incident by similarity.
2. **Summarize** each cluster (`summarize_cluster`) — replace "Monday: deadline
   Friday; Tuesday: confirmed Friday; Wednesday: Friday again" with one fact:
   "Project deadline: Friday (confirmed 3 times)". Meaning preserved,
   redundancy gone.
3. **Consolidate** into permanent graph nodes (`create_consolidated_memory`).
4. **Maintain provenance** (`maintain_provenance_chain`) — keep the
   `DERIVED_FROM` links so the agent can trace a belief back to the exact
   interactions that produced it.

Two disciplines from the chapter shape the implementation:

- **Minimum cluster size** (Example 4-13: "Need enough examples to
  generalize"). A pattern derived from a single episode is not a pattern.
  Default minimum is 3.
- **Sleep-time compute** (Letta + UC Berkeley, Ch4): consolidation runs
  during idle periods, not while a user waits. Shifting it off the response
  path cuts active inference cost ~5x and lets you pre-compute inferences
  (which tasks are at risk, given a deadline + dependencies) before anyone
  asks.

## When to Use

- An agent with accumulating episodic memory that grows noisy over time
- DevOps incident memory: turn many similar 503-after-deploy incidents into
  one durable `Pattern` node with a runbook
- Conversational assistants that repeat the same fact across sessions
- Any system that needs to answer "how do you know X?" with a provenance trace

Phrases: "consolidate memory", "summarize episodes", "sleep-time compute",
"provenance chain", "compress experience into knowledge", "cluster incidents".

## When NOT to Use

- One-shot / stateless agents — there is nothing to consolidate
- The synchronous response path — consolidation is a background/idle job
- Facts that must remain individually addressable (an audit log of distinct
  events) — consolidation deliberately merges them
- Clusters that never reach the minimum size — keep the raw episodes; do not
  fabricate a pattern from one example

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | list of raw episodes | `lib.cluster_by_topic(episodes, threshold)` | list of clusters | related episodes group; unrelated ones split |
| 2 | one cluster | `lib.summarize_cluster(cluster)` | one durable fact string | multi-episode summary carries a confirmation count |
| 3 | all episodes | `lib.consolidate(episodes, min_cluster_size)` | list of `ConsolidatedFact` | clusters below min size are skipped |
| 4 | a fact + episodes | `lib.provenance_of(fact, episodes)` | source episodes | round-trips; dangling links raise |
| 5 | facts + idle worker | `lib.precompute_inferences(facts, inference_fn)` | {fact_id: inferences} | runs off the response path |

CLI: `cluster`, `consolidate`, `scenario incident-consolidation`, `benchmark`.

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "I'll consolidate on every turn so memory is always fresh." | Consolidation is expensive (clustering + summarization). The chapter's sleep-time-compute result is explicit: run it during idle periods, not the response path — ~5x cheaper active inference. On-turn consolidation pays the cost when the user is waiting. |
| "One vivid episode is enough to make a pattern." | Example 4-13 sets `if len(cluster) < 3: continue`. A pattern from one example is an overfit. The minimum-size gate is part of the design, not a tuning knob. |
| "I'll drop the provenance links to save space." | Then "how do you know the deadline is Friday?" becomes unanswerable and you cannot debug a wrong conclusion. The `DERIVED_FROM` chain is what makes consolidated knowledge trustworthy and inspectable. |
| "Sentence-level facts are simpler to extract." | Sentence-level extraction fragments cross-turn context (Ch4). HINDSIGHT extracts 2-5 narrative facts per conversation. The `summarizer_fn` seam is where you swap the extractive default for the narrative LLM form. |

## Red Flags

- **Every episode lands in its own singleton cluster.** The similarity
  threshold is too high, or the similarity function is mis-tuned for the
  domain (the default token-overlap may need an embedding swap).
- **One giant cluster swallows everything.** Threshold too low — unrelated
  episodes are being glued together. Tighten it or switch to semantic
  similarity.
- **Consolidated facts have empty `derived_from`.** The provenance chain was
  dropped — the fact is now unexplainable and undebuggable.
- **Consolidation appears in the request latency profile.** It is running on
  the response path. Move it to a background/idle worker.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 10/10:
   related episodes cluster, the min-size gate skips small clusters, full
   provenance is recorded and round-trips, dangling provenance raises,
   clustering is deterministic, and sleep-time precompute keys by fact id.
2. **Verify CLI help.** `python cli.py --help` exits 0 and prints the SKILL.md
   description.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly) by Anthony Alcaraz & Julien —
Ch4: Memory — "Consolidation: From Experience to Knowledge" (Example 4-5) and
"Adding Memory to the DevOps Agent" (Example 4-13). Sleep-time compute: Letta +
UC Berkeley research cited in Ch4. Narrative-fact extraction: HINDSIGHT
(Latimer et al. 2025).
