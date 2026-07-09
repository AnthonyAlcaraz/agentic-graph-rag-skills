---
name: intervention-selector
description: |
  Ch7 self-evolution router: map a diagnostic report to exactly one
  intervention, deterministically and auditably, not as a per-engineer
  judgment call. Four branches in strict order: insufficient context ->
  RETRIEVAL_FIX (fix upstream of the model), FORMAT_VIOLATION ->
  STRUCTURAL_CONSTRAINT (attach an output schema so the error is impossible),
  localized REASONING failure with intact knowledge -> PROMPT_REFINEMENT
  (steer, do not retrain), everything else -> FINE_TUNE (systemic or recurring
  failure). A second axis ranks intervention types on the self-modification
  intensity hierarchy: prompt tuning is lightest (fast, reversible, low risk),
  weight adaptation is middle (slower, semi-reversible, moderate risk), code
  modification is heaviest (slowest, requires rollback, highest risk). Ports
  Ch7 Example 7-9 exactly, thresholds tunable per the chapter Tip. Use AFTER a
  diagnostic report exists and you must choose the fix. NOT for producing the
  diagnosis itself (that is the Layer 0/1/2 evaluation pipeline), NOT for
  applying the fix (this routes; SEAL/TPT/Outlines apply).
osmani-pattern: Reviewer
ghosh-layer: Reasoning
chapter-source: "Agentic Graph RAG (O'Reilly) Ch7 — Self-Evolution and Evaluation — Choosing the Right Intervention: Prompt, Fine-Tune, or Constrain? + Example 7-9 (select_intervention) + self-modification intensity hierarchy"
references:
  - "Ch7 Tip: intervention selection must be deterministic and auditable, tuned against historical diagnostic data"
  - "Composes downstream with Semantic Backpropagation, SEAL, TPT, and the Graduated Validation Protocol"
---

# Intervention Selector

## Overview

A diagnosis is only valuable if it leads to the right intervention. Different
failure types call for different responses. A reasoning failure at a single
node calls for a prompt update; a systemic knowledge gap calls for
fine-tuning; a format violation calls for an architectural constraint.
Applying the wrong fix wastes time at best and makes things worse at worst.

The diagnostic report already contains the failure type and target nodes, so
mapping them to an intervention is a straightforward routing function (Ch7
Example 7-9). The chapter Tip is explicit about why this is a function and not
a human call: intervention selection should be deterministic and auditable,
not a judgment call made differently by each on-call engineer.

The router applies four branches in strict order:

1. **Insufficient context -> RETRIEVAL_FIX.** The context was insufficient, so
   the fix lives upstream of the model in the retrieval pipeline. Flag the
   Knowledge Graph or retrieval gap.
2. **FORMAT_VIOLATION -> STRUCTURAL_CONSTRAINT.** The agent had the right
   knowledge and reasoning but failed to produce a machine-readable output.
   Attach an output schema to that node so the format error is impossible
   rather than less likely. Architectural change, not a model change,
   permanent fix for that component.
3. **Localized REASONING failure -> PROMPT_REFINEMENT.** REASONING failure,
   few low-InfoGain steps (`len(low_infogain_steps) <= low_step_max`), high
   knowledge index (`knowledge_index > ki_floor`). The agent has the
   capability; steer it at that node. Fast, reversible, low risk, the right
   first resort.
4. **Everything else -> FINE_TUNE.** A systemic knowledge gap, a recurring
   pattern of the same reasoning failure, or a persistent misalignment.
   Generate a curriculum via SEAL/TPT and retrain.

The second axis, the self-modification intensity hierarchy, orders the
intervention types by cost and risk (Ch7): prompt tuning is the lightest
intervention (fast, reversible, low risk), weight adaptation sits in the
middle (slower, semi-reversible, moderate risk), and code modification is the
heaviest (slowest, requires explicit rollback, highest risk). The router
never emits CODE_MODIFICATION; it is the heaviest tier, reserved for explicit
code-level self-modification loops (SICA) run in a sandbox with full rollback.

## When to Use

- A Ch7 diagnostic report exists (Layer 1 context sufficiency, Layer 2
  cognitive failure type, low-InfoGain steps, knowledge index) and you must
  pick the fix
- Closing a self-evolution loop: execution -> diagnosis -> feedback ->
  intervention -> validation. This is the intervention step
- Automating the fix decision so it is uniform across on-call engineers
  rather than a per-person judgment call
- Ranking a chosen intervention on the intensity hierarchy before it enters
  the Graduated Validation Protocol (lower-risk interventions enter at a
  lighter canary tier)

Phrases: "which intervention", "prompt fine-tune or constrain", "route the
diagnosis", "select_intervention", "how do I fix this diagnosed failure",
"intervention intensity".

