---
name: three-graph-router
description: |
  Route an incoming record/fact into the correct graph of the Three-Graph
  Architecture (Ch3) — DOMAIN (trusted, entity-resolved single source of
  truth), LEXICAL (verbatim source text with provenance, the "retrieval" in
  RAG), or SUBJECT (LLM-extracted artifacts kept SEPARATE from domain until
  entity resolution links them). The router enforces the boundaries that make
  the architecture work — an extraction can NEVER be written straight into the
  domain graph; it must enter subject and link via CORRESPONDS_TO above a
  confidence threshold (default 0.85). Use when ingesting
  mixed structured + unstructured data into an agent knowledge graph, when
  designing the separation between trusted and extracted knowledge, or when
  preventing extraction errors from contaminating ground truth. NOT for
  single-source trusted data (no separation needed), NOT for the entity-
  resolution matching algorithm itself (this gates the link; a real matcher
  swaps in at the seam), NOT for graph storage/query engine choice.
osmani-pattern: Inversion
ghosh-layer: Workflow
chapter-source: "Agentic GraphRAG (O'Reilly) Ch3 — Knowledge Representation — The Three-Graph Architecture for Agent Knowledge"
references:
  - "Ch3 Three-Graph Architecture (domain / lexical / subject), Figure 3-2"
  - "Ch3 Entity Resolution and Linking Across Graphs (CORRESPONDS_TO, Jaro-Winkler thresholds 0.95/0.85/0.75)"
---

# Three-Graph Router

## Overview

Real agentic systems integrate trusted structured data (CSVs, databases) with
untrusted extracted data (documents, reviews). Merging them into one graph is
the failure: unverified information pollutes trusted data, provenance is lost,
extraction errors cascade, and validating agent reasoning becomes impossible.

The Three-Graph Architecture solves this by separating knowledge on **origin,
certainty, and semantic role**:

- **Domain graph** — trusted, curated, entity-resolved. The canonical product
  list, the definitive org hierarchy. High certainty, stable IDs, protected
  from contamination.
- **Lexical graph** — original unstructured text in structured form. Document
  and Chunk nodes, immutable, complete provenance (every chunk links back to
  its source). This is the "retrieval" in RAG.
- **Subject graph** — entities/facts an LLM extracted from the lexical graph,
  kept SEPARATE from domain until entity resolution establishes confident
  links. Extraction artifacts with explicit uncertainty (confidence, model
  version, timestamp).

The router refuses the boundary violations that quietly destroy the
architecture: raw text without provenance is refused from the lexical graph,
extractions without a confidence score are refused from the subject graph, and
an extraction is never written straight into the domain graph. The critical
operation is entity resolution: a subject entity
links to a domain entity via `CORRESPONDS_TO` only when similarity clears a
confidence threshold (default 0.85; 0.95 high-stakes, 0.75 exploratory). The
worked example: a review mentions "the Stockholm chair", the system extracts a
`Subject_Product`, finds `Product(PROD_12345, "Stockholm Chair")` in the domain
graph, and links them if similar enough — enabling the cross-graph query
`domain -> CORRESPONDS_TO -> subject -> EXTRACTED_FROM -> lexical` with full
provenance.

## When to Use

- Ingesting mixed structured + unstructured sources into one agent knowledge base
- Designing the trusted-vs-extracted separation for a graph RAG system
- Preventing LLM extraction errors from contaminating a system of record
- Implementing the CORRESPONDS_TO linkage between extracted and canonical entities

Phrases: "three-graph", "domain/lexical/subject graph", "CORRESPONDS_TO",
"entity resolution linkage", "keep extractions separate", "provenance",
"trusted vs extracted knowledge".

## When NOT to Use

- **Single trusted source.** If all data is curated and entity-resolved, it all
  lives in the domain graph; the separation buys nothing.
- **The matching algorithm itself.** This skill GATES the link with a threshold;
  the actual embedding/Jaro-Winkler matcher is a swappable seam, not this skill's
  job.
- **Graph storage/query engine selection.** Use `graph-model-selector` for the
  model class; this routes records, it does not pick Neo4j-vs-RDF.
- **Append-only logs with no notion of "trusted".** No domain/subject split
  applies.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | `Record(payload, origin, entity_resolved, has_provenance, confidence)` | `lib.route(record)` | `{graph, label_suffix, reasons, requires_resolution}` | structured+resolved->domain; raw_text+provenance->lexical; extraction+confidence->subject |
