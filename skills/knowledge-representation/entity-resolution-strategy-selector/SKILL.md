---
name: entity-resolution-strategy-selector
description: |
  Choose HOW to decide when two records are the same real-world entity —
  EVIDENCE-BASED resolution (deterministic feature-by-feature scoring with
  explainable evidence and culturally-robust rules) vs GENERALIZATION-BASED AI
  (LLM statistical similarity, nondeterministic, post-hoc rationalization) —
  per Ch3 "Entity Resolution: The Foundation of Agent Knowledge". Scores a
  requirement profile (high_stakes, adversarial channel-separation,
  explainability, determinism, cultural_variation, training_examples) and picks
  evidence-based, generalization-AI, or a hybrid. Ships a deterministic matcher
  that scores name/address/phone similarity into an explainable confidence with
  evidence metadata (the chapter's "89% because NAME 87%, ADDRESS 100%, PHONE
  95%"), classifies the resulting graph edge (RESOLVED / POSSIBLY_RELATED /
  DISCLOSED), and flags the three edge cases naive matching misses. Use when
  standing up entity resolution for an agent knowledge graph, justifying an
  evidence-vs-LLM choice for identity/compliance/fraud work, or auditing a
  proposed merge. NOT for the extraction stage that produces the records (that
  is upstream KG construction), NOT for picking a specific ER product
  (Senzing-vs-build), NOT for arity-2 relationship modeling (use
  graph-model-selector).
osmani-pattern: Inversion
ghosh-layer: Primitive
chapter-source: "Agentic Graph RAG (O'Reilly) Ch3 — Knowledge Representation — Entity Resolution: The Foundation of Agent Knowledge / Evidence-based resolution vs generalization-based AI / Entity resolution as graph building blocks / Edge cases"
references:
  - "Ch3 evidence-vs-generalization distinction (deterministic + explainable + culturally-robust + calibrated vs nondeterministic + post-hoc)"
  - "Ch3 channel-separation fraud scenario (one launderer, engineered aliases)"
  - "Ch3 edge-type building blocks (RESOLVED / POSSIBLY_RELATED / DISCLOSED); edge cases (honorifics, near-identical, address normalization)"
---

# Entity Resolution Strategy Selector

## Overview

Entity resolution determines when two data records refer to the same
real-world entity — the cornerstone that lets an agent maintain a coherent
worldview across fragmented systems. If the agent cannot decide when two
references are the same entity, its whole reasoning framework collapses: the
graph either conflates distinct entities or fragments a single one.

The chapter draws one decisive distinction, and this skill turns it into a
selection:

- **Evidence-based resolution** examines specific features, applies
  domain-specific matching rules, and builds a case from concrete evidence. It
  is **deterministic** (same input, same output), **explainable** (every match
  cites which features drove it and their scores), **culturally robust**
  (explicit rules handle Arabic / Chinese / Russian naming), and **calibrated**
  (confidence reflects actual match accuracy).
- **Generalization-based AI** (an LLM) infers from statistical similarity
  learned in training. It is **nondeterministic**, its explanations are
  **post-hoc rationalizations**, it **breaks on non-Western names**, and its
  confidence is **not tied to accuracy**.

Evidence-based wins for identity, compliance, high-stakes, and adversarial
work. The sharp case is **channel separation**: a money launderer appears as
Bob Jones, then Bob R. Smith II at the same address with different phone
formatting, then Robert Smith Jr. elsewhere with overlapping contact details —
each variation engineered to pass fuzzy filters while looking distinct. Simple
string matching fails catastrophically; what wins is consolidating fragmented
identities on evidence from multiple overlapping features.

The selector scores a requirement profile across the six factors the chapter
names and returns evidence-based, generalization-AI, or a hybrid (LLM for
cheap candidate generation, evidence-based for the auditable final decision).
The matcher makes the trade-off concrete: it scores name/address/phone
similarity, aggregates to an explainable confidence with per-feature evidence,
classifies the graph edge (RESOLVED / POSSIBLY_RELATED / DISCLOSED), and flags
the three edge cases that require domain and cultural knowledge.

## When to Use

- Standing up entity resolution for an agent knowledge graph and deciding the
  resolution strategy
- Justifying evidence-based vs LLM matching in a design doc for identity,
  compliance, or fraud work
- Auditing a proposed merge: what confidence, on what evidence, and is it an
  edge case?

Phrases: "entity resolution", "record linkage", "deduplication", "are these
the same entity", "evidence-based vs LLM matching", "channel separation",
"RESOLVED edge", "match confidence explainability".

## When NOT to Use

- **The extraction stage.** Producing the records (LLM triple extraction,
  iText2KG / RAKG / ATOM construction) is upstream; this skill decides identity
  once records exist.
- **Picking a specific ER product.** This chooses the *strategy* and gives a
  reference matcher, not Senzing-vs-build. Vendor choice is downstream.
- **Arity-2 relationship modeling.** Whether a fact needs a hyperedge is the
  `graph-model-selector` skill; this one is about identity, not structure.
