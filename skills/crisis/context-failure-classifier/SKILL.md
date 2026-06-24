---
name: context-failure-classifier
description: |
  Classify an observed agent symptom into Ch1's context-failure taxonomy.
  Given a sentence describing what an agent did wrong, name the agent-level
  failure mode (action blindness / memory fragmentation / planning paralysis
  / context drift / tool chaos), the architectural root cause among the five
  fatal flaws, and the curing graph capability. Batch mode aggregates a
  post-mortem's symptoms into a prioritized cure list, surfacing Ch1's
  cascade point — that the failure modes reinforce one another. Use to
  triage why an enterprise agent is failing and decide what to build next.
  NOT for general bug triage (it only knows retrieval/context failures), NOT
  for model-quality issues (Ch1: the flaws are architectural, not the model).
osmani-pattern: Reviewer
ghosh-layer: Reasoning
chapter-source: "Agentic Graph RAG (O'Reilly) Ch1 — The Crisis — five fatal flaws (lines 9-15) + Consequences for vector-based agents (lines 159-168)"
references:
  - "Microsoft 'From Local to Global: A GraphRAG Approach to Query-Focused Summarization' (local vs global query failure)"
  - "Anthropic 'Effective Context Engineering for Agents' (bloated tool sets / tool-chaos failure mode)"
---

# Context-Failure-Mode Classifier

## Overview

Ch1 argues the symptoms enterprises see — an agent that breaks
dependencies, forgets, reverts to dead configs, can't connect facts,
guesses the wrong API — are not independent bugs. They are the surface of
**five fatal flaws** of naive vector RAG, and at the agent level each flaw
"compounds into agent failure," "reinforcing others, creating a cascade of
agent incompetence."

This skill maps a free-text symptom to that taxonomy. It answers three
questions for each symptom:

1. **Which agent-level failure mode is this?** Action blindness, memory
   fragmentation, planning paralysis, context drift, or tool chaos.
2. **What is the architectural root cause?** One of the five fatal flaws.
3. **What cures it?** The specific graph capability (entity relationships,
   evolving memory, temporal evolution, multi-hop reasoning, tool
   orchestration).

Batch mode reads a list of symptoms (e.g. a post-mortem's bullets) and
returns a cure list ordered by how many symptoms each cure resolves —
operationalizing Ch1's claim that closing one root flaw often relieves
several symptoms because they cascade.

## When to Use

- Triaging why a deployed enterprise agent produces wrong / unsafe outputs
- Turning a post-mortem's narrative into a prioritized architecture backlog
- Deciding which graph capability to build first given observed failures
- Teaching the difference between symptom (agent behavior) and root cause
  (architecture)

Phrases: "why did my agent break dependencies", "agent forgot context",
"classify this failure", "agent reverted to old config", "agent picked the
wrong tool", "what should we fix first".

## When NOT to Use

- General software bug triage — this taxonomy only covers retrieval/context
  failures
- Model-quality complaints (hallucination from a weak model, refusals) —
  Ch1 is explicit the five flaws are architectural, not model quality
- Latency / cost / infra incidents with no context-failure behavior

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | one symptom sentence | `lib.classify(symptom)` | primary mode + root flaw + cure + candidates | matched signals justify the chosen mode |
| 2 | symptom with multiple signals | `lib.classify(symptom)` | `cascade_modes` populated | secondary modes surfaced (the cascade) |
| 3 | list of symptoms | `lib.classify_batch(list)` | per-symptom + aggregate | flaw counts sum to classified count |
| 4 | aggregate | read `prioritized_cures` | cures ordered by symptom coverage | top cure resolves the most symptoms |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "These are five separate bugs, fix them one at a time." | Ch1: "Each failure mode reinforces others, creating a cascade of agent incompetence." The classifier surfaces cascade_modes so you fix the shared root flaw, not five symptoms. |
| "The agent hallucinated; we need a better model." | Ch1: the flaws "cannot be addressed by optimizing search or tweaking embedding models." If the symptom matches the taxonomy, the cure is a graph capability, not a model upgrade. |
| "It picked the wrong tool because the prompt was bad." | Anthropic's failure mode (Ch1 line 85): bloated tool sets where "a human engineer can't definitively say which tool should be used." That is tool_chaos, cured by tool orchestration, not by prompt polishing. |
| "Just retrieve more chunks and it'll connect the facts." | Planning paralysis comes from the associativity gap — transitive relationships "simply don't exist in isolated embeddings" (Ch1 line 146). More chunks don't create the missing edges. |

## Red Flags

- **A real context-failure symptom returns unclassified.** Re-state it in
  behavioral terms (what the agent *did*), not infrastructure terms; the
  classifier keys on observed behavior.
- **Everything classifies as one mode.** Either the symptoms genuinely
  share a root flaw (legitimate, check the cascade), or the symptom text is
  too generic to discriminate — add the specific wrong behavior.
- **Cure list recommends building all five capabilities at once.** Ch1's
  cascade point means start with the highest-coverage cure; building all
  five before validating one is the "three-car garage" anti-pattern.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report:
   - each of the five modes classifies from its distinctive signal
   - each primary carries the correct root-flaw and cure mapping
   - an irrelevant symptom is reported unclassified, not forced
   - batch mode aggregates flaw counts and orders cures by coverage
   - every taxonomy mode maps to a known fatal flaw
2. **Verify CLI help.** `python cli.py --help` exits 0 and prints the SKILL.md description.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly) by Anthony Alcaraz & Julien
— Ch1: The Crisis of Agentic AI, specifically the five-fatal-flaws opening
and the "Consequences for vector-based agents" section (action blindness /
memory fragmentation / planning paralysis / context drift, and the cascade
that reinforces them). Tool-chaos failure mode anchored in Anthropic's
"Effective Context Engineering for Agents"; local-vs-global query failure in
Microsoft's "From Local to Global: A GraphRAG Approach."
