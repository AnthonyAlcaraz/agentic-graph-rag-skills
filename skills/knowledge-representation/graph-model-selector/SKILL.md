---
name: graph-model-selector
description: |
  Select a graph data model — labeled property graph (LPG) vs RDF vs
  hypergraph — by scoring REASONING REQUIREMENTS against five implementation
  features (formal reasoning, n-ary relations, performance, tool ecosystem,
  constraint expressiveness), per Ch3 "Evaluating Graph Models". Also models
  the n-ary -> hyperedge representation (Example 3-1: a prescription connecting
  doctor + patient + medication + dosage + date + condition as ONE hyperedge
  vs the 1-intermediate-node + N-edge reification an LPG/RDF forces). The
  chapter's rule: start from "what reasoning must my agents do?", not from the
  data. Use when choosing a graph backend for an agentic system, justifying a
  build-vs-buy or model choice, or deciding whether an n-ary fact needs a
  hyperedge. NOT for picking a specific vendor product (this picks the model
  class, not Neo4j-vs-Neptune), NOT for non-graph storage decisions, NOT when
  the org already mandates a model (just adopt it).
osmani-pattern: Inversion
ghosh-layer: Primitive
chapter-source: "Agentic GraphRAG (O'Reilly) Ch3 — Knowledge Representation — Graph Data Models / Evaluating Graph Models / N-ary relations (Example 3-1)"
references:
  - "Zhou et al., In-depth Analysis of Graph-based RAG in a Unified Framework (Ch3 four-stage framework)"
  - "Ch3 Example 3-1 hypergraph prescription; Example 3-2 PostgreSQL triples fallback"
---

# Graph Model Selector

## Overview

AI agents are only as intelligent as the knowledge structures you give them,
and the model you choose constrains what they can reason about. The chapter is
explicit: **start with your reasoning requirements, not your data.** Formal
logical inference (medical diagnosis) demands a different model than
traversal-heavy network analysis or many-entity events.

Three model classes, each with a characteristic profile:

- **Labeled property graph (LPG)**: fast traversals, mature ecosystem
  (Neo4j / Neptune / ArangoDB), flexible. Can only tell you what you explicitly
  programmed — no native inference.
- **RDF (subject-predicate-object triples)**: formal logical semantics enable
  native inference. Tell it `Disease1 causes Symptom1` and `Patient exhibits
  Symptom1` and it infers `Disease1` is a candidate diagnosis with no rule
  written. Slower; n-ary needs reification.
- **Hypergraph**: one hyperedge connects any number of entities, so n-ary
  relations are native — no auxiliary nodes. Ecosystem is immature.