## When NOT to Use

- **Producing the diagnosis.** This skill consumes a report; it does not build
  one. The report comes from the Ch7 Layer 0/1/2 evaluation pipeline
  (Reasoning Shape Analysis, context sufficiency check). Feed a report in.
- **Applying the fix.** The router returns a routed intervention. SEAL/TPT
  generate the curriculum, Outlines attaches the schema, the workflow-graph
  editor updates the prompt. This skill decides; it does not execute.
- **Emitting CODE_MODIFICATION.** Code-level self-modification is the most
  dangerous form of self-evolution. It is never an automated router output;
  it belongs to a sandboxed SICA loop with an LLM overseer and full rollback.
- **Cross-node coherence.** The router handles a single node in isolation. For
  coherent evolution across the graph (preventing a good fix to one node from
  silently breaking a neighbor), use Semantic Backpropagation (Ch7), not this.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | diagnostic report dict (layer_1_context, layer_2_cognitive, target_nodes) | `lib.select_intervention(report, low_step_max=2, ki_floor=0.8)` | one `Intervention` (type, action, target, rationale) | exactly one type from RETRIEVAL_FIX / STRUCTURAL_CONSTRAINT / PROMPT_REFINEMENT / FINE_TUNE; rationale names the fired condition |
| 2 | report with `layer_1_context.sufficient == False` | branch 1 | RETRIEVAL_FIX, target `"retrieval_pipeline"` | short-circuits before failure_type is examined |
| 3 | report with `failure_type == "FORMAT_VIOLATION"` (context sufficient) | branch 2 | STRUCTURAL_CONSTRAINT, target = `report["target_nodes"]`, action "Attach output schema to node" | fires only when context is sufficient |
| 4 | REASONING, `len(low_infogain_steps) <= low_step_max`, `knowledge_index > ki_floor` | branch 3 | PROMPT_REFINEMENT, action "Update prompt for target node" | strict `>` on ki_floor; `<=` on low_step_max |
| 5 | anything else (KNOWLEDGE, many low steps, ki at/below floor) | branch 4 | FINE_TUNE, action "Generate curriculum via SEAL/TPT and retrain" | fallthrough; no other branch matched |
| 6 | intervention type string | `lib.intervention_intensity(type)` | `{tier, speed, reversibility, risk, description}` | all five keys present; unknown type raises ValueError |
| 7 | two intervention types | `lib.risk_rank(a)` vs `lib.risk_rank(b)` | ordinal ranks | prompt(1) < fine-tune(2) < code-modification(3) |
| 8 | diagnostic report dict | `lib.explain(report)` | one audit line naming execution_id, chosen type, tier, risk, fired condition, action, target | deterministic: same report yields the same line |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "The engineer on call can just decide the fix." | The Ch7 Tip is explicit: "intervention selection should be deterministic and auditable, not a judgment call made differently by each on-call engineer." A per-person decision is neither reproducible nor auditable. |
| "A format violation just needs a better prompt to speak JSON." | Ch7 rejects this: "Rather than teaching the model to speak JSON better through more training, attach an output schema constraint directly to that specific node." The constraint makes the error impossible, not merely less likely, and produces a permanent fix for that component. |
| "Every diagnosed failure should trigger fine-tuning to be safe." | Fine-tuning is the heavyweight fix, reserved for a systemic knowledge gap or a recurring pattern. Ch7: prompt refinement "is fast, reversible, and the right first resort" for a localized reasoning failure. Retraining a single-node reasoning slip is expensive and slow to validate for no gain. |
| "Skip the context check; failure_type already tells me everything." | Ch7 Example 7-9 checks `layer_1_context.sufficient` first for a reason: if the context was insufficient, no model-side intervention helps. The fix is upstream in the retrieval pipeline. Routing a context gap to a prompt or fine-tune change treats the wrong layer. |
| "The 0.8 KI and two-step thresholds are magic numbers I can ignore." | Ch7 Tip: "The thresholds here are starting points. Tune them against your own historical diagnostic data." They are exposed as `low_step_max` and `ki_floor` parameters precisely so you tune them, not so you discard the check. |
| "Let the router emit a code fix when the prompt path fails." | Ch7 Caution: "Code-level self-modification is the most powerful and most dangerous form of self-evolution. Use it only in sandboxed environments with full rollback capability." It is never an automated router output; it belongs to a SICA loop with an overseer. |

## Red Flags

- **Router output depends on dict-key order or run time.** Selection must be a
  pure deterministic function of the report fields. Non-determinism breaks the
  auditability the Ch7 Tip requires.
