---
name: vector-vs-graph-retrieval-selector
description: |
  Recommend VECTOR / GRAPH / HYBRID retrieval for a query workload, grounded
  in Ch1's BenchmarkQED evidence for where vector RAG succeeds and where it
  collapses. Classifies the workload on the BenchmarkQED scope x type axes
  (local/global, data/activity), weighs multi-hop / temporal / associativity
  needs, domain structure, corpus scale, and latency, then returns a
  recommendation with the chapter's numbers (vector RAG ~90% on DataLocal vs
  20-30% on ActivityGlobal; LazyGraphRAG +50-60% on multi-hop; EyeLevel 12%
  vs 2% accuracy drop at 100k pages). Includes the explicit larger-context-
  window rebuttal (the ~1M-token BenchmarkQED test) and surfaces GraphRAG's
  own costs. Use when choosing a retrieval architecture for an enterprise
  agent. NOT for tuning an existing pipeline's embeddings, NOT for consumer
  FAQ bots where vector RAG is already the right fit.
osmani-pattern: Reviewer
ghosh-layer: Reasoning
chapter-source: "Agentic Graph RAG (O'Reilly) Ch1 — Defining Agentic AI — The Limitations of Vector-Based Retrieval + GraphRAG (lines 117-236)"
references:
  - "Microsoft 'From Local to Global: A GraphRAG Approach to Query-Focused Summarization' + BenchmarkQED (local/global x data/activity)"
  - "EyeLevel.ai — vector vs graph accuracy degradation at scale (12% vs ~2% at 100k pages)"
  - "LinkedIn KG-augmented RAG — 28.6% median per-issue resolution-time reduction over six months"
---

# Vector-vs-Graph Retrieval Selector

## Overview

Ch1 makes the vector-vs-graph choice evidence-based rather than ideological.
Microsoft's BenchmarkQED classifies queries on two axes:

- **Scope** — *local* (specific facts in a small number of regions) vs
  *global / sensemaking* (reasoning over large portions of the dataset).
- **Type** — *data* (direct fact retrieval) vs *activity*
  (interpretive / strategic).

The chapter's numeric anchors:

- Vector RAG: **~90%** accuracy on simple lookups (DataLocal); **20-30%** on
  complex reasoning (ActivityGlobal). "The very mechanism that makes vector
  search efficient becomes its fundamental limitation."
- **LazyGraphRAG outperforms vector RAG by 50-60%** on multi-hop reasoning.
- **EyeLevel.ai**: at 100,000 pages, vector accuracy drops up to **12%** while
  graph drops only **~2%**.
- The larger-context-window rebuttal: BenchmarkQED tested vector RAG against
  LazyGraphRAG with a **~1-million-token window** (essentially the whole
  dataset); vector RAG **still lost on every query type except the most basic
  factual questions**, and bigger windows worsen "lost in the middle."

