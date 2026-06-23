---
name: homoiconic-meta-schema
description: |
  Homoiconic knowledge representation (Ch3) — code and data share the same
  representation so an agent can inspect and modify its own knowledge structures
  with the same machinery it uses for regular data. Two constructs: (1) meta-
  knowledge structures (Example 3-6) where a metaschema describes what an
  EntityType is and entity-type definitions are stored AS DATA — this skill
  validates an entity-type against the metaschema AND validates a data instance
  against its entity-type using the SAME validator at both levels (the
  homoiconic property made operational); (2) executable knowledge patterns
  (Example 3-7) where operational rules live in the graph as Rule entities with
  condition + action — this skill parses the tiered WHEN/THEN/ELSE action,
  validates the rule, and evaluates it against facts (DetermineCustomerSegment:
  >20 -> Premium, >10 -> Regular, else Basic). Use when building self-evolving
  agents that reason about / modify their own schema, when storing business
  rules as queryable graph data instead of hidden application code, or when
  validating agent-proposed schema extensions. NOT for static schemas that never
  change (a plain class/struct is simpler), NOT for executing arbitrary code
  (this evaluates a constrained tiered-rule grammar, not a general interpreter),
  NOT for the schema PATTERN choice (use schema-pattern-selector).
osmani-pattern: Reviewer
ghosh-layer: Primitive
chapter-source: "Agentic Graph RAG (O'Reilly) Ch3 — Knowledge Representation — Homoiconic Knowledge Representation (Examples 3-6, 3-7)"
references:
  - "Ch3 Meta-knowledge structures (Example 3-6 metaschema + Person entity-type)"
  - "Ch3 Executable knowledge patterns (Example 3-7 DetermineCustomerSegment Rule)"
  - "Ch3 DevOps OperationalRule (homoiconic representation for agent adaptability)"
---

# Homoiconic Meta-Schema

## Overview

Agent-friendly knowledge graphs need **homoiconicity**: code and data in the
same representation, so agents can inspect and modify their own operational
logic. Ch3 gives two constructs.

**Meta-knowledge structures (Example 3-6).** A metaschema describes the schema
itself — it defines what an `EntityType` is (a name, a description, a list of
property definitions). Then domain knowledge is stored using the same
representation: a `Person` entity-type is just data with `name`, `birth_date`,
`occupation` properties. The syntax of schema and data is identical. This skill
runs the same validation at both levels: `validate_entity_type` checks a type
against the metaschema; `validate_data_against_type` checks an instance against
its type. Same machinery, two levels — that is the homoiconic property doing
real work. It lets agents reason about knowledge completeness, dynamically
update schemas as they learn, and self-evolve without external reprogramming.

**Executable knowledge patterns (Example 3-7).** Operational rules become
first-class graph entities. A `Rule` has descriptive metadata, a `condition`
(graph pattern match), and an `action` (tiered `WHEN ... THEN SET ...` /
`ELSE`). Because the rule is data, agents can reason about rules, not just
follow them — discover, modify, create rules, and explain decisions by citing
the rule. This skill parses the tiered action, validates the rule has a
parseable clause, and evaluates it in source order against facts
(`DetermineCustomerSegment`: 25 purchases -> Premium, 15 -> Regular, 3 ->
Basic). The DevOps `OperationalRule` (`ValidateProductionDeployment`) is the
same construct applied to infrastructure.

## When to Use

- Building agents that reason about or modify their own schema (Ch7 self-evolution)
- Storing business/operational rules as queryable graph data, not hidden code
- Validating agent-proposed schema extensions before applying them
- Representing the ontology itself as data the agent can query

Phrases: "homoiconic", "metaschema", "schema as data", "entity-type definition",
"executable knowledge", "rule as graph entity", "self-evolving schema",
"meta-knowledge".

## When NOT to Use

- **Static schemas.** If the schema never changes, a plain class/struct is
  simpler; homoiconicity pays off only when the agent modifies its own structure.
