---
name: xskill-self-improving-object
description: |
  Turn execution traces into knowledge that improves without retraining. Two
  Ch7 primitives compose: XSkill dual-stream extraction distills EXPERIENCES
  (action-level: what worked or failed for one tool call) and SKILLS
  (task-level: a multistep pattern that solves a category of task) from the
  execution graph. Cognee then treats each skill as a graph OBJECT that
  observes its own executions, computes its success rate, and rewrites itself
  via amendify() when it degrades. Routing selects skills by demonstrated
  success on the task pattern, not by description similarity. Use to give an
  agent memory of past failures (experiences alone cut tool errors 29.9% to
  16.3%) and skills that track a changing environment. NOT for a static agent
  that never re-runs similar tasks (no traces to learn from), NOT for the raw
  execution graph itself (use the execution-graph skill, which is the substrate
  this consumes).
osmani-pattern: Pipeline
ghosh-layer: Workflow
chapter-source: "Agentic GraphRAG (O'Reilly) Ch7 — Self-Evolution and Evaluation — Inference-Time Knowledge Augmentation + Skills as Self-Improving Graph Objects + Example 7-20 (KnowledgeAccumulator) and Example 7-22 (SkillNode / SkillGraph)"
references:
  - "XSkill (Jiang et al., 2026) — dual-stream continual learning"
  - "Cognee add-cognify-search-learn skill-as-graph-object pipeline"
  - "Consumes the execution-graph skill (Ch7 Example 7-1) as its input substrate"
---

# XSkill Self-Improving Graph Objects

## Overview

The improvement mechanisms earlier in Ch7 (prompt refinement, SEAL data
generation, fine-tuning) all modify the agent itself. Knowledge augmentation
is lighter: it accumulates knowledge from past executions and retrieves it at
inference time, touching neither the model nor its prompts. The motivating
measurement from the chapter: on the Kaggle GameArena chess benchmark, 78% of
Gemini-2.5-Flash losses were illegal moves, rule violations rather than weak
strategy. The agent kept repeating the same category of mistake because it had
no memory of past failures.

XSkill (Jiang et al., 2026) extracts two complementary knowledge types from
trajectories:

- **Experiences** operate at the action level. Each execution node's input,
  action, and outcome becomes a candidate experience record. Experiences alone
  reduce tool errors from 29.9% to 16.3% (a 45% reduction).
- **Skills** operate at the task level. The path from the root query node to a
  successful resolution node becomes a candidate multistep skill. Together with
  experiences, the average success rate rises from 33.6% to 40.3%.

Cognee closes the remaining gap: XSkill's skills are static artifacts. Cognee
treats a skill as a first-class graph node (Example 7-22) with execution
records, a success rate, and an amendment history. Its four-stage pipeline is
add (parse SKILL.md, compute content hash) then cognify (extract trigger
phrases and complexity) then search (route by which skill SUCCEEDS at similar
tasks) then learn (log an observation per execution). When a skill degrades,
`amendify()` rewrites it against the last 10 failures, validates the amendment
against held-out records, and rolls back on failure.

## When to Use

- After an agent has accumulated execution traces and you want it to stop
  repeating avoidable mistakes without retraining
- Environments that drift (a Kubernetes API change, a new CI/CD stage) where a
  static SKILL.md silently goes stale
- Routing among several overlapping skills where description similarity picks
  the wrong one and demonstrated success should decide
- Building the self-evolution loop on top of the execution-graph substrate

Phrases: "learn from past failures", "self-improving skill", "amendify",
"route by success rate", "XSkill", "Cognee", "knowledge retirement",
"dual-stream extraction".

## When NOT to Use

- One-shot agents that never see similar tasks again. No trace stream, nothing
  to distill.
- The raw execution graph itself. That is the `execution-graph` skill; this
  skill consumes its output.
- As a substitute for evaluation. This distills and routes knowledge; it does
  not score answer quality (use the Ch7 evaluation layers for that).
- When the environment is fixed and the skill has a stable high success rate.
  amendify() will not fire and the machinery is dead weight.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Execution nodes (id, task_type, action, context, outcome, caused_task_failure, neighbors) | `lib.extract_experiences(nodes)` | One `AgentExperience` per diverged node | Routine successes skipped; count equals diverged-node count |
