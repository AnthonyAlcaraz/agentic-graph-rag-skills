---
name: four-layer-eval-cascade
description: |
  The Multi-Layered Evaluation Framework as a sequential diagnostic cascade
  that STOPS at the first failing layer. Layer 0 is a zero-shot hallucination
  gate (NLI grounding, catches 60-70% of hallucinations at under 5% of
  full-judge compute). Layer 1 is a context evaluator (binary sufficient/not).
  Layer 2 is a cognitive fault isolator (KNOWLEDGE vs REASONING). Layer 3 is
  the TIR-Judge (correctness times format times tool, MULTIPLICATIVE
  so a well-formatted wrong answer scores 0). The cascade emits a diagnostic report that names the
  failure mode, locates it by node, and prescribes an intervention. Use to
  autopsy a failed agent execution and route the fix (retrieval / prompt /
  fine-tune). NOT for one-shot single-call agents (no reasoning trace to
  isolate), NOT a replacement for the execution graph it reads from (build that
  first).
osmani-pattern: Reviewer
ghosh-layer: Workflow
chapter-source: "Agentic GraphRAG (O'Reilly) Ch7 — Self-Evolution and Evaluation — The Multi-Layered Evaluation Framework: A Cognitive Autopsy + Examples 7-2/7-3/7-4/7-6/7-16/7-17"
references:
  - "GLiClass (Knowledgator, 2025) — zero-shot NLI hallucination detection for Layer 0"
  - "Meta J1 reasoning-trace judge — Layer 1 context sufficiency"
  - "MICRO-ACT DECOMPOSE + Knowledge Index / InfoGain — Layer 2 cognitive isolation"
  - "TIR-Judge (Xu et al.) — Layer 3 code-executing evaluation, TIR-Judge-8B matches 4x-larger reward models"
  - "Reads the execution-graph primitive; feeds Semantic Backpropagation and the self-improvement engine"
---

# Four-Layer Evaluation Cascade

## Overview

The execution graph tells you what happened. This framework is the diagnostic
engine that tells you why. It operates as a sequential filter, moving from the
most general failure cause to the most specific, and it stops at the first
layer that catches the failure. Each layer asks a progressively narrower
question (Ch7 Figure 7-1):

- **Layer 0 (hallucination gate)** gates on grounding. A lightweight NLI-style
  classifier scores whether the answer is grounded in the retrieved premise.
  The threshold is 0.85. It catches 60-70% of hallucinations at less than 5%
  of the compute of a full LLM judge call. Scores between 0.5 and 0.85 escalate
  to the full pipeline (the SLM-LLM flywheel); scores below 0.5 hard-block.
- **Layer 1 (context evaluator)** asks: did the agent even possess the
  information it needed? A failure here is a knowledge-representation or
  retrieval failure, not a reasoning failure. The verdict is binary
  (sufficient or not) with a `missing_information` list (J1-style).
- **Layer 2 (cognitive fault isolator)** splits a cognitive failure into two
  mutually exclusive categories. A KNOWLEDGE failure means coherent reasoning
  over wrong facts (low Knowledge Index). A REASONING failure means the right
  facts, badly connected (near-zero or negative InfoGain steps).
- **Layer 3 (TIR-Judge)** verifies quantitative claims by executing code
  against the KG. Its reward is `correctness * format * tool`, multiplicative
  so a confidently wrong but well-formatted answer scores zero.

The output is a structured diagnostic report (Ch7 Example 7-4): it names the
failure mode, locates it by node ID, and prescribes an intervention. That
report is what drives the self-improvement engine.

The worked anchor is the DevOps premature-closure autopsy (Ch7 Example 7-16 /
7-17): sufficient context, Knowledge Index 0.91, InfoGain trace
`[0.34, 0.29, 0.22, 0.03, -0.01, 0.19]`, low-InfoGain steps `[4, 5]`, fault at
CausalAttributionNode, recommended intervention PROMPT_REFINEMENT.

## When to Use

- Autopsy a failed agent execution when you need to name WHY, not just THAT, it
  failed
- Route the fix: is this a retrieval problem, a prompt problem, or a
  fine-tuning problem?
- Cheap prescreening: run Layer 0 on every response before spending judge
  compute on Layers 1-3 (the evaluation budget starts the inference budget)
