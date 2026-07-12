---
name: memory-consistency-model-selector
description: |
  Choose a memory consistency model PER agent-coordination operation — STRONG
  (linearizable), CAUSAL, READ-YOUR-WRITES, or EVENTUAL — by scoring the
  operation's requirements (shared authoritative state, conflict intolerance,
  staleness budget, collaboration, self-session continuity), per Ch4 "Memory
  consistency models for agent coordination". This is CAP (consistency vs
  availability) applied per operation to shared agent memory: when Agent A
  writes a fact, WHEN does Agent B see it? Getting it wrong makes agents
  contradict each other, overwrite conclusions, or act on stale state. The
  chapter's rule: default to causal, escalate to strong only for irreversible
  decision points. Also flags cache-sharing divergence (Ch4 "Cache sharing in
  multi-agent systems") — an agent acting on a cached read older than a
  committed write it depends on. Use when designing shared memory for a
  multi-agent system, justifying a consistency choice, or auditing a stale-
  cache handoff. NOT for single-agent stateless systems (no coordination),
  NOT for picking a datastore product (this picks the model, not Redis-vs-etcd),
  NOT when the platform already mandates a consistency model (just adopt it).
osmani-pattern: Inversion
ghosh-layer: Primitive
chapter-source: "Agentic Graph RAG (O'Reilly) Ch4 — Memory — Memory consistency models for agent coordination + Cache sharing in multi-agent systems"
references:
  - "CAP theorem (Brewer): consistency / availability / partition-tolerance — here applied per agent-coordination operation, not once globally"
  - "Ch4 git metaphor: pull-request review = strong, feature-branch tests = eventual, merge queue = causal"
---

# Memory Consistency Model Selector

## Overview

When Agent A writes a fact to shared memory, when does Agent B see it? Ch4
names this the memory consistency problem, and getting it wrong produces agents
that contradict each other, overwrite each other's conclusions, or act on stale
information. **This is CAP — the classic consistency/availability trade-off —
applied per coordination operation to shared agent memory, not decided once
globally.** Consistency is chosen per operation because most workflows mix
safety-critical decision points with tolerant background work.

Four consistency models, each with a characteristic profile:

- **strong** (linearizable): every agent sees the latest write before any
  proceeds. A synchronization barrier after every write — expensive, but
  required when agents act on shared **authoritative** state (locks, budgets,
  inventory) or make safety-critical irreversible decisions. The chapter's
  example: a drug-interaction finding every agent must see before recommending
  treatment.
- **causal**: causally-related writes are ordered; unrelated updates may lag.
  If A's conclusion depends on B's finding, any reader of A also sees B. The
  practical default for collaborating agents.
- **read_your_writes**: an agent always sees its own writes; other agents'
  writes may arrive later. Session memory for a single agent's continuity.
- **eventual**: cheapest; all agents converge eventually, but not when. Fine
  when no single fact is safety-critical and a final synthesis reconciles
  disagreement (background enrichment, literature accumulation).

The selector scores each model across the operation's requirement axes and
recommends one, surfacing `escalate_to_strong` when the default is not strong
but the operation touches authoritative state — the chapter's rule: **default
to causal, escalate the irreversible decision points to strong.**

The cache-divergence helper makes the failure concrete. Ch4's cache-sharing
section warns that without a protocol, Agent B acts on a cached read that a
newer committed write already superseded. `detect_cache_divergence` flags
exactly that: any cached snapshot older than the latest committed write on the
same key.

## When to Use

- Designing shared memory for a multi-agent system with concurrent writers
- Justifying a consistency choice for one coordination operation in a design doc
- Auditing a handoff where an agent may be acting on a stale cached value
- Deciding whether a decision point needs a strong-consistency barrier

Phrases: "consistency model", "linearizable vs eventual", "causal consistency",
"read your writes", "stale cache", "multi-agent memory coordination", "when does
Agent B see Agent A's write", "CAP for agent memory".

## When NOT to Use

- **Single-agent / stateless systems.** No cross-agent coordination means no
  consistency problem to solve.
- **Picking a datastore product.** This selects the consistency model, not
  Redis-vs-etcd-vs-Postgres. Product choice is downstream.
- **A platform-mandated model.** If the framework fixes the consistency
  guarantee, adopt it; the scoring is moot.
- **A single global decision.** The chapter's point is per-operation choice; do
  not collapse a whole system to one model to "keep it simple" (see the
  rationalizations).

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | operation requirements (5 weights 0..3) | `lib.score_models(op)` | `[(model, score), ...]` sorted desc | weights * fitness, descending |
| 2 | same | `lib.recommend_model(op)` | `{recommended, scores, rationale, profile, escalate_to_strong}` | strong on authoritative/conflict, eventual on staleness, causal on collaboration, ryw on self-session |
| 3 | committed writes + per-agent cached reads | `lib.detect_cache_divergence(writes, snaps)` | list of `{agent, key, cached_at, latest_write_at, staleness_gap}` | stale snapshot flagged; current snapshot clean |

CLI: `recommend`, `score`, `cache-check`, `scenario` (shared-budget-lock /
background-enrichment / collaborative-research / session-assistant),
`benchmark`.

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Just use strong consistency everywhere, it's the safe default." | Strong pays a synchronization barrier after every write. On a literature-accumulation or background-enrichment operation that cost buys nothing — no single fact is safety-critical. Ch4: default to causal, escalate to strong only for irreversible decision points. Blanket-strong is the availability tax the per-operation choice exists to avoid. |
| "Eventual is cheapest, use it globally." | Eventual on a shared budget or inventory lock means two agents read different versions and both spend the same money. `escalate_to_strong` fires precisely because the workflow default and the individual authoritative decision point need different models. |
| "One consistency model per system keeps it simple." | The chapter is explicit that consistency is chosen per operation: a pull-request review (strong) versus feature-branch tests (eventual) versus a merge queue (causal) coexist in one repo. Collapsing to one model either over-pays everywhere or under-protects the safety-critical points. |
| "Cache staleness is an edge case, skip the check." | Ch4's cache-sharing section names it as the concrete failure surface: without a protocol, Agent B acts on a superseded cached read and produces a contradictory result. `detect_cache_divergence` is the cheap deterministic guard; a divergent decision downstream is not cheap. |
| "Causal is basically read-your-writes, they're interchangeable." | No. Read-your-writes guarantees an agent sees only its OWN writes; causal orders writes across agents that are causally linked. A collaboration operation where A builds on B needs causal; a single agent's session continuity needs read-your-writes. The scoring separates them so the wrong one is not chosen by habit. |

## Red Flags

- **All five requirement weights set to 3.** You have not prioritized the
  operation. Re-interview: if every axis is critical, the selector degenerates
  to raw fitness averages.
- **Recommended = eventual but the operation touches a budget/lock.** Mismatch:
  authoritative state cannot ride on eventual consistency. Check `escalate_to_strong`.
- **One consistency model chosen for the entire system.** The chapter mandates
  per-operation choice; a single global model is a design smell.
- **Cache-check returns divergences and they are ignored.** Each stale agent is
  a contradictory-decision risk. Add a cache-sharing protocol (broadcast,
  pub-sub, or request-grant per Ch4) or force a re-read before the handoff.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 11/11:
   - strong wins on shared-authoritative-state and on conflict-intolerance
   - eventual wins on high staleness budget, causal on collaboration,
     read_your_writes on self-session-only
   - zero requirements score all models 0; all four are scored, descending
   - cache-check flags a stale read with the correct staleness gap and stays
     clean when the cache is current
   - `escalate_to_strong` fires when causal is the default but authoritative
     state is present
   - the requirement-axis set and the four-model set have not drifted
2. **Run a scenario.** `python cli.py scenario shared-budget-lock` recommends
   strong; `python cli.py scenario background-enrichment` recommends eventual.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints this SKILL.md
   description (CLAUDE.md CLI mandate).

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, forthcoming) Ch4 — Memory,
sections "Memory consistency models for agent coordination" (the strong /
causal / eventual models and the default-causal-escalate-to-strong rule) and
"Cache sharing in multi-agent systems" (broadcast / pub-sub / request-grant
patterns and the stale-cache failure surface). The read-your-writes model is
the standard session-consistency guarantee from distributed-systems practice,
added as the fourth per-operation option. The consistency/availability framing
is the CAP theorem (Brewer) applied per coordination operation.