The selector scores each model across the five features the chapter names
(formal reasoning, n-ary, performance, tool ecosystem, constraint
expressiveness) weighted by the caller's requirements, and surfaces a hybrid
recommendation when the top two are close (the chapter's "Putting it all
together" hybrid guidance).

The n-ary helper makes the trade-off concrete. A prescription
(`doctor + patient + medication + dosage + date + condition`) is one hyperedge
(`representation_cost.hypergraph_elements == 1`) but costs `1 + arity` elements
(one relation node + one edge per participant) under LPG or RDF reification.

## When to Use

- Choosing a graph backend model class for a new agentic system
- Justifying a build-vs-buy or LPG-vs-RDF-vs-hypergraph decision in a design doc
- Deciding whether a multi-entity fact warrants a hyperedge or reification

Phrases: "which graph model", "property graph vs RDF", "hypergraph", "n-ary
relation", "reification", "graph data model selection", "Neo4j vs RDF".

## When NOT to Use

- **Picking a specific product.** This selects the model class, not
  Neo4j-vs-TigerGraph-vs-Neptune. Vendor choice is downstream (see Ch3
  build-vs-buy six-factor list).
- **Non-graph storage.** If the data is genuinely tabular with no relationship
  reasoning, a relational store is correct.
- **An org-mandated model.** If finance mandates RDF/OWL or the platform is
  fixed, adopt it; the scoring is moot.
- **A single binary relationship.** Arity-2 facts don't need the n-ary helper;
  a plain labeled edge is fine.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Reasoning requirements (5 weights 0..3) | `lib.score_models(reqs)` | `[(model, score), ...]` sorted desc | weights * feature-scores, descending order |
| 2 | Same | `lib.recommend_model(reqs)` | `{recommended, scores, rationale, hybrid_recommended}` | RDF wins on formal, hypergraph on n-ary, LPG on perf+tooling |
| 3 | An n-ary fact as a `HyperEdge(type, nodes, attributes)` | `lib.representation_cost(edge)` | `{arity, hypergraph_elements=1, property_graph_elements=1+N, rdf_reified_triples=1+N}` | hypergraph cost is 1; others are 1+arity |
| 4 | Same hyperedge | `lib.reify_as_property_graph(edge)` | 1 intermediate node + N edges listing | `intermediate_nodes==1`, `auxiliary_edges==arity` |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Property graphs are popular, just use Neo4j for everything." | Popularity is the tool-ecosystem axis only. If the agent needs native inference (medical diagnosis, compliance), LPG forces you to hand-code every inference rule. The chapter's whole point: the model constrains reasoning — pick from requirements, not from market share. |
| "RDF does reasoning, so always pick RDF." | RDF pays in performance and n-ary complexity (reification). Traversal-heavy real-time analytics on RDF can be the wrong call. The five-feature scoring exists precisely so one axis doesn't dominate by default. |
| "I'll force this 6-entity prescription into binary edges — hyperedges are exotic." | `representation_cost` shows the bill: 1 relation node + 6 edges, and queries must traverse all of them to reconstruct the event. The hyperedge keeps semantic unity in one element. The chapter calls binary-forcing "artificial complexity." |
| "The selector said hybrid — that's a cop-out." | The chapter explicitly recommends hybrids ("a property graph for high-performance traversals combined with an RDF/OWL layer for formal reasoning"). When two axes both matter and no single model covers both, the hybrid IS the answer — record it as a conscious trade-off, not a non-decision. |
| "Skip the model question, use PostgreSQL triples (Example 3-2)." | Valid for retrieval-focused systems with predictable query patterns — the chapter says so. But for temporal reasoning, contradiction management, and incremental processing, dedicated graph models win. Score the requirements first; the PG-triples fallback is a deliberate choice, not a default. |

## Red Flags

- **All five requirement weights set to 3.** You have not actually prioritized
  — re-interview the use case. If everything is critical, nothing is, and the
  selector degenerates to the raw feature averages.
- **Recommended = RDF but performance weight is the highest.** Mismatch:
  re-check the weights. RDF's performance score is the lowest of the three.
- **Hybrid flagged but the team has no appetite for two systems.** Record the
  trade-off explicitly: pick the single model that covers the higher-weighted
  axis and accept the documented gap on the other.
- **Choosing hypergraph for a team with no hypergraph DB experience.** The
  ecosystem is immature; budget for custom tooling or reconsider.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 10/10:
   - RDF wins formal-only, hypergraph wins n-ary-only, LPG wins perf+tooling
   - n-ary cost: hypergraph = 1 element, LPG/RDF = 1 + arity
   - reification produces exactly 1 intermediate node + arity edges
   - hybrid surfaces on balanced formal+n-ary requirements
2. **Run the scenario.** `python cli.py scenario medical-diagnosis` recommends
   an inference-capable model and prints the n-ary prescription cost.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints this
   SKILL.md description (so any harness can discover the skill from --help).

## Security Posture

- **Prompt injection.** Inputs are requirement weights and hyperedge specs -
  pure data scored against fixed feature tables. Adversarial values (inflated
  weights, crafted attribute strings) can at most skew a recommendation; nothing
  in the input is executed or interpolated into a query.
- **Data exfiltration.** No network calls, no file writes. Hyperedge attributes
  may describe sensitive domain facts (the prescription example); they stay
  in-process and appear only in the stdout cost report the caller owns.
- **Privilege escalation.** No shell invocation, no eval, no dynamic import. The
  recommendation is advisory - it selects a model class on paper; provisioning
  an actual graph backend happens elsewhere under the platform's own controls.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien) Ch3 — Knowledge
Representation, sections "Graph Data Models", "Evaluating Graph Models" (the
five implementation features), and the n-ary discussion with Example 3-1
(hypergraph prescription). The four-stage graph-RAG framing is Zhou et al.,
"In-depth Analysis of Graph-based RAG in a Unified Framework", cited in the
same chapter. PostgreSQL-triples fallback: Example 3-2.