- **PROMPT_REFINEMENT chosen while `knowledge_index` is low.** A low KI is a
  knowledge gap, not a reasoning slip. Branch 3 requires `ki > ki_floor`; if a
  low-KI report routes to a prompt fix, the sufficiency or KI field is wrong.
- **FINE_TUNE chosen for a one-node, one-step reasoning failure.** Heavyweight
  fix for a lightweight problem. Check `low_infogain_steps` count and KI; a
  localized failure should route to PROMPT_REFINEMENT.
- **CODE_MODIFICATION emitted by the router.** It never should be. The router
  emits only the four report-driven interventions; code modification is a
  sandboxed SICA-loop decision, not an automated routing output.
- **`intervention_intensity` returns fewer than five keys.** Downstream
  validation tiering reads tier and risk; a missing key breaks the Graduated
  Validation Protocol admission decision.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report all
   16 gates pass: insufficient-context -> RETRIEVAL_FIX; FORMAT_VIOLATION ->
   STRUCTURAL_CONSTRAINT; REASONING/2-low-steps/ki-0.91 -> PROMPT_REFINEMENT;
   REASONING/4-low-steps -> FINE_TUNE; KNOWLEDGE/low-ki -> FINE_TUNE; the
   intensity hierarchy ordering prompt < fine-tune < code-modification by
   risk; and the DevOps scenario report resolving to PROMPT_REFINEMENT.
2. **Run the DevOps scenario.** `python cli.py scenario devops-prediction`
   feeds the Ch7 running-example report (stripe-python 3.2.1 -> 3.3.0, timeout
   30s -> 10s, checkout-service -> order-service -> fulfillment-service,
   fictional AWS account 123456789012) and must resolve to PROMPT_REFINEMENT,
   the lightest intervention, because the failure was a reasoning pattern
   localized to one node, not a knowledge gap.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints the SKILL.md
   description.

## Security Posture

- **Prompt injection.** The diagnostic report is trusted internal data emitted
  by your own evaluation pipeline. If any report field (`diagnosis`,
  `target_nodes`) can be influenced by untrusted user input that reached the
  Layer 2 diagnostic, treat those strings as untrusted and validate before the
  routed action is executed downstream. The router itself makes no decision
  from free-text fields: it branches only on `sufficient` (bool),
  `failure_type` (enum), `low_infogain_steps` (list length), and
  `knowledge_index` (float), which bounds the injection surface.
- **Data exfiltration.** `lib.py` makes no network calls and no shell calls. It
  reads the report dict passed in and returns an `Intervention`. The CLI reads
  the report from the explicit `--path` argument and prints to stdout; the
  caller owns downstream piping.
- **Privilege escalation.** No shell invocation, no concatenated input to a
  shell, no file writes anywhere. The CLI only reads the `--path` report file.
  The router decides; it never applies a fix, so it cannot itself trigger a
  fine-tune job, edit a prompt, or modify code. CODE_MODIFICATION is never an
  output, so the highest-risk intervention cannot be reached through this seam.

## Composition

- **Composes downstream with** Semantic Backpropagation (Ch7): the router
  picks the intervention type for a node; semantic backpropagation generates
  the neighbor-aware feedback that fills a PROMPT_REFINEMENT, and guards
  against a good single-node fix silently breaking a neighbor.
- **Composes downstream with** SEAL and TPT (Ch7): a FINE_TUNE output is the
  entry point to SEAL/TPT curriculum generation and retraining.
- **Composes downstream with** constrained generation / Outlines (Ch6): a
  STRUCTURAL_CONSTRAINT output attaches an output schema to the target node.
- **Feeds** the Graduated Validation Protocol (Ch7): the intensity tier and
  risk of the chosen intervention set the canary tier it enters at (a prompt
  refinement enters at Tier 1; a code modification enters at the strictest).
- **Consumes** the diagnostic report from the Ch7 Layer 0/1/2 evaluation
  pipeline and the execution-graph primitive (`self-evolution/execution-graph`)
  that the diagnosis is built on.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, AnthonyAlcaraz / forthcoming)
Chapter 7 — Self-Evolution and Evaluation, the section "Choosing the Right
Intervention: Prompt, Fine-Tune, or Constrain?" It ports Example 7-9
(`select_intervention`) exactly, including the chapter thresholds (two or
fewer low-InfoGain steps for a prompt fix, a knowledge index above 0.8 for a
reasoning-only diagnosis) exposed as tunable parameters per the accompanying
Tip. The self-modification intensity hierarchy (prompt lightest, weight
adaptation middle, code modification heaviest) is drawn from the chapter's
SICA / self-modification-intensity discussion, and the DevOps running example
(PROMPT_REFINEMENT for the CausalAttributionNode premature-closure failure) is
the chapter's worked loop closure.