- Feed the self-improvement engine — Semantic Backpropagation needs the
  report's fault_location and low_infogain_steps

Phrases: "cognitive autopsy", "why did the agent fail", "evaluation cascade",
"hallucination gate", "context sufficiency", "knowledge vs reasoning failure",
"TIR-Judge", "recommended intervention", "premature closure".

## When NOT to Use

- **One-shot single-call agents.** There is no reasoning trace to isolate at
  Layer 2 and no multi-step execution to autopsy. Log the call instead.
- **As a replacement for the execution graph.** This cascade reads the graph;
  it does not build it. Build the execution-graph primitive first.
- **As the production classifier stack.** Every layer here is a deterministic
  dev-time stand-in. Swap Layer 0 for GLiClass/DeBERTa NLI, Layer 1 for a J1
  judge, Layer 3 for a TIR-Judge CodeExecutor before production.
- **For mechanistic circuit-level diagnosis.** The chapter is explicit: for
  most failures, stop the diagnostic process at Layer 2 rather than produce
  spurious mechanistic explanations.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | query + answer + context_premise (+ threshold) | `lib.layer0_hallucination_gate(...)` | `GateResult(passed, confidence, action, skip_full_eval)` | grounded answer scores >= 0.85 (PROCEED); an absent entity claim drives score < 0.5 (BLOCK_AND_REGENERATE) |
| 2 | query + context (+ required_claims) | `lib.layer1_context_evaluator(...)` | `ContextVerdict(sufficient, missing_information, conflicting_statements, confidence)` | sufficient iff every required claim token-appears in context; missing ones listed |
| 3 | infogain_trace + knowledge_index (+ fault_node, thresholds, diagnosis) | `lib.layer2_cognitive_fault_isolator(...)` | `CognitiveVerdict(failure_type, fault_location, knowledge_index, infogain_trace, low_infogain_steps, diagnosis)` | KI < ki_threshold -> KNOWLEDGE else REASONING; low_infogain_steps are 1-based indices below infogain_floor |
| 4 | claim_value + expected_value (+ format_ok, tool_ok) | `lib.layer3_tir_judge(...)` | `TIRReward(correctness, format_compliance, tool_accuracy, composite)` | composite is multiplicative; a wrong value zeroes it regardless of format |
| 5 | execution dict | `lib.run_cascade(execution)` | diagnostic report (Example 7-4 shape) | runs L0->L1->L2->L3, stops at first failing layer; report carries stopped_at_layer + recommended_intervention + target_nodes |
| 6 | (bundled) | `cli.py scenario devops-autopsy` | rebuilds Example 7-16/7-17 report | stops at Layer 2, REASONING, low steps [4,5], recommends PROMPT_REFINEMENT |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Just run the full LLM judge on every response." | Ch7: "For a DevOps agent processing 200 predictions per hour, that is 600 judge calls per hour before you count the actual inference. The evaluation budget starts the inference budget." Layer 0 catches 60-70% of hallucinations at under 5% of full-judge compute. Screen cheap, escalate the uncertain 0.5-0.85 band. |
| "Make the TIR reward additive so a well-formatted answer still gets partial credit." | Ch7 is explicit: "The composite score is multiplicative, not additive. A perfectly formatted response with an incorrect answer scores zero... a confidently wrong answer that looks well structured is more dangerous than an obviously malformed one." |
| "Skip Layer 1 and go straight to reasoning analysis." | Ch7: "A failure here is not a reasoning failure. It is a failure of knowledge representation or retrieval." If the context was insufficient, InfoGain analysis on the reasoning is measuring the wrong thing. Layer 1 stops the cascade and routes to RETRIEVAL_FIX. |
| "KNOWLEDGE and REASONING failures need the same fix." | Ch7: "A knowledge failure would call for better retrieval or richer context. A reasoning failure calls for a prompt or model change that forces the agent to consider multiple hypotheses before committing." The Layer 2 split is what makes the intervention correct: PROMPT_REFINEMENT vs FINE_TUNE. |
| "Trace the failure to specific model circuits for a precise explanation." | Ch7: "circuit-level diagnosis is not reliably possible" for metareasoning and complex multistep logic errors. "The framework is designed to recognize these and stop the diagnostic process at Layer 2 rather than produce spurious mechanistic explanations." |

## Red Flags