- **General code execution.** `evaluate_rule` interprets a constrained tiered
  WHEN/THEN/ELSE grammar, NOT arbitrary code. Do not treat it as an interpreter
  for untrusted input.
- **Schema PATTERN selection.** Use `schema-pattern-selector` to choose
  Event-Centric vs Multi-Perspective etc.; this validates the homoiconic
  meta-level and executable rules.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | entity-type definition dict | `lib.validate_entity_type(def)` | `{valid, errors}` | name required, property names unique, types valid |
| 2 | entity-type + data instance | `lib.validate_data_against_type(type, instance)` | `{valid, errors}` | required props present, value types match (same validator level) |
| 3 | Rule dict (name, condition, action) | `lib.validate_rule(rule)` | `{valid, errors, parsed_clauses}` | action must parse to >= 1 WHEN clause |
| 4 | action text | `lib.parse_action(text)` | `{when: [...], else: {...}}` in source order | tiered order preserved |
| 5 | Rule + facts dict | `lib.evaluate_rule(rule, facts)` | `{field: value}` or None | first matching WHEN by source order, then ELSE |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Schema and data are different things — keep the schema in code." | That is exactly the non-homoiconic system the chapter contrasts against. When schema lives in code, the agent cannot inspect or evolve it. Storing the entity-type AS DATA (Example 3-6) is what lets the agent reason about completeness and self-evolve. |
| "Business rules belong in application code, not the graph." | Then the agent can follow rules but never reason about them, modify them, or explain decisions by citing them. Example 3-7 makes rules first-class graph entities precisely to unlock those capabilities. Implicit procedural knowledge becomes explicit, queryable structure. |
| "I'll evaluate WHEN clauses in any order." | Tiered rules depend on source order: `>20 -> Premium` must be checked before `>10 -> Regular`, or 25 purchases wrongly matches Regular first. `parse_action` and `evaluate_rule` preserve order on purpose. |
| "Duplicate property names are harmless." | The chapter's AI-assisted ontology validation explicitly checks "property names are unique". Duplicates make the type ambiguous; the validator fails them. |
| "Skip data-instance validation — the type definition is enough." | The homoiconic value is that the SAME validator works at both levels. Validating instances against their type is what catches the missing-required-field and wrong-type errors before they corrupt the graph. |

## Red Flags

- **Entity-type passes but instances of it keep failing required-field checks.**
  The type declares fields the data pipeline never populates — the schema and the
  extractor disagree.
- **A Rule validates but `evaluate_rule` returns None for normal inputs.** The
  action clauses don't cover the input range and there's no ELSE — add a default
  tier.
- **WHEN clauses out of order in the source.** Tiered evaluation will match the
  wrong tier; reorder most-specific-first.
- **Agent proposes a schema extension with a property type outside the allowed
  set.** Reject and surface — unchecked types are how schema drift enters a
  self-evolving system.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 10/10:
   - valid Person type passes; missing-name, duplicate-property, invalid-type fail
   - data instance: required-present passes, missing-required and wrong-type fail
   - rule parses 2 WHEN + 1 ELSE; tiered eval gives 25->Premium, 15->Regular, 3->Basic
   - rule missing action fails
2. **Run the scenario.** `python cli.py scenario customer-segment` validates the
   Person type as data, validates an instance against it, and evaluates the
   segmentation rule across tiers.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints this SKILL.md
   description (CLAUDE.md CLI mandate).

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, forthcoming) Ch3 — Knowledge
Representation, section "Homoiconic Knowledge Representation": meta-knowledge
structures (Example 3-6, the metaschema + Person entity-type) and executable
knowledge patterns (Example 3-7, the DetermineCustomerSegment Rule). The DevOps
`OperationalRule` (`ValidateProductionDeployment`) in the chapter's "Homoiconic
Knowledge Representation for Agent Adaptability" section is the same construct
applied to infrastructure, feeding the Ch7 self-evolution work.
