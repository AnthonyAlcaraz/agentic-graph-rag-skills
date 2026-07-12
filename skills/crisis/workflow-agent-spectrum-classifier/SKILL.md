---
name: workflow-agent-spectrum-classifier
description: |
  Place an AI system on Ch1's continuous workflow-agent spectrum instead of
  the false binary "is it an agent or not". Scores the three dimensions of
  agency (autonomy / action / authority) plus how predefined the execution
  path is, returns a spectrum position (0 = workflow, 1 = agent) and a band
  (WORKFLOW / BLENDED / AGENT), applies Ch1's action test (a system that
  cannot effect change is an assistant/advisor, not an agent), and reports
  the four emergent capabilities (autonomous decision-making, contextual
  understanding, strategic tool utilization, memory persistence). Accepts
  numeric dimensions or a free-text system description. Use to right-size an
  architecture — deterministic workflow, blended human-in-the-loop, or full
  agent. NOT for ranking model quality, NOT for systems with no LLM in the
  loop.
osmani-pattern: Reviewer
ghosh-layer: Reasoning
chapter-source: "Agentic GraphRAG (O'Reilly) Ch1 — Defining Agentic AI — Classifying Agentic Systems: The Workflow-Agent Spectrum + the three dimensions of agency"
references:
  - "Andrew Ng — systems can be 'agent-like to different degrees'"
  - "Anthropic — the workflow-vs-agent distinction (predefined paths vs dynamically determined processes)"
---

# Workflow-Agent Spectrum Classifier

## Overview

Ch1 rejects "is it an agent or not" as the wrong question. Following Andrew Ng
("systems can be agent-like to different degrees") and Anthropic's
workflow-vs-agent distinction, it places systems on a **continuous spectrum**:

- **Workflow end** — "predefined execution paths: orchestrated sequences that
  follow explicit instructions." Reliable and deterministic, limited
  adaptability. Chapter examples: a FAQ generator, a fund-analysis app.
- **Agent end** — systems that "determine processes dynamically, providing
  flexibility at the cost of predictability." Chapter examples: coding agents,
  deep research agents.
- **Blended middle** — "deterministic workflows with nondeterministic LLMs
  inserted at key points," with humans in the loop where judgment is required.
  Chapter example: an investment firm's market-commentary report — the LLM
  retrieves, analyzes, and submits; humans review for compliance and submit to
  regulators.

The placement is grounded in the **three dimensions of agency**, which "exist
on sliding scales, not as binary attributes":

- **Autonomy** — degree of independent decision-making without external
  direction.
- **Action** — ability to execute decisions that affect the environment.
  "Without this capability to effect change, you have an assistant or advisor,
  not an agent."
- **Authority** — scope and limitations of permitted actions. (Ch1's
  real-estate-agent example: high autonomy to market a property, little
  authority over price.)

When a system operates across these dimensions, four capabilities emerge:
autonomous decision-making, contextual understanding, strategic tool
utilization, and memory persistence. The skill reports them alongside the
band.

## When to Use

- Right-sizing an architecture: deterministic workflow vs blended
  human-in-the-loop vs full agent
- Settling a "is this really an agent?" debate with a shared rubric
- Auditing whether a "read-only advisor" is being over-sold as an agent (the
  action test)
- Teaching the three agency dimensions with concrete placements

Phrases: "is this a workflow or an agent", "where on the spectrum", "classify
this system", "is it agentic", "workflow vs agent", "does this count as an
agent".

## When NOT to Use

- **Ranking model quality** — the spectrum is about system design, not the
  underlying model.
- **Non-LLM systems** with no autonomy/action to speak of — placement is
  trivially WORKFLOW and uninformative.
- **As an authority control.** This reports the authority *dimension*; it does
  not enforce permissions. Use `capability-authorization-gate` (Ch3) for that.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | autonomy / action / authority / determinism (0..1) | `lib.classify(...)` | spectrum position + band | position in 0..1; band matches cutoffs |
