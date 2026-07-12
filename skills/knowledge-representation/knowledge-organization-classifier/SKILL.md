---
name: knowledge-organization-classifier
description: |
  Classify an organizational vocabulary onto the Ch3 knowledge-organization
  spectrum — pick list -> taxonomy -> thesaurus -> ontology — by the structural
  features the spec actually exhibits, walking bottom-up so a partial ontology
  does NOT over-claim. Also validates that something claiming to be an ontology
  carries the five core components the chapter names (classes, subclasses,
  individuals, axioms, relationships) with no dangling parent/class references,
  and recommends the next-tier upgrade with the concrete feature to add.
  Use when auditing an existing taxonomy/vocabulary before integrating it into
  an agent knowledge graph, when deciding whether you need a full ontology or a
  simpler structure, or when validating an AI-assisted ontology draft. NOT for
  building the ontology content itself (that is domain modeling), NOT for the
  SKOS cross-vocabulary mapping step (exactMatch/broader/related — a different
  primitive), NOT for entity resolution (use three-graph-router's linkage gate).
osmani-pattern: Reviewer
ghosh-layer: Primitive
chapter-source: "Agentic GraphRAG (O'Reilly) Ch3 — Knowledge Representation — Knowledge Organization and Ontology Fundamentals"
references:
  - "Ch3 The knowledge organization spectrum (pick list / taxonomy / thesaurus / ontology)"
  - "Ch3 Ontology core components (classes, subclasses, individuals, axioms, relationships)"
  - "Ch3 Iterative ontology creation with AI assistance (structural validation: relationships reference existing nodes, identifying properties)"
---

# Knowledge Organization Classifier

## Overview

Nearly every enterprise needs an organizational vocabulary to standardize
terminology (customer vs client vs patron), preserve institutional knowledge,
and meet governance/compliance requirements. These vocabularies live on a
spectrum from simple to complex (Ch3):

- **Pick list** — controlled value list, no hierarchy (country list, currency
  codes).
- **Taxonomy** — parent-child hierarchy with predefined terms and synonyms
  (Transportation -> Bike, Bus, Car, Truck).
- **Thesaurus** — taxonomy plus generic associative ("related") relationships.
- **Ontology** — a graph/network of classes with object properties, expanded
  relationship types, scope notes, and inference. The chapter's argument for
  ontologies is **flexibility**: pick lists/taxonomies/thesauruses require
  reorganizing whole hierarchies to add instances; ontologies expand without
  structural disruption.

The classifier reads the structural features a spec exhibits and places it on
the spectrum, walking bottom-up so a partial structure (classes but no
properties) does not claim to be a full ontology. The ontology validator
enforces the five core components Ch3 names — **classes, subclasses,
individuals, axioms, relationships** — and the structural checks from the
AI-assisted-ontology section (subclasses reference existing parents,
relationships reference existing classes). The upgrade helper names the concrete
feature to add to reach the next tier.

## When to Use

- Auditing an existing taxonomy/vocabulary before integrating it into an agent KG
- Deciding whether the use case needs a full ontology or a simpler structure
- Validating an AI-assisted ontology draft before publishing it as a service
- Justifying an "upgrade to ontology" recommendation with the missing feature

Phrases: "knowledge organization spectrum", "pick list vs taxonomy",
"taxonomy vs ontology", "ontology core components", "is this a real ontology",
"controlled vocabulary audit", "validate ontology".

## When NOT to Use

- **Building ontology content.** This audits structure; authoring the actual
  classes/relationships is domain modeling with experts.
- **SKOS cross-vocabulary mapping.** `exactMatch` / `broader` / `related`
  between vocabularies is a separate step (Ch3 "Creating a Unified Semantic
  Foundation"); this classifies a single vocabulary's structure.
- **Entity resolution.** Linking records that refer to the same entity is the
  `three-graph-router` linkage gate, not this skill.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | feature spec dict (`has_hierarchy`, `has_synonyms`, `has_associative`, `has_classes`, `has_properties`, `has_inference`, `values`) | `lib.classify(spec)` | `{classification, spectrum_index, reasons}` | bottom-up walk; partial ontology classifies lower |
| 2 | same | `lib.recommend_upgrade(spec)` | `{current, next, action}` | names the concrete feature to add for the next tier |
| 3 | ontology dict (classes, subclasses, individuals, axioms, relationships) | `lib.validate_ontology_components(ont)` | `{valid, present, missing, errors}` | all five components required; valid only if none missing and no dangling refs |
| 4 | ontology with a subclass whose parent is unknown | `lib.validate_ontology_components(ont)` | error listing the unknown parent | enforces subclass->parent integrity |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "It has classes, so it's an ontology — call it done." | Classes alone are not an ontology. Ch3 requires five components (classes, subclasses, individuals, axioms, relationships) plus object properties and inference. The classifier walks bottom-up precisely so classes-without-properties does not over-claim ontology status. |
| "A taxonomy is good enough, ontologies are overkill." | Sometimes true — pick the simplest tier the use case needs. But the chapter's flexibility argument matters: taxonomies require reorganizing whole hierarchies to add instances, ontologies expand without disruption. If the vocabulary will scale and evolve, the upgrade pays off. The classifier just makes the choice explicit. |
| "Dangling subclass parents and relationship endpoints are fine, the meaning is obvious." | The AI-assisted-ontology validation in Ch3 explicitly checks that "relationships reference existing nodes". A subclass whose parent doesn't exist, or a relationship pointing at a non-existent class, is a structural defect the validator must catch before the ontology is trusted by an agent. |
| "Axioms are academic — skip them." | Axioms codify domain truths and constraints (Cancer subclassOf Disease; a patient has at most one primary physician). Without them the ontology is a labeled graph, not a reasoning substrate. The validator lists axioms as a required core component. |
| "I'll classify a partial ontology as an ontology to look further along." | Over-claiming hides the missing features. The classifier reports the true tier and the upgrade action so the gap is visible, not papered over. |

## Red Flags

- **Spec classified as ontology but `has_inference` and `has_associative` both
  false.** Misclassification risk — re-check the feature flags; an ontology
  needs expanded relationships or inference.
- **`validate_ontology_components` returns `missing: [individuals]` for every
  draft.** The ontology defines structure but has no instance data — fine for a
  schema, but it is not yet operational for agent reasoning.
- **Many `unknown parent` / `unknown class` errors.** The vocabulary was merged
  from sources without alignment; harmonize class hierarchies before trusting it.
- **Everything classifies as pick_list.** The specs lack hierarchy flags —
  likely the feature extraction is incomplete, not that every vocabulary is flat.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 10/10:
   - each spectrum tier classifies correctly; partial ontology does not over-claim
   - spectrum indices are monotonic pick_list < taxonomy < ontology
   - complete 5-component ontology validates; missing-axioms and unknown-parent fail
   - upgrade chains pick_list -> taxonomy
2. **Run the scenario.** `python cli.py scenario healthcare-ontology` classifies
   currency codes / a transportation taxonomy and validates a healthcare ontology
   plus a broken one.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints this SKILL.md
   description (so any harness can discover the skill from --help).

## Security Posture

- **Prompt injection.** Vocabulary specs and ontology drafts are untrusted
  input - often AI-generated. The classifier reads fixed boolean/list keys
  against a fixed spectrum; adversarial flags can over-claim a tier but never
  execute. Scope notes and class names are treated as opaque strings, not
  instructions.
- **Data exfiltration.** No network calls, no file writes. Vocabulary content
  may encode internal business structure; it stays in-process and appears only
  in the stdout report the caller owns.
- **Privilege escalation.** No shell invocation, no eval, no dynamic import. A
  passing validation is advisory - it does not publish the ontology; an
  AI-drafted ontology still needs expert review before agents reason over it.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien) Ch3 — Knowledge
Representation, section "Knowledge Organization and Ontology Fundamentals": "The
knowledge organization spectrum" (pick list / taxonomy / thesaurus / ontology)
and "Ontology core components" (classes, subclasses, individuals, axioms,
relationships). The structural validation checks (relationships reference
existing nodes; entities have identifying properties) are from "Iterative
ontology creation with AI assistance".