| 2 | raw_text record without provenance | `lib.route(record)` | raises `ValueError` | lexical graph requires provenance — refuses silent insert |
| 3 | extraction record without confidence | `lib.route(record)` | raises `ValueError` | subject graph requires uncertainty metadata |
| 4 | extraction marked `entity_resolved=True` | `lib.route(record)` | raises `ValueError` | extractions never enter domain directly |
| 5 | subject name + `{domain_id: name}` candidates + threshold | `lib.link_subject_to_domain(...)` | `Correspondence(subject_id, domain_id, similarity, linked, threshold)` | links only if best similarity >= threshold |
| 6 | start graph + target graph | `lib.cross_graph_query_path(start, target)` | edge-type sequence | domain->lexical = [CORRESPONDS_TO, EXTRACTED_FROM] |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Just merge everything into one graph — the separation is overhead." | The chapter names the exact failures: unverified info pollutes trusted data, provenance is lost, extraction errors cascade, validation becomes impossible. The separation is the entire value proposition; merging is the anti-pattern the architecture exists to prevent. |
| "The LLM extracted it with 0.9 confidence, write it straight to the domain graph." | No. Confidence is not entity resolution. The extraction is a SUBJECT artifact until CORRESPONDS_TO links it to a canonical domain entity. `route` raises if you try to mark an extraction `entity_resolved` and skip the subject graph. The domain graph is the single source of truth precisely because extractions cannot bypass resolution. |
| "Provenance on lexical chunks is bookkeeping I can skip." | Provenance is what lets the agent cite the exact source passage and lets analysts audit retrieval quality. The chapter lists "complete provenance" as a defining lexical characteristic. `route` refuses provenance-less raw_text on purpose. |
| "I'll set the CORRESPONDS_TO threshold to 0.5 so more links form." | 0.5 floods the domain graph with false links — the conflation error the chapter warns is as damaging as fragmentation. Defaults: 0.95 high-stakes, 0.85 standard, 0.75 exploratory. Lowering it is a deliberate, documented precision/recall trade-off, not a default. |
| "Re-extracting the subject graph is dangerous — it'll change my data." | The opposite: because subject is separate from domain, you re-extract subject from the immutable lexical graph as models improve, and the domain graph is untouched. The separation is what makes re-extraction safe. |

## Red Flags

- **Many extractions routed with `requires_resolution=False`.** Bug — every
  subject entity needs resolution before it can be trusted as domain.
- **`link_subject_to_domain` linking almost everything.** Threshold too low;
  you are conflating distinct entities. Raise it and re-audit.
- **`link_subject_to_domain` linking almost nothing.** Threshold too high OR the
  similarity stub is wrong for the domain — swap in the real matcher at the seam.
- **Domain graph node count growing on every ingestion run.** Extractions are
  leaking into domain. Verify `route` is the only write path to domain and that
  it rejects extraction origins.
- **Lexical chunks with no source-document edge.** Provenance broken; agent
  citations become unverifiable.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 10/10:
   - each origin routes to the correct graph
   - provenance-less raw_text, confidence-less extraction, and
     extraction-marked-resolved all RAISE (boundary enforcement)
   - linkage respects the threshold and picks the best candidate
   - cross-graph path is correct
2. **Run the scenario.** `python cli.py scenario stockholm-chair` routes all
   three record types and shows the CORRESPONDS_TO link forming.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints this SKILL.md
   description (so any harness can discover the skill from --help).

## Security Posture

- **Prompt injection.** Records are untrusted by design - subject-graph
  extractions come from adversarial documents. The router never executes
  payload content; its refusal rules ARE the defense that keeps injected
  extractions out of the trusted domain graph. The attack to resist is
  threshold-lowering or marking extractions entity_resolved to bypass the gate.
- **Data exfiltration.** No network calls, no file writes. Record payloads and
  provenance metadata stay in-process; routing decisions go to stdout and the
  caller owns downstream piping.
- **Privilege escalation.** A CORRESPONDS_TO link is the escalation surface: it
  promotes extracted data toward trusted status. The gate links only above the
  confidence threshold, and no code path writes an extraction directly to
  domain - keep those invariants when swapping in a real matcher at the seam.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien) Ch3 — Knowledge
Representation, section "The Three-Graph Architecture for Agent Knowledge"
(domain / lexical / subject graphs, Figure 3-2) and "Entity Resolution and
Linking Across Graphs" (the CORRESPONDS_TO three-stage linking pipeline and the
0.95 / 0.85 / 0.75 Jaro-Winkler thresholds). The Stockholm-chair worked example
is the chapter's own illustration of subject-to-domain resolution.
