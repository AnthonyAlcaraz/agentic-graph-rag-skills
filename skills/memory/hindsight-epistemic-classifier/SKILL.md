---
name: hindsight-epistemic-classifier
description: |
  Classify facts into HINDSIGHT's 4 epistemic networks (Latimer et al. 2025,
  cited in Ch4): World (objective external facts), Experience (agent's own
  first-person actions), Opinion (subjective beliefs with confidence), and
  Observation (synthesized entity summaries). The separation enables
  traceability — when users ask "how do you know that", the agent can
  distinguish evidence from inference from summary. Use when memory must
  support "how do you know" questions and the agent will be asked to
  justify its outputs. NOT for one-shot agents (no need to justify), NOT
  for storage-only systems (the classification is for retrieval-time
  reasoning, not just persistence).
osmani-pattern: Reviewer
ghosh-layer: Primitive
chapter-source: "Agentic GraphRAG (O'Reilly) Ch4 — Memory — Epistemic Classification subsection (HINDSIGHT Latimer et al. 2025 §3.4)"
references:
  - "HINDSIGHT (Latimer et al., 2025) — primary research anchor"
  - "Composes with bi-temporal-edge (Experience facts get ingested_at)"
---

# HINDSIGHT 4-Network Epistemic Classifier

## Overview

Production memory systems benefit from distinguishing **what the agent
observed** from **what it believes**. HINDSIGHT (Latimer et al., 2025, cited
in Ch4) organizes memory into four networks:

- **World network** — objective facts about external reality. Verifiable
  by external sources (the production region is us-east-1, the CEO of
  ACME is X, the API endpoint returned 503).
- **Experience network** — the agent's own first-person actions. "I called
  the deploy API at 22:30." "I retrieved 5 documents." First-person,
  timestamped, agent-as-actor.
- **Opinion network** — subjective beliefs with confidence scores. "I
  believe the root cause is X with 0.7 confidence." Inference, not
  observation.
- **Observation network** — synthesized entity summaries. "Sarah is the
  on-call lead this week" derived from the union of {Sarah's calendar,
  on-call rotation doc, prior incidents}. Distillation, not evidence.

Per the HINDSIGHT paper as quoted in Ch4: "developers and users can see
what the agent knows versus what it believes." This skill is the
classification layer that makes the distinction queryable.

## When to Use

- Audit-grade agents — when a user asks "how do you know that," the
  response must trace evidence to network
- Regulated environments — opinion must be flagged as opinion, not stated
  as fact
- Multi-agent systems — Agent A's opinion should not become Agent B's fact
  via uncritical knowledge sharing
- Debugging hallucinations — if the agent stated X confidently, the
  network classification tells you whether X is evidence-grounded
  (World/Experience) or inference (Opinion/Observation)

Phrases: "where did the agent get this", "is this fact or inference",
"justify the answer", "trust calibration", "HINDSIGHT", "epistemic status".

## When NOT to Use

- One-shot agents that need no justification trail
- Storage-only systems (the classification is for retrieval-time
  reasoning, not just persistence)
- Pure-retrieval agents that never synthesize — the Observation network
  is empty, the Opinion network is empty; just use World + Experience

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Raw fact text + optional metadata | `lib.classify(text, metadata)` | `EpistemicClass(network, confidence)` | network ∈ {World, Experience, Opinion, Observation}; confidence in [0, 1] |
| 2 | List of facts | `lib.classify_batch(facts)` | List of EpistemicClass | counts per network match expected distribution for the source |
| 3 | Memory containing classified facts | `lib.justify(memory, query)` | Provenance chain: which World+Experience facts ground a given Opinion/Observation | every Opinion or Observation traces back to World or Experience |
| 4 | Classified memory | `lib.network_audit(memory)` | Health report — % per network, orphan Opinions (no provenance chain), Experience without timestamps | flags `experience_without_timestamp_count > 0` |

## Classification Heuristics

| Network | Linguistic signals | Metadata signals |
|---------|---------------------|------------------|
| World | declarative third-person, no agent pronoun, verb tense past or present, no confidence hedging | `source != agent`, `external_ref` present |
| Experience | first-person agent pronouns ("I called", "I retrieved"), action verbs, timestamp | `source == agent`, `action_type` present |
| Opinion | hedging ("I believe", "likely", "probably", "appears to"), explicit confidence | `confidence < 1.0`, `inferred_from` present |
| Observation | synthesis language ("based on X and Y", "in summary"), multiple inputs | `derived_from` has multiple refs |

The default classifier is heuristic — production should swap in an LLM
classifier with a typed-output schema at this seam.

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "All facts are facts — networks are overengineering." | Then when the user asks "how do you know," the agent cannot distinguish "the API returned 503" (World, evidence) from "I believe the database was overloaded" (Opinion, inference). The trust calibration collapses. |
| "Just track a confidence score; networks are redundant." | Confidence is a property of Opinion. World facts don't have confidence — they have provenance. Confidence-only loses the World/Experience/Opinion distinction. |
| "Observation can be folded into World." | Observation is *synthesized* from World; it inherits the synthesis-step's failure modes. If you fold it into World, your "World" silently includes summarizations that may contradict raw evidence. The chapter's worked example: Sarah's role is World; "Sarah is the most reliable on-call" is Observation. |
| "I'll skip Experience because the agent always logs its actions." | Logging is not classification. Experience is the network that answers "what did *I* do" vs "what happened in the world." If your logs are merged into World, you've conflated agent-action with external-event. |

## Red Flags

- **Opinion network is empty.** Either the agent never reasons (unusual)
  or opinions are being misclassified as World (more likely; check
  hedging-language detection).
- **Experience network has no timestamps.** Replay / forensic
  reconstruction is broken — fix at lib boundary.
- **Observation network references nothing.** The provenance chain is
  broken; observations should reference the World/Experience facts they
  synthesize from.
- **World network has confidence < 1.0 entries.** World is supposed to
  be evidence; if it has confidence, it's Opinion misclassified.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report:
   - all 4 networks distinguishable from typical training-data examples
   - classify_batch produces deterministic output
   - justify returns a non-empty provenance chain for Opinion/Observation
2. **Verify CLI help.** Exits 0, prints SKILL.md description.

## Security Posture

- **Prompt injection.** Fact text is untrusted input classified against fixed
  signals - never executed. The attack shape is epistemic masquerade:
  adversarial phrasing that dresses an opinion as an objective World fact so
  downstream agents over-trust it. The provenance chain from `justify` is the
  cross-check; use it.
- **Data exfiltration.** No network calls, no file writes. Facts and their
  provenance chains may reference sensitive sources; they surface only in the
  stdout report the caller owns.
- **Privilege escalation.** No shell invocation, no eval, no dynamic import.
  Network labels are trust metadata: silently promoting Opinion/Observation to
  World is the escalation to guard against - the label is advisory and grants
  no evidentiary standing by itself.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien) Ch4 — Epistemic
Classification subsection. Primary research: HINDSIGHT (Latimer et al.,
2025).