| 2 | Successful executions (id, task_type, path, preconditions) | `lib.extract_skills(execs, min_support=3)` | `AgentSkill` per task_type with a shared path | No skill emitted below min_support; steps equal the common path |
| 3 | skill_id + definition dict | `SkillGraph.add(skill_id, definition)` | Registered `SkillNode` (version 1, content_hash set) | Node present; content_hash reproducible from definition |
| 4 | skill_id | `SkillGraph.cognify(skill_id)` | trigger_phrases + complexity + content_hash | Trigger phrases non-empty; complexity scales with step count |
| 5 | task dict (description, pattern) | `SkillGraph.route(task)` | Best `SkillNode` or None | Ranked by `success_rate_for(pattern)`, NOT similarity |
| 6 | skill_id + task + outcome (+error) | `SkillGraph.learn(skill_id, task, outcome, error)` | Observation appended | `SkillNode.executions` grows; success_rate recomputes |
| 7 | failure_threshold | `SkillNode.amendify(0.6)` | True if amended, else False | Fires only below threshold AND on validation; version + content_hash change |
| 8 | experiences + now_days | `lib.retire_experiences(exps, now_days, decay_days=90)` | Weight per experience | Age > 90 days halves the weight |
| 9 | SkillNodes | `lib.flag_stale_skills(skills, recent=10, floor=0.6)` | Flagged skill_ids | Sub-60% skill over recent 10 attempts flagged |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Route by description similarity, it is simpler." | Ch7 is explicit that this is the core architectural choice: "the graph selects skills by demonstrated performance, not description similarity." A newly added canary-deployment skill with successful executions must outrank a general deployment skill with a 40% failure rate on canary-specific tasks. Similarity picks the wrong one. |
| "Extract an experience from every node." | Only nodes whose outcome diverged from expectation carry a lesson (Example 7-20 filters on `outcome_diverged_from_expectation`). A routine success teaches nothing; extracting it dilutes retrieval with noise. |
| "Emit a skill from any successful run." | The chapter requires >= 3 executions sharing a common successful path before a skill is real (Example 7-20: `len(executions) >= 3`). One run is an anecdote, not a pattern. |
| "Skip retirement, more knowledge is better." | Ch7 names knowledge retirement as the critical design choice: experiences not revalidated within 90 days lose half their retrieval weight, and skills below 60% success over the most recent 10 attempts are flagged. Unretired knowledge serves stale lessons after the environment has moved. |
| "Let amendify() rewrite the skill whenever it fails." | Every amendment must validate against held-out execution records before replacing the current version, and failed amendments roll back automatically (Example 7-22). Rewriting on raw failure count reintroduces reward-hacking: the skill confirms its own bias instead of correcting it. |

## Red Flags

- **route() returns the higher-similarity skill instead of the higher-success
  one.** The ranking key the whole design depends on has been swapped back to similarity.
- **A skill's version keeps climbing but success_rate never recovers.**
  amendify() is validating against the same failures it is fitting to; the
  held-out set is not actually held out.
- **extract_experiences returns one record per node.** The divergence filter is
  off; retrieval will be flooded with routine successes.
- **extract_skills emits a skill from two executions.** min_support is not
  being enforced; an anecdote is being sold as a pattern.
- **Experiences never lose weight.** Retirement is not running; the agent
  serves 90-day-old lessons against a changed environment.
- **content_hash does not change after amendify().** The definition was not
  actually rewritten; change detection is broken.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report all
   gates passing: extract_experiences yields one experience per diverged node;
   extract_skills needs >= min_support; success_rate computes correctly;
   amendify() fires only below 0.6 and bumps version + changes content_hash
   (and rolls back on validation failure); route ranks by success_rate not
   similarity (canary vs general); flag_stale_skills flags a sub-60% skill;
   retire_experiences half-weights a >90-day experience.
2. **Run the DevOps scenario.** `python cli.py scenario devops-skill` shows the
   general deployment skill with higher description similarity losing the route
   to the canary-deployment skill on demonstrated success.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints this
   SKILL.md description.

## Security Posture

- **Prompt injection.** Lessons, amendment text, and trigger phrases come from
  execution traces and skill definitions. When those originate from untrusted
  tool outputs or user-supplied definitions, treat every string field as
  untrusted until validated: a malicious `error` or `context` could bias an
  amendment or a lesson. The heuristic extractors here do no instruction
  following; the LLM seams marked `# TODO(production)` are where an
  author-verifier separation and input sanitization must be added.
- **Data exfiltration.** `lib.py` makes no network calls and performs no shell
  invocation. It reads only the paths passed on the CLI and prints results to
  stdout; the caller owns any downstream piping.
- **Privilege escalation.** No shell, no `eval`, no dynamic import of trace
  content, no file writes outside the explicit `--path` inputs. amendify()
  mutates only the in-memory skill definition; persistence is the caller's
  decision, and the content_hash makes any change auditable.

## Composition

- **Consumes** the `execution-graph` skill (Ch7 Example 7-1): the nodes and
  successful subgraphs it extracts from are execution-graph output.
- **Composes with** the Ch7 evaluation layers, which score the outcomes that
  become experience and skill success labels.
- **Pairs with** the intervention router: knowledge augmentation ("what the
  agent remembers from doing") sits beside prompt refinement ("what the agent
  is told to do") and fine-tuning ("what the agent knows how to do"); the
  router selects among them by failure type.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien)
Chapter 7 — Self-Evolution and Evaluation, the Inference-Time Knowledge
Augmentation section (Example 7-20, KnowledgeAccumulator dual-stream
extraction) and the Skills as Self-Improving Graph Objects section (Example
7-22, SkillNode / SkillGraph with amendify() and success-rate routing). Named
sources: XSkill (Jiang et al., 2026) for dual-stream continual learning and the
29.9% to 16.3% / 33.6% to 40.3% figures; Cognee for the add-cognify-search-learn
skill-as-graph-object pipeline and the 90-day / 60%-over-10 retirement rules.
