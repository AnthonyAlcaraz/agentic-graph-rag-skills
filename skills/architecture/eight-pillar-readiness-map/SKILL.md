---
name: eight-pillar-readiness-map
description: |
  Map an agentic-graph system's current capabilities across the eight pillars of
  Agentic GraphRAG Ch2 (knowledge representation, memory, reasoning, planning,
  tool orchestration, structured output, self-evolution, optimization), respect
  the chapter's layering (each pillar depends on the ones before it), flag
  dependency violations (a higher pillar claimed present while a lower one it
  requires is missing), report which of the five Chapter-1 flaws remain
  unsolved (per Table 2-1), and recommend the next pillar to build. Use when
  auditing an agent's production readiness or planning the build order. NOT for
  building any single pillar (each has its own chapter and skills), NOT for
  routing a request (that is dual-graph-router), NOT for a generic maturity
  model unrelated to the eight pillars.
osmani-pattern: Reviewer
ghosh-layer: Orchestration
chapter-source: "Agentic GraphRAG (O'Reilly) Ch2 — Architecture Foundations — The Eight Pillars of Agentic Graph Architecture + Table 2-1"
references:
  - "Ch2 'The Eight Pillars of Agentic Graph Architecture' — the pillars are layered, not independent; knowledge representation must come first; the final two (self-evolution, optimization) depend on the complete architecture"
  - "Ch2 Table 2-1 'Mapping the five flaws to the eight pillars' — relationship blindness -> knowledge representation; context amnesia + temporal ignorance -> memory; reasoning paralysis -> reasoning + planning; tool chaos -> tool orchestration + structured output"
  - "Ch2 'The Initial State' + 'The Transformation Arc' — the DevOps agent starts fragmented (representation problem, not technology problem) and gains one pillar-layer per part"
---

# Eight-Pillar Readiness Map

## Overview

The dual-graph architecture is the structural framework; the eight pillars are
the implementation roadmap — the specific capabilities that turn the framework
into a working system. Each pillar emerged from a recurring production failure
pattern, and the pillars are **layered, not independent**: knowledge
representation (Ch3) must come first because every other pillar depends on the
knowledge graph; memory (Ch4) builds on it; reasoning and planning (Ch5) require
both; tool orchestration (Ch6) requires all of those; and the final two,
self-evolution (Ch7) and optimization (Ch8), depend on the complete architecture
being in place.

This skill takes a system's declared capability per pillar (present / partial /
missing) and produces a readiness map:

- a **readiness score** (weighted across the eight pillars),
- **dependency violations** — a higher pillar claimed present while a lower one
  it requires is missing (the chapter says this is structurally unsound),
- **unresolved Chapter-1 flaws** — mapping remaining gaps back to the five flaws
  per Table 2-1 (relationship blindness, context amnesia, temporal ignorance,
  reasoning paralysis, tool chaos),
- the **next pillar** to build (always the earliest incomplete layer, because
  building higher first creates a violation).

The DevOps agent's Chapter-2 initial state is the worked example: knowledge
representation only partial (the data exists in logs and configs but is not a
graph), everything else missing, all five flaws open. It is a "representation
problem, not a technology problem."

## When to Use

- Auditing an agentic-graph system's production readiness
- Planning the build order for a new agent (which pillar next?)
- Checking that a claimed capability is not resting on a missing foundation
- Tracking progress across the book's parts (each part adds a pillar-layer)

Phrases that should invoke this skill: "map the eight pillars", "which pillar
should we build next", "is this agent production-ready", "pillar readiness",
"what flaws are still unsolved", "eight-pillar audit".

## When NOT to Use

- **Building a single pillar.** Each pillar has its own chapter and skills
  (`knowledge-representation/`, `memory/`, `reasoning-planning/`,
  `tool-orchestration/`, `self-evolution/`). This skill maps; it does not build.
- **Routing a request.** Vertical-vs-horizontal routing is `dual-graph-router`.
- **A generic org/AI maturity model.** The eight pillars are specific to the
  dual-graph architecture; do not repurpose this for unrelated capability grids.
- **Scoring the QUALITY of a pillar.** This tracks presence/partial/missing, not
  how good a present pillar is — use the pillar's own evaluation skills for that.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | capability dict {pillar: present\|partial\|missing} | `lib.assess(caps)` | `ReadinessReport` | unstated pillars default to missing; invalid status raises ValueError |
