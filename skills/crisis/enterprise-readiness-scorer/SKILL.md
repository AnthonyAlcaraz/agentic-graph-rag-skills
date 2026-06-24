---
name: enterprise-readiness-scorer
description: |
  Score a proposed or deployed enterprise agent against the architectural
  requirements Ch1 argues are non-negotiable: absence of the five fatal
  flaws of naive vector RAG (context amnesia / relationship blindness /
  temporal ignorance / reasoning paralysis / tool chaos), calibration of
  the three agency dimensions (autonomy / action / authority), presence of
  the four emergent capabilities, and the decision-trace test that
  separates a real context graph from a relabeled search index. Produces a
  0-100 score, a band (PRODUCTION-READY / PILOT-READY / PROTOTYPE /
  NAIVE-VECTOR), and a gap-closing recommendation per open flaw. Use before
  greenlighting an enterprise agent for production. NOT for ranking models
  (Ch1 says the flaws are architectural, not model-quality), NOT for
  consumer FAQ bots where vector RAG is a fine fit.
osmani-pattern: Reviewer
ghosh-layer: Workflow
chapter-source: "Agentic Graph RAG (O'Reilly) Ch1 — The Crisis of Enterprise Agentic AI — five fatal flaws + agency dimensions + agent capabilities + Enterprise Context Graphs section"
references:
  - "Singhal, 'Introducing the Knowledge Graph: things, not strings', Google 2012 (the strings-to-things shift)"
  - "Lilian Weng, 'LLM Powered Autonomous Agents', 2023 (LLM-as-brain: planning, memory, tool use)"
  - "Arvind Jain (Glean), 'Context Data Platform' — observe-real-work / structure-on-activity / continuously-learn"
  - "Kirk Marple (Graphlit) — the rejected-alternatives test for real context graphs"
---

# Enterprise Agentic-Readiness Scorer

## Overview

Ch1 opens with a promise and a trap. The promise: an agent that pursues
goals instead of answering questions. The trap: "you fire up your favorite
LLM, add it to your agentic framework of choice, and connect it to a
vector-based RAG system. Should be easy, right? Wrong." A naive
vector-only approach creates **five fatal flaws** that are not bugs but an
architectural failure preventing the system from becoming truly agentic.

This skill turns that diagnosis into a score. It checks four things the
chapter argues are required for enterprise agency:

1. **The five fatal flaws are cured.** Each flaw is cured only by a
   specific graph capability (context amnesia by evolving memory,
   relationship blindness by entity relationships, temporal ignorance by
   temporal evolution, reasoning paralysis by multi-hop reasoning, tool
   chaos by tool orchestration).
2. **The three agency dimensions are calibrated.** Autonomy, action, and
   authority are sliding scales, not binary — and Ch1's point is
   *calibration*, not maximization (a real-estate agent has high autonomy
   but deliberately low pricing authority).
3. **The four emergent capabilities are present.** Autonomous
   decision-making, contextual understanding, strategic tool utilization,
   memory persistence.
4. **The decision-trace test passes.** Per Marple's test in the Enterprise
   Context Graphs section: can the system tell you not just what happened,
   but what alternatives were considered and rejected?

## When to Use

- Before greenlighting an enterprise agent for production deployment
- Reviewing a vendor's "context graph" claim against the rejected-alternatives test
- Comparing a naive-vector prototype to a graph-augmented redesign
- Architecture review where someone proposes "just add a bigger vector store"

Phrases: "is this agent production-ready", "enterprise agentic readiness",
"score my RAG architecture", "are we naive vector RAG", "context graph vs
search index".

## When NOT to Use

- Ranking LLMs by quality — Ch1 is explicit that the flaws are
  architectural, not model-quality ("cannot be addressed by expanding
  context windows or refining embedding techniques")
- Consumer FAQ / support bots where queries map to a text snippet — Ch1
  names these as a great fit for plain vector RAG
- Single-turn Q&A with no actions, state, or temporal evolution

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | profile JSON (graph_capabilities map) | `lib.score_flaws(caps)` | (points, cured, open_flaws) | each flaw cured only by its mapped capability |
| 2 | profile JSON (agency map) | `lib.score_agency(agency)` | (points, missing dims) | scores coverage/calibration, not magnitude |
| 3 | profile JSON (capabilities map) | `lib.score_capabilities(caps)` | (points, missing) | proportional to capabilities present |
| 4 | captures_rejected_alternatives bool | `lib.decision_trace_test(b)` | (15 or 0, note) | binary test per Marple |
| 5 | full profile | `lib.assess(profile)` | score + band + recommendations | score bounded 0-100; band matches thresholds |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Our LLM is frontier-grade, so we are production-ready." | Ch1: the five flaws "aren't bugs. They represent an architectural failure" and "cannot be addressed by optimizing search or tweaking embedding models." Model quality does not cure an architecture gap. |
| "We have a vector store, that covers retrieval." | A vector store cures none of the five flaws by itself. Score it: all five stay open, band is NAIVE-VECTOR. The flaws are cured by graph capabilities, not by a vector index. |
| "We logged everything, so we have a context graph." | Marple's test (line 285): can it tell you what alternatives were *rejected*? Logging final states is read-time data. The decision-trace test is worth 15 points precisely to catch relabeled search indexes. |
| "Max out autonomy and authority for a powerful agent." | Ch1: agency dimensions are sliding scales and must be *calibrated*, not maximized. The real-estate agent has high autonomy, near-zero pricing authority. This scorer rewards calibration coverage, not magnitude. |

## Red Flags

- **Score is high but decision_trace is 0.** The agent may pass the
  capability checklist while recording only outcomes; it will become "a
  high-fidelity log of failure" if it ever hallucinates (Ch1 counter-thesis).
- **All five flaws open but band is not NAIVE-VECTOR.** Scoring bug —
  open flaws should dominate; recheck the FLAW_CURE mapping.
- **Agency magnitude drives the score.** Misreads Ch1: a deliberately
  low-authority agent is correct design, not a deficiency.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report:
   - all-open flaws score 0; all-cured score the full 40
   - each flaw cured only by its mapped graph capability
   - decision-trace test is binary 15/0
   - a perfect profile is exactly 100 and PRODUCTION-READY; empty is NAIVE-VECTOR
   - agency scores calibration coverage, not magnitude
2. **Verify CLI help.** `python cli.py --help` exits 0 and prints the SKILL.md description.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly) by Anthony Alcaraz & Julien
— Ch1: The Crisis of Agentic AI, specifically the five-fatal-flaws opening
(the naive-vector failure), the "Defining Agentic AI" agency dimensions and
capabilities, and the "Enterprise Context Graphs" decision-trace test.
Supporting references: Singhal 2012 (strings to things), Lilian Weng 2023
(LLM-as-brain), Arvind Jain / Glean context-data-platform, Kirk Marple /
Graphlit rejected-alternatives test.