- **Every response reaches Layer 3.** Layer 0 is not screening. Check the
  grounding heuristic and the 0.85 threshold; the gate exists to keep 60-70%
  of failures out of the expensive layers.
- **Layer 1 always returns sufficient.** No `required_claims` are being passed,
  so insufficiency cannot be detected. The default sufficient verdict is
  optimistic by design; supply the claims a correct answer requires.
- **A REASONING verdict routes to FINE_TUNE.** Premature closure (a short
  low-InfoGain tail with high KI) should route to PROMPT_REFINEMENT. A
  REASONING failure sent to fine-tuning is treating a prompt problem as a
  weights problem.
- **`low_infogain_steps` is empty on a known-bad trace.** The `infogain_floor`
  is too low, or the trace was not captured per step. The premature-closure
  trace must surface steps [4, 5].
- **Composite reward is nonzero on a wrong quantitative claim.** The reward was
  made additive somewhere. A wrong value must zero the composite.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report all
   gates passed, including: multiplicative TIR zeroes on a wrong answer; the
   cascade stops at Layer 0 on an ungrounded answer; the cascade stops at
   Layer 1 on insufficient context; Layer 2 classifies REASONING vs KNOWLEDGE
   by Knowledge Index; `low_infogain_steps` computes to [4, 5] from the
   premature-closure trace; the devops-autopsy scenario recommends
   PROMPT_REFINEMENT.
2. **Run the DevOps scenario.** `python cli.py scenario devops-autopsy`
   rebuilds the Ch7 Example 7-16 / 7-17 report: stops at Layer 2, REASONING,
   fault at CausalAttributionNode, low steps [4, 5], recommended
   PROMPT_REFINEMENT.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints the SKILL.md
   description.

## Security Posture

- **Prompt injection.** The `answer`, `context_premise`, and `required_claims`
  are treated as untrusted strings. `lib.py` only tokenizes and substring-
  matches them; it never evaluates, executes, or interpolates them into a
  shell or an LLM prompt. In production the Layer 3 seam runs generated Cypher
  or Python against the KG. That CodeExecutor must sandbox the generated code
  and parameterize queries. The `# TODO(production)` at the Layer 3 seam is the
  place to enforce it.
- **Data exfiltration.** No network calls in `lib.py`. The cascade returns the
  diagnostic report to the caller. CLI JSON is printed to stdout; downstream
  piping is the caller's responsibility.
- **Privilege escalation.** No shell invocation, no `eval`/`exec`, no file
  writes. `cli.py` reads exactly one file, the execution JSON named by the
  explicit `--path` flag. Everything else is pure in-memory computation.

## Composition

- **Reads** the execution-graph primitive (`self-evolution/execution-graph`).
  The graph supplies the per-node input/output, the InfoGain trace, and the
  fault node ID this cascade autopsies.
- **Feeds** Semantic Backpropagation and the self-improvement engine. The
  report's `fault_location`, `low_infogain_steps`, and
  `recommended_intervention` are the inputs that scope a structured feedback
  signal to the responsible node.
- **Composes with** the Anthropic `agent-skills` Reviewer pattern at the pattern-taxonomy
  layer and the Ghosh Workflow layer: the four sequential gates are a review
  pipeline whose output is a routing decision, not a code edit.
- **Extends via** the dual-pathway model (Luo et al.): a `pathway_classification`
  field (Q-anchored vs A-anchored) can annotate a Layer 2 KNOWLEDGE failure to
  decide fine-tune (Q-anchored) vs better retrieval (A-anchored). Out of scope
  here; the report shape leaves room for it.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien),
Chapter 7 — Self-Evolution and Evaluation, "The Multi-Layered Evaluation
Framework: A Cognitive Autopsy" section, plus the DevOps cognitive-autopsy
worked example. Chapter examples realized here: 7-2 (zero-shot hallucination
pregate), 7-3 (J1 context sufficiency judge), 7-4 (diagnostic report
structure), 7-6 (tool-integrated three-component reward), and 7-16 / 7-17 (the
premature-closure InfoGain trace and its diagnostic report). Named references:
GLiClass (Knowledgator, 2025), Meta J1, MICRO-ACT DECOMPOSE, TIR-Judge (Xu et
al.), and the SLM-LLM flywheel (Microsoft Research, 2024). Production substrate:
NLI classifier + J1 judge + CodeExecutor issuing Cypher against the KG.