Where vector RAG shines (Ch1): local, fact-based lookups — customer support,
FAQ, recommendation. Where it collapses: multi-hop reasoning, temporal
awareness, the associativity gap ("which services were affected by the
database migration that followed the security patch we discussed last month").

Ch1's own recommendation for agents is a **HYBRID** architecture — parallel
vector + graph (vector search -> graph traversal -> context synthesis) —
because agentic behavior "requires constantly moving between local and global
understanding." GraphRAG is not free: the chapter names upfront
graph-construction cost, query latency that grows with graph size, contextual
nuance lost in triples, and schema-evolution cost. The selector surfaces those
costs whenever it recommends GRAPH or HYBRID.

## When to Use

- Choosing a retrieval architecture for a new enterprise agent
- Answering "should we add a graph, or is vector RAG enough?"
- Rebutting "let's just use a bigger context window instead of a graph"
- Mapping a mixed query workload to the right per-query strategy
- Teaching the BenchmarkQED local/global x data/activity quadrants

Phrases: "vector or graph", "do we need GraphRAG", "will a bigger context
window fix it", "retrieval architecture", "why does RAG fail on this query",
"local vs global queries".

## When NOT to Use

- **Tuning an existing pipeline** (chunk size, embedding model, reranker) —
  this chooses the architecture, not its hyperparameters.
- **Consumer FAQ / support bots** where DataLocal lookups dominate — the answer
  is VECTOR and you already know it.
- **As a graph builder.** This recommends graph; it does not construct one.
  See Ch3 skills (`graph-model-selector`, `schema-pattern-selector`).

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | scope / type / multi-hop / temporal / structure / scale / latency | `lib.recommend(...)` | VECTOR / GRAPH / HYBRID + reasons | DataLocal lookup -> VECTOR; ActivityGlobal multi-hop -> GRAPH |
| 2 | agentic workload | `recommend(..., agentic=True)` | HYBRID | agent workloads default to the parallel hybrid |
| 3 | graph signals + unstructured/latency-critical | `recommend(...)` | HYBRID (not pure GRAPH) | costly-graph condition down-shifts GRAPH -> HYBRID |
| 4 | `larger_context_window=True` | read `larger_context_window_rebuttal` | the ~1M-token rebuttal text | rebuttal cites the 1M-token BenchmarkQED test |
| 5 | `dataset_scale_pages >= 100000` | read `scale_note` | EyeLevel 12%-vs-2% note | scale note present at 100k+ pages |
| 6 | GRAPH/HYBRID result | read `graphrag_costs` | the four GraphRAG struggles | costs present for GRAPH/HYBRID, absent for VECTOR |
| 7 | list of workloads | `lib.recommend_batch(...)` | per-workload + tally | tally sums to the workload count |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Just use a bigger context window and skip the graph." | Ch1's direct test: BenchmarkQED ran vector RAG with a ~1M-token window (the whole dataset) and it still lost on every query type except the most basic factual questions. More tokens don't create relationships, temporal evolution, or systematic patterns — they worsen "lost in the middle." |
| "Vector RAG scored 90%, it's fine." | That 90% is DataLocal only. On ActivityGlobal the same system scores 20-30%. If your workload has global/multi-hop queries, the headline number does not apply. |
| "Graphs are always better, use GRAPH everywhere." | Ch1 names GraphRAG's costs: upfront construction, query latency, nuance loss in triples, schema-evolution burden. For a latency-critical DataLocal lookup, vector wins. The selector down-shifts to HYBRID/VECTOR when those costs bite. |
| "Our data is unstructured, so a graph is impossible." | Then the recommendation is HYBRID, not 'give up on graph': run vector first, traverse a partial graph selectively, synthesize. Ch1's hybrid is exactly this parallel path. |
| "Scale doesn't change the vector-vs-graph answer." | EyeLevel.ai (Ch1): at 100k pages vector drops up to 12% while graph drops ~2%. Scale widens the gap; the selector attaches the scale note at 100k+ pages. |

## Red Flags

- **A multi-hop / temporal / global workload recommended VECTOR.** The scope or
  multi-hop flags are unset; re-check the workload description against the
  associativity-gap example.
- **GRAPH recommended for a latency-critical DataLocal lookup.** Graph
  traversal is slower than an ANN lookup here; the selector should have chosen
  VECTOR or HYBRID — verify the flags.
- **HYBRID chosen for everything.** Either the workload is genuinely agentic
  (legitimate — that is the book's default) or the signals are under-specified;
  add concrete scope/type/multi-hop values.
- **A GRAPH/HYBRID recommendation adopted without reading `graphrag_costs`.**
  The upfront-construction and maintenance cost is real; budget for it before
  committing.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 8/8:
   - DataLocal lookup -> VECTOR; ActivityGlobal multi-hop -> GRAPH; agentic ->
     HYBRID; graph-signals + unstructured -> HYBRID
   - the larger-context-window flag attaches the 1M-token rebuttal
   - 100k+ pages attaches the EyeLevel 12%-vs-2% scale note
   - GRAPH/HYBRID surface GraphRAG costs; VECTOR does not
   - the ActivityGlobal quadrant carries the 20-30% anchor
2. **Verify CLI help.** `python cli.py --help` exits 0 and prints the SKILL.md
   description.
3. **Inspect the scenario.** `python cli.py scenario devops` should recommend
   VECTOR for the 5xx lookup, GRAPH for the cascading-migration query, and
   HYBRID for the autonomous agent.

## Security Posture

- **Prompt injection.** The selector consumes structured flags and booleans,
  not free-text documents, so there is no injection surface in `lib.py`. The
  numeric anchors and rebuttal text are author-controlled constants, not
  model-generated.
- **Data exfiltration.** No network calls; the only file read is the workloads
  JSON path the caller supplies (default: the bundled sample). `--json` output
  goes to stdout.
- **Privilege escalation.** No shell invocation, no dynamic import, no file
  writes. The recommendation is advisory; it selects an architecture and does
  not touch any datastore or credential.
- **Decision integrity.** Treat the recommendation as a starting point, not a
  mandate — the chapter's numbers are reported so a human can audit the
  rationale rather than trust an opaque verdict.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, AnthonyAlcaraz), Chapter 1 —
Defining Agentic AI, "The Limitations of Vector-Based Retrieval" and
"GraphRAG" sections. The BenchmarkQED quadrants, the 90% / 20-30% vector-RAG
numbers, the LazyGraphRAG +50-60% multi-hop figure, the EyeLevel.ai
12%-vs-2%-at-100k-pages result, and the ~1-million-token larger-context-window
rebuttal are all the chapter's, anchored in Microsoft's "From Local to Global:
A GraphRAG Approach to Query-Focused Summarization" and BenchmarkQED research.