| 2 | statuses | `lib.dependency_violations(statuses)` | list of violations | a present/partial pillar with a missing required lower pillar is flagged |
| 3 | statuses | `lib.unresolved_flaws(statuses)` | list of open flaws | a flaw is solved only if a solving pillar is fully present |
| 4 | statuses | `lib.next_pillar(statuses)` | pillar key or None | the earliest not-present pillar in layer order |
| 5 | — | `lib.initial_state()` | the DevOps Chapter-2 starting capabilities | KR partial; all others missing |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "We built reasoning first because it is the interesting part — skip the graph for now." | The chapter is explicit: "Knowledge representation must come first because every other pillar depends on the knowledge graph." Reasoning present while KR missing is a dependency violation — the reasoning has nothing grounded to reason over. |
| "Self-evolution is the goal, let's jump to Chapter 7." | Self-evolution "depends on the complete architecture being in place." It reads the observation record produced by the harness that the earlier pillars build. Claimed present on an incomplete stack, it is a violation, not a capability. |
| "Tool orchestration solves tool chaos, so once we have it we are done with flaws." | tool_chaos also needs structured_output at the tool/node boundaries (the impedance-mismatch pillar). A present tool_orchestration with missing structured_output leaves tool_chaos only partially addressed. |
| "Partial on a pillar is basically present." | Partial means the flaw it targets is only partially addressed. The initial DevOps state has partial KR (data exists, unstructured) and still leaves relationship_blindness open — partial is not solved. |
| "We can build the pillars in any order our team prefers." | The pillars are layered by dependency, not preference. Building out of order produces the dependency violations this skill exists to catch; the recommended next pillar is always the earliest incomplete layer. |

## Red Flags

- **A high readiness score with dependency violations.** The weighted score can
  look healthy while the layering is broken — always read the violations list,
  not just the percentage.
- **Every flaw shows unsolved but pillars are marked present.** The
  status-to-flaw mapping drifted, or pillars were marked present without their
  dependencies — cross-check with the violations list.
- **next_pillar skips ahead of a missing lower pillar.** Impossible by
  construction; if you see it, `PILLAR_ORDER` or `depends_on` was edited
  incorrectly.
- **self_evolution or optimization shown as solving a flaw.** They map to
  production viability, not to any of the five flaws; a flaw mapping to them is
  a corruption of Table 2-1.
- **CLI `--help` exits non-zero.** SKILL.md / CLI mismatch; the multi-harness
  invariant is broken.

## Non-Negotiable Verification

1. **Run the benchmark battery.**
   ```
   python cli.py benchmark
   ```
   Confirm eight layered pillars, five mapped flaws, the initial state
   recommending knowledge_representation, the mid state solving the first four
   flaws while leaving tool_chaos open, and the violation state flagging
   reasoning + self_evolution as resting on a missing foundation.

2. **Inspect the initial state visually.**
   ```
   python cli.py assess --system initial
   ```
   Confirm KR is partial, all others missing, all five flaws unsolved, and the
   roadmap starts at knowledge_representation.

3. **Confirm the layering catches a violation.**
   ```
   python cli.py assess --system violation
   ```
   Confirm reasoning and self_evolution are flagged as claimed-present-but-
   foundation-missing.

4. **JSON output round-trips.**
   ```
   python cli.py assess --system mid --json | python -c "import json,sys; json.load(sys.stdin)"
   ```
   No exception means the CLI is harness-portable.

## Security Posture

- **Prompt injection.** Capability statuses are a small closed vocabulary
  (present/partial/missing) validated on input; any other value raises
  ValueError rather than being interpreted. Pillar keys are validated against
  the fixed eight; unknown keys raise. There is no free-text execution surface.
- **Data exfiltration.** No network calls, no file writes outside the read-only
  bundled `sample-systems.json`. The `--json` report goes to stdout; the caller
  owns downstream piping.
- **Advisory only.** This skill emits a report; it never edits the audited
  system, installs a pillar, or grants a capability. A readiness score is not an
  authorization — the dependency-violation output is the safety signal (do not
  ship a system whose claimed pillars rest on missing foundations).

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien),
Chapter 2 — Agentic Graph Architecture Foundations:

- "The Eight Pillars of Agentic Graph Architecture" — the eight pillars, their
  layering, and why each exists (a recurring production failure pattern).
- Table 2-1 "Mapping the five flaws to the eight pillars" — relationship
  blindness → knowledge representation; context amnesia + temporal ignorance →
  memory; reasoning paralysis → reasoning + planning; tool chaos → tool
  orchestration + structured output.
- "The Initial State" and "The Transformation Arc" — the DevOps agent's
  fragmented starting point and the pillar-per-part progression.

This Reviewer-pattern skill audits the whole architecture; the per-pillar skills
in the sibling chapter folders build the capabilities it maps.
