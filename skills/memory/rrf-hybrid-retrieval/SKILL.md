---
name: rrf-hybrid-retrieval
description: |
  Reciprocal Rank Fusion (RRF) hybrid retrieval across 4 parallel channels —
  semantic / keyword / graph-traversal / temporal — followed by cross-encoder
  rerank and token-budget filter (HINDSIGHT, Latimer et al. 2025, cited in
  Ch4). Rank-based fusion means scores don't need calibration across
  channels; absent items contribute nothing; items high in multiple lists
  surface naturally. Use when memory must answer queries that mix
  conceptual / exact-id / connected-entity / recent-event facets. NOT for
  single-channel retrieval (just use that channel), NOT for systems where
  one channel dominates (the fusion is overhead).
osmani-pattern: Pipeline
ghosh-layer: Workflow
chapter-source: "Agentic GraphRAG (O'Reilly) Ch4 — Memory — Retrieval section + HINDSIGHT (Latimer et al. 2025)"
references:
  - "Cormack et al., Reciprocal Rank Fusion outperforms Condorcet (2009) — the canonical RRF paper"
  - "HINDSIGHT 4-channel application in agentic memory (Ch4 anchor)"
---

# RRF Hybrid Retrieval

## Overview

A DevOps incident query like "latency spike in checkout related to recent
deploy" needs four kinds of retrieval:

- **Semantic**: conceptually similar past incidents (vector similarity)
- **Keyword**: exact identifiers (`checkout-api`, `deploy-v3.5.0`)
- **Graph traversal**: connected entities (services that depend on
  checkout-api; deploys that touched it)
- **Temporal**: recent events (last 24h, by deploy timestamp)

Any single channel misses; semantic loses exact identifiers, keyword
misses synonyms, graph misses isolated nodes, temporal misses the
"happened before 24h ago but matters" cases. The fusion is the point.

**Reciprocal Rank Fusion** (Cormack et al. 2009):

```
RRF(item) = sum over channels c of: 1 / (k + rank_c(item))
```

Where `k=60` is the standard. Rank-based — no score calibration needed.
Items missing from a channel contribute zero from that channel. Items
ranked high across multiple channels naturally rise to the top.

After fusion, run a cross-encoder reranker over the top-N for precision,
then apply a token-budget filter so the result fits the downstream LLM's
context window. Per HINDSIGHT (Latimer et al. 2025, cited in Ch4): "After
RRF, a neural cross-encoder reranker refines precision on top candidates,
then token budget filtering ensures results fit the downstream LLM's
context window."

## When to Use

- Memory queries that span multiple retrieval-channel "shapes" (conceptual
  + exact + connected + recent)
- Production DevOps incident-investigation, customer-support resolution,
  research-synthesis agents
- When you need to combine heterogeneous retrieval methods and don't want
  to calibrate scores across them

Phrases: "hybrid retrieval", "RRF", "reciprocal rank fusion", "multi-
channel search", "combine semantic and keyword", "cross-encoder rerank".

## When NOT to Use

- Single-channel retrieval is sufficient (e.g. keyword-only ID lookup)
- One channel dominates and the others contribute noise
- Real-time hot path where the cross-encoder rerank exceeds latency
  budget (~50-200ms typical) — fall back to RRF without rerank

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | query + 4 channel rankings (each a list of doc_ids in rank order) | `lib.rrf_fuse(channels, k=60)` | List of (doc_id, fusion_score) sorted descending | doc_ids in multiple channels rank higher than doc_ids in one |
| 2 | top-N from fusion + query | `lib.cross_encoder_rerank(top_n, query)` | Reranked top-N | reranker can re-order but does not introduce or drop items |
| 3 | reranked list + token-count fn + budget | `lib.token_budget_filter(items, get_tokens, budget)` | Filtered list fitting under budget | sum(tokens) <= budget |
| 4 | full pipeline | `lib.hybrid_retrieve(query, channel_callables, ...)` | Final result list | each item has fusion_score + rerank_score + token_count |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "I'll just use vector search and call it a day." | Vector search misses exact identifiers ("incident INC-1043" — the embedding for "INC-1043" is noise). Exact identifiers are graph-traversal + keyword's job. The 4-channel composition exists because no single channel is sufficient. |
| "I'll combine scores from each channel — RRF is overkill." | Score scales differ across channels (cosine 0-1, BM25 0-100+, graph hop-count 1-10). Combining requires calibration. RRF sidesteps this by using ranks. The Ch4 anchor names this exact advantage. |
| "Cross-encoder rerank is slow — skip it." | Skip it when latency budget is tight, document the choice. The rerank produces measurable precision lift on the top-5; without it, top-5 is fusion-only and can include "popular but wrong" items. |
| "Token budget filter loses information." | Yes — that's the point. The downstream LLM's context is bounded. Either you filter, or the LLM truncates blindly. Filtering with intent (drop the lowest-rerank-score) beats truncation by accident. |

## Red Flags

- **RRF score distribution is flat (top-10 all very close).** Channels are
  redundant — they're returning the same items. The fusion is buying
  nothing; either trim channels or check that each channel is exercising
  a different shape.
- **Cross-encoder rerank changes top-10 by > 80%.** Either the fusion is
  bad or the cross-encoder is mis-tuned for this domain.
- **Token budget filter drops > 50% of reranked items.** Budget is too
  small for the query complexity — either widen the budget or write
  multiple narrower queries.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report:
   - RRF formula matches Cormack et al. 2009 reference
   - items in multiple channels rank above items in one
   - token-budget filter respects the budget bound
   - full pipeline produces results with all four score fields
2. **Verify CLI help.** Exits 0 and prints SKILL.md description.

## Security Posture

- **Prompt injection.** Retrieved items are untrusted content headed straight
  for an LLM context - fusion and rerank order them, they do not sanitize
  them. An adversarial document that ranks in multiple channels gets
  RRF-amplified into the budget-filtered prompt; run an injection filter
  between retrieval and prompt assembly.
- **Data exfiltration.** Fusion aggregates across four channels with no ACL of
  its own - a broad query can pull sensitive items from any channel into one
  context. Enforce access control per channel BEFORE fusion; the skill itself
  makes no network calls and writes no files.
- **Privilege escalation.** No shell invocation, no eval. The influence vector
  is rank manipulation: content stuffed with exact identifiers plus synonyms
  to score across channels and dominate the token budget. Cross-encoder rerank
  helps but is not a security control.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien) Ch4 — Retrieval
section. RRF formula: Cormack et al. 2009 (Reciprocal Rank Fusion
outperforms Condorcet and individual rank learning methods). HINDSIGHT
4-channel application: Latimer et al. 2025.
