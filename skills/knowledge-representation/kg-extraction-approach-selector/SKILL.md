---
name: kg-extraction-approach-selector
description: |
  Select a knowledge-graph EXTRACTION approach for a given source — structured
  database integration vs LLM-based triple extraction vs iText2KG (incremental)
  vs RAKG (document-level) — by scoring a SOURCE PROFILE against five features
  (handles unstructured text, incremental-friendly, document-level context,
  determinism, setup cost), per Ch3 "Extraction Approaches for Heterogeneous
  Sources". A structured source hard-routes to schema materialization; the
  `incremental-cost` helper makes the iText2KG win concrete (re-process only
  new documents, not the entire corpus). Use when picking how to ingest a
  source into an agent's knowledge graph. NOT for choosing the graph MODEL
  class (use graph-model-selector), NOT for vendor/product selection, NOT for
  temporal/bitemporal modeling (that is the ATOM discussion, out of scope
  here), NOT when the ingestion pipeline is already mandated.
osmani-pattern: Decision-Table
ghosh-layer: Primitive
chapter-source: "Agentic GraphRAG (O'Reilly) Ch3 — Building the Knowledge Graph — Extraction Approaches for Heterogeneous Sources (structured integration / LLM extraction / iText2KG incremental / RAKG document-level)"
references:
  - "iText2KG — incremental, topic-independent, schema-free KG construction with entity disambiguation (Ch3 'The incremental approach')"
  - "RAKG — Document-level Retrieval-Augmented Knowledge Graph construction; reported 96% accuracy, 88% entity coverage, 95% relationship fidelity (Ch3 'Document-level extraction')"
---

# KG Extraction Approach Selector

## Overview

An agent's knowledge comes from heterogeneous sources — relational databases,
documents, free text — and each source shape demands a different extraction
strategy. The chapter's rule: **the source and the reasoning need pick the
approach, not the other way round.** Forcing one extractor onto every source is
the failure this skill exists to prevent.

Four approaches, each with a characteristic profile:

- **Structured database integration**: the source already has a schema, so
  materialize it into nodes and edges (batch, CDC stream, or virtual graph
  views). Deterministic and high-precision — no LLM variance to validate.
  Only applicable when the source is genuinely structured.
- **LLM-based extraction**: prompt an LLM for ontology-constrained
  subject-predicate-object triples from free text. Simplest to stand up and
  flexible across topics, but non-deterministic; validate against the ontology
  and route low-confidence extractions to human review.
- **iText2KG (incremental)**: extract entities and relations section-by-section
  and disambiguate each against the prior set. A growing corpus is *extended*
  without re-processing what is already ingested, and no domain-specific schema
  is required.
- **RAKG (document-level)**: gather every text segment where an entity appears
  plus related subgraphs *before* generating relations. Whole-document context
  and hallucination filtering push relationship fidelity high, at the cost of
  retrieval infrastructure.

The selector scores each approach across the five features weighted by the
caller's source profile. A structured source is a categorical fact (you cannot
LLM-extract triples from a relational table), so it hard-routes to
materialization; everything else is decided by the weighted scores — an
unstructured + growing corpus routes to iText2KG, unstructured + whole-document
context routes to RAKG, and a one-shot unstructured pass routes to plain LLM
extraction.

The `incremental_cost` helper makes the iText2KG advantage concrete. Adding 50
documents to a 5000-document corpus: iText2KG processes 50; a full-rebuild
approach re-processes all 5000. The `savings_vs_rebuild` field is the
re-extraction a batch pipeline pays on every update.

## When to Use

- Choosing how to ingest a specific source into an agentic knowledge graph
- Justifying an incremental vs document-level vs one-shot extraction decision
- Estimating the re-processing cost of a growing corpus under each approach

Phrases: "how to extract this into the graph", "iText2KG vs RAKG", "incremental
KG construction", "document-level extraction", "extract triples from documents",
"structured database to graph".

## When NOT to Use

- **Choosing the graph model class.** Property-graph vs RDF vs hypergraph is a
  different decision — use `graph-model-selector`. This picks the *extractor*.
- **Vendor / product selection.** This picks the approach class, not
  Neo4j-APOC-vs-a-specific-ETL-tool.
- **Temporal / bitemporal modeling.** Separating observation time from validity
  periods is the ATOM discussion in the same chapter, out of scope for this
  four-way selector.
- **A mandated ingestion pipeline.** If the extraction path is already fixed,
  adopt it; the scoring is moot.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Source profile (source_type + 5 knobs) | `lib.score_approaches(profile)` | `[(approach, score), ...]` sorted desc | weights * feature-scores, descending order |