| 2 | autonomy + path_determinism | `lib.spectrum_position(...)` | 0..1 position | rises with autonomy, falls with determinism |
| 3 | action value | read `is_agent_by_action_test` | agent-vs-advisor gate | false when action < the agent threshold |
| 4 | autonomy + memory/tool/contextual signals | `lib.emergent_capabilities(...)` | four-capability checklist | flags reflect the supplied signals |
| 5 | free-text description | `lib.classify_text(text)` | placement + `estimated_dimensions` | dynamic-agent text -> not WORKFLOW; scripted text -> not AGENT |
| 6 | list of systems | CLI `batch` | per-system placement | each system carries a band + notes |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "It uses an LLM, so it's an agent." | Ch1: agency is a spectrum, not a label. A FAQ generator uses an LLM on a predefined path — it sits at the WORKFLOW end. Score autonomy and path determinism, don't assume. |
| "It reasons brilliantly, so it's a top-tier agent." | Ch1's action test: "Without this capability to effect change, you have an assistant or advisor, not an agent." A read-only diagnostic with high autonomy still fails the action test. |
| "This complex process must be a full agent." | Ch1: the most complex enterprise processes are BLENDED — "deterministic workflows with nondeterministic LLMs inserted at key points," humans in the loop. Full-agent framing removes the human judgment the process requires. |
| "Give it maximum autonomy and authority — more agentic is better." | Ch1: the dimensions are calibrated, not maximized (the real-estate agent has high autonomy, low pricing authority). Miscalibrated authority is a safety problem, not an agency win. |
| "The band is just cosmetic labeling." | The band drives the architecture in later chapters: WORKFLOW -> explicit deterministic edges, AGENT -> conditional adaptive edges (Ch1 GraphRAG Flexibility section). Misplacing the band mis-designs the graph. |

## Red Flags

- **A system scores AGENT but fails the action test.** It is an advisor sold as
  an agent; either grant it (bounded) action or stop calling it an agent.
- **Everything lands BLENDED.** Either the dimensions are all set near 0.5
  (under-specified) or the free-text description is too vague — supply concrete
  autonomy/action signals.
- **High autonomy paired with high authority and no human-in-the-loop note.**
  Verify this is intended; unbounded authority under high autonomy is the
  configuration Ch1 warns to calibrate.
- **`classify_text` disagrees with your intuition.** It is best-effort keyword
  inference; read `estimated_dimensions`, correct them, and re-run
  `classify` with the numeric values.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 8/8:
   - FAQ generator -> WORKFLOW, DevOps agent -> AGENT, market-commentary ->
     BLENDED
   - the read-only advisor fails the action test and carries the advisor note
   - position is monotonic in autonomy and determinism
   - emergent-capability flags reflect the supplied signals
   - free-text dynamic-agent text is not WORKFLOW; scripted text is not AGENT
2. **Verify CLI help.** `python cli.py --help` exits 0 and prints the SKILL.md
   description.
3. **Inspect the scenario.** `python cli.py scenario devops` should show the
   four DevOps systems spread across all three bands.

## Security Posture

- **Prompt injection.** Numeric `classify` has no text surface. `classify_text`
  and the `describe` subcommand read a free-text description with regex keyword
  matching only — no `eval`, no instruction execution — so a crafted
  description can at worst bias the estimated dimensions, which are returned
  transparently under `estimated_dimensions` for the caller to correct.
- **Data exfiltration.** No network calls; the only file read is the systems
  JSON path the caller supplies (default: the bundled sample). `--json` output
  goes to stdout.
- **Privilege escalation.** No shell invocation, no dynamic import, no file
  writes. Placement is advisory and must not be wired to real permission
  grants — the action/authority scores describe intent, they do not enforce it.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien), Chapter 1 —
Defining Agentic AI, "Classifying Agentic Systems: The Workflow-Agent
Spectrum" and the "three dimensions of agency" definition. The spectrum framing
follows Andrew Ng ("agent-like to different degrees") and Anthropic's
workflow-vs-agent distinction, both named in the chapter; the workflow /
blended / agent examples (FAQ generator, market-commentary report, coding &
deep-research agents) and the action test are the chapter's.
