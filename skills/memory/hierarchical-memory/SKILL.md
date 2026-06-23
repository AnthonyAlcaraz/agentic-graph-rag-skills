---
name: hierarchical-memory
description: |
  Three-tier hierarchical memory (Letta / MemGPT pattern) — core / recall /
  archival. Core holds a small, fast, frequently-accessed working set (e.g.
  core_limit=2000 tokens). Recall holds raw interaction history for "what
  did we talk about yesterday" questions. Archival holds effectively
  unlimited overflow, still searchable. Make forgetting and archiving
  explicit design choices, not afterthoughts. Use when an agent must
  feel consistent across long sessions and the context window is the
  scarcest resource. NOT for one-shot agents (no persistence needed),
  NOT for event logs (use append-only kafka-style), NOT when every
  fact is equally important (then a flat store is correct).
osmani-pattern: Generator
ghosh-layer: Workflow
chapter-source: "Agentic Graph RAG (O'Reilly) Ch4 — Memory — Letta (MemGPT) Approach + Example 4-6 + CPU Architecture of Agent Memory"
references:
  - "Letta / MemGPT (Packer et al., production anchor)"
  - "Rahimi-derived CPU-architecture three-layer framing (I/O / Cache / Persistent)"
---

# Hierarchical Memory (Letta / MemGPT)

## Overview

Letta popularizes a three-tier memory architecture that mirrors human
cognition and CPU memory hierarchy. The architectural decomposition (Ch4):

- **Core memory** (cache layer): small, fast, structured. The agent's
  active reasoning context. Bounded (`core_limit` parameter). Once full,
  eviction is forced — you cannot have everything in core. This is the
  forcing function that pushes the agent to declare what is durably
  important.
- **Recall memory** (raw interaction layer): the literal conversation
  history. Append-only. Answers "what did we talk about yesterday."
- **Archival memory** (persistent layer): effectively unlimited storage
  for evicted-but-still-relevant facts. Searchable. Not deleted.

Eviction is the key discipline. Naive FIFO (oldest goes first) loses
high-value durable facts that were learned early. Naive LRU (least-recently-
used) loses background-but-relevant context. The chapter recommends a
combined score: access frequency × recency, with explicit handling for
"durable attributes" (peanut allergy) vs "short-lived states" (having
coffee right now).

## When to Use

- Long-running personal assistant agents — multi-session, must feel
  consistent over time
- Multi-day DevOps incident investigation where some facts (production
  region, on-call rotation) are durably important and others (current
  shell history) rotate fast
- Customer-support agents that need both "what we know about this customer"
  (core) and "what was said in last week's tickets" (archival)

Phrases that should invoke this skill: "the agent needs memory across
sessions", "core context", "evict old memory", "MemGPT", "Letta hierarchy",
"working memory vs long-term memory".

## When NOT to Use

- **One-shot agents.** Single-prompt, no persistence — flat context is
  correct. The eviction overhead pays for nothing.
- **Event logs / audit trails.** Use append-only kafka-style logs. The
  recall layer here is interaction-oriented, not event-oriented.
- **Every fact equally important.** Then a flat KV store is right. The
  hierarchy exists because some facts are more important than others;
  if that gradient doesn't exist, the hierarchy is overhead.
- **Hard real-time eviction is too slow.** Default impl is O(n) on
  eviction. Production needs a heap for `evict_least_used`. Swap the
  internal index at the seam noted in `lib.py`.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | core_limit (int, in fact-count or token-count) | `lib.HierarchicalMemory(core_limit=N)` | empty 3-tier memory | core / recall / archival all start empty |
| 2 | user_input, agent_response | `mem.process_interaction(...)` | recall updated; extracted facts promoted to core | `len(mem.recall) > 0`; new facts in core (or in archival if core was full) |
| 3 | fact (string), durability ("durable" / "short-lived") | `mem.add_fact(fact, durability)` | core if room, else evict-and-add | `mem.core` size never exceeds `core_limit` |
| 4 | core is full + new fact | `mem._evict_least_used()` | LFU/LRU fact moved to archival | evicted fact is `was_in_core=True` in archival; core size = limit - 1 + 1 = limit |
| 5 | query string | `mem.query(q)` | hits from core (priority) + recall + archival | results tagged by source tier; archival hits include `evicted_at` |
| 6 | core or archival, no constraints | `mem.snapshot()` | dict serialization | round-trip preserves access counts + tier membership |
| 7 | core size + access pattern after N interactions | `mem.diagnostics()` | health report (% durable in core, eviction rate, archival growth) | flags pathological patterns (e.g. 80% short-lived facts in core = wrong promotion logic) |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Core is small — I'll just make it bigger." | The chapter is explicit: "The core_limit=2000 parameter is not just a tuning knob, but a forcing function." Growing core defers the eviction decision; the decision still has to be made when the new limit is reached. Bigger core trades scarce LLM context budget for cheap-but-unused archival space. |
| "FIFO eviction is good enough." | Loses the "User is allergic to peanuts" fact when a flood of "user is having coffee right now" facts hits. The Ch4 worked example names this exact failure. Track access patterns; durable attributes should resist eviction. |
| "Archival is just deleted memory — I can drop it." | Then recall via `archival.search()` fails. The Ch4 invariant: "eviction is not deletion." The cost of keeping archival is small (it can live in slow durable storage); the cost of dropping it is the agent forgets things it learned. |
| "Recall and archival are the same thing." | Recall is interaction-oriented (full conversation turns, append-only). Archival is fact-oriented (evicted from core, still searchable). They serve different queries: "what did we talk about" vs "what did I learn about the user." Conflating them loses the distinction. |
| "I'll skip the diagnostics step — eviction logic is correct by construction." | Diagnostics catch the slow-rotting failure mode: short-lived facts gradually accumulating in core because their promotion logic was too permissive. Without it you discover the regression in production. |

## Red Flags

- **Core consistently full + high eviction rate.** Promotion logic is too
  permissive; short-lived facts are being promoted. Tighten the durability
  classifier.
- **Same fact promoted-then-evicted-then-promoted repeatedly.** Eviction
  scoring is unstable; either weight access frequency more or add hysteresis.
- **Archival hit rate is 0%.** Either the archival is too small to be
  useful or the search layer is broken. Verify with a known-archived query.
- **Recall is unbounded and growing.** Production needs a recall-eviction
  policy (most recent N interactions, or summarize-and-replace). The
  default impl ships with append-only; size it.
- **`diagnostics()` shows >50% short-lived facts in core after a week.**
  Eviction policy is mis-tuned for this workload.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report:
   - core size never exceeds `core_limit` across 100 random interactions
   - evicted facts are findable in archival
   - durability=durable facts resist eviction over durability=short-lived
   - round-trip serialize/deserialize preserves all tier memberships
2. **Run the DevOps scenario.** `python cli.py scenario long-running-incident`
   must show that durable facts (on-call rotation, production region)
   stay in core while short-lived facts (current shell command, tail of
   log file) rotate through and end up in archival.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints SKILL.md.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, AnthonyAlcaraz / forthcoming),
Chapter 4 — Letta (MemGPT) Approach section, Example 4-6, and the CPU
Architecture of Agent Memory section. Production anchor: Letta / MemGPT
(Packer et al.).