- **A domain with no identity stakes.** Genuinely low-stakes fuzzy dedup with
  abundant labeled examples and no compliance need can use generalization-AI —
  the selector will say so.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Requirement profile (6 weights 0..3) | `lib.score_strategies(profile)` | `[(strategy, score), ...]` sorted desc | weights * factor-affinities, descending order |
| 2 | Same | `lib.recommend_strategy(profile)` | `{recommended, scores, rationale, hybrid_recommended}` | evidence-based wins high-stakes/adversarial; generalization-AI wins example-rich low-stakes; hybrid when mixed |
| 3 | Two records `{name, address, phone}` | `lib.resolve_match(a, b, weights)` | `{confidence, edge_type, features_used, evidence[]}` | confidence == sum of per-feature contributions; evidence names which features drove it |
| 4 | A match confidence (or `declared=True`) | `lib.classify_edge(conf, declared)` | `{edge_type, confidence, reason}` | >=0.85 RESOLVED, >=0.5 POSSIBLY_RELATED, else NO_MATCH; declared -> DISCLOSED |
| 5 | Two records | `lib.flag_edge_cases(a, b)` | list of `{case, warning, action}` | catches honorific-same-entity, near-identical-different-entity, address-same-location |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Just ask an LLM if these two records are the same person." | For identity, compliance, and fraud the LLM's answer is nondeterministic, its explanation is a post-hoc rationalization, and its confidence does not reflect accuracy. When a wrong merge denies a mortgage or voids a ballot, the org ends up in court. Evidence-based scoring is deterministic and cites the evidence. |
| "Fuzzy string matching on each field is good enough." | It fails catastrophically under channel separation — variations are *engineered* to defeat per-attribute fuzzy filters. The win is channel consolidation from evidence across multiple overlapping features, not any single field. |
| "These names are almost identical, so merge them." | `flag_edge_cases` catches near-identical-different-entity: John R Smith vs John E Smith differ by one letter that may mean father-and-son. High string similarity is a reason for caution, not a merge; the action is do-not-merge-without-evidence. |
| "These names look totally different, so they're different people." | Wrong the other way: al-Hajj Abdullah Qardash and Abu Abdullah Qardash bin Amir look different as strings but are the same person once honorifics and Arabic naming conventions are handled. Cultural robustness is exactly where generalization-AI breaks. |
| "The selector said hybrid — pick one and move on." | Hybrid is a real pattern: generalization-AI cheaply proposes candidate pairs (blocking), evidence-based makes the final auditable decision. Record it as a conscious trade-off, not a non-decision. |
| "Confidence is confidence; I don't need the per-feature breakdown." | Evidence metadata (which features matched and their scores) is what makes the match explainable and auditable. "89% because NAME 87%, ADDRESS 100%, PHONE 95%" is defensible; a bare 89% is not. |

## Red Flags

- **All six profile weights set to 3.** You have not prioritized. If every
  concern is critical the selector degenerates to raw affinity sums — re-interview
  the use case.
- **Generalization-AI recommended while adversarial or high-stakes is weighted.**
  Mismatch: re-check the weights. Generalization-AI scores 0 on those axes by
  construction.
- **RESOLVED edge created on a single feature.** Channel-separation resistance
  comes from *overlapping* features. A match driven by name alone is fragile —
  demand corroborating evidence.
- **Merging on a near-identical pair without checking edge cases.** Run
  `flag_edge_cases` first; a one-character difference can be a distinct entity.
- **Trusting an LLM confidence score as calibrated.** It reflects statistical
  regularity, not match accuracy — do not threshold merges on it.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 10/10:
   - adversarial high-stakes picks evidence-based; example-rich low-stakes picks
     generalization-AI; mixed flags a hybrid
   - identical records resolve at 1.0 and classify RESOLVED
   - `resolve_match` emits per-feature evidence and the confidence equals the
     summed contributions
   - edge thresholds hold and `declared=True` overrides to DISCLOSED
   - all three edge cases (honorifics / near-identical / address) fire on the
     chapter's examples
2. **Run the scenario.** `python cli.py scenario fraud-channel-separation`
   recommends evidence-based and consolidates the engineered aliases with
   per-feature evidence.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints this
   SKILL.md description (CLAUDE.md CLI mandate).

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, forthcoming) Ch3 — Knowledge
Representation, section "Entity Resolution: The Foundation of Agent Knowledge"
and its subsections: "Why traditional approaches fail" (channel-separation
fraud), "Evidence-based resolution vs generalization-based AI" (the deterministic
/ explainable / culturally-robust / calibrated distinction and the "89% because
NAME 87%, ADDRESS 100%, PHONE 95%" example), "Entity resolution as graph
building blocks" (RESOLVED / POSSIBLY_RELATED / DISCLOSED edge types and
evidence metadata), and "Edge cases" (honorific same-entity, near-identical
different-entity, address same-location). The feature-scoring, edge
classification, and edge-case detection here are a self-contained stdlib
reference implementation of those ideas, not production ER tooling.