| 2 | Same | `lib.recommend_approach(profile)` | `{recommended, ranked, rationale, source_type}` | structured→structured_db; unstructured routes by dominant knob |
| 3 | `new_docs`, `total_docs`, `approach` | `lib.incremental_cost(...)` | `{docs_processed, docs_reprocessed, savings_vs_rebuild, ...}` | iText2KG processes new_docs; rebuild processes total_docs |
| 4 | A named scenario | `cli.py scenario growing-infra-telemetry` | recommendation + incremental cost | recommends iText2KG and prints the re-processing saving |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "LLMs extract from anything, just prompt one for every source." | For an already-structured source that discards deterministic precision and adds hallucination risk for zero benefit. The chapter integrates structured sources by materialization (APOC / CDC / virtual views), not by LLM triples. Match the extractor to the source. |
| "Re-run the whole extraction on every corpus update; simpler." | `incremental_cost` shows the bill: re-processing 5000 documents to add 50 is 100x wasted work, and LLM extraction is neither free nor deterministic across runs. iText2KG extends the graph and disambiguates against the prior set — that is the entire point of the incremental approach. |
| "iText2KG is incremental, so always pick it." | Incremental construction reasons within a section and disambiguates across sections; it does not gather every mention of an entity across a whole document the way RAKG does. When a relation depends on cross-document context, RAKG's retrieval-augmented grounding (higher relationship fidelity, hallucination filtering) is the right call. |
| "Document-level RAKG has the best benchmark numbers, use it everywhere." | RAKG's 96%/88%/95% come with retrieval infrastructure and per-entity context gathering — heavier setup than a one-shot LLM pass, and pointless on a structured source or a corpus that never needs whole-document context. High benchmark numbers on one axis do not make it the default. |
| "The source is a mix, so I can't decide." | Score the profile: a mixed source still handles unstructured text (weight 3), and the growth / document-context knobs route it exactly as an unstructured one would. Materialize the structured part, run the chosen LLM framework on the rest — record the split as a conscious decision. |

## Red Flags

- **source_type=structured but the profile weights unstructured handling.** A
  contradiction: a relational table is materialized, not LLM-extracted. Re-check
  the source classification before running the scorer.
- **iText2KG chosen for a one-shot batch that never grows.** Its incremental
  disambiguation machinery buys nothing if you extract once. Prefer plain LLM
  extraction and keep the setup cost low.
- **RAKG chosen with no retrieval layer budgeted.** Document-level grounding
  needs the mention-retrieval + subgraph-retrieval infrastructure; without it
  you are running plain LLM extraction with extra ceremony.
- **All extraction routed through one approach across every source.** The
  chapter is explicit that heterogeneous sources need heterogeneous strategies;
  a single-extractor pipeline is the anti-pattern.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 10/10:
   - structured→structured_db, unstructured+incremental→iText2KG,
     unstructured+doc-context→RAKG, unstructured one-shot→llm_extraction
   - mixed+incremental still routes to iText2KG
   - incremental_cost: iText2KG processes only new_docs, a rebuild processes
     total_docs, and savings equal `total_docs - new_docs`
   - all four approaches scored, ordered descending; feature set is the 5 axes
2. **Run the scenario.** `python cli.py scenario growing-infra-telemetry`
   recommends the incremental approach and prints the per-update saving.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints this
   SKILL.md description (so any harness can discover the skill from --help).

## Security Posture

- **Prompt injection.** The source profile is data-only knobs scored against
  fixed feature tables; adversarial values can at most skew the recommendation.
  The real injection surface is downstream: LLM/iText2KG/RAKG extraction runs
  prompts over untrusted documents, so the chosen pipeline - not this selector -
  must filter adversarial document content before extraction.
- **Data exfiltration.** No network calls, no file writes. Corpus statistics
  and source descriptions stay in-process; the report goes to stdout and the
  caller owns downstream piping.
- **Privilege escalation.** No shell invocation, no eval, no dynamic import.
  The recommendation is advisory - standing up the actual ingestion pipeline
  (DB credentials, retrieval infrastructure) happens elsewhere under the
  platform's own access controls.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien) Ch3 — Building the
Knowledge Graph, section "Extraction Approaches for Heterogeneous Sources":
structured database integration (graph materialization / virtual views / hybrid),
LLM-based extraction of ontology-constrained triples, and the two LLM
construction frameworks the chapter names — iText2KG (incremental,
topic-independent, schema-free with entity disambiguation) and RAKG
(document-level retrieval-augmented construction; reported 96% accuracy, 88%
entity coverage, 95% relationship fidelity). The temporal ATOM framework from the
same section is deliberately out of scope for this four-way selector.
