---
name: agent-constraint-triangle-scorer
description: |
  Score an agent configuration against Ch1's Agent Constraint Triangle — the
  three interconnected constraints (complexity management, tool orchestration,
  context utilization) that make agent design an inherently difficult
  operational problem. Given the agent's reasoning-chain length, tool-catalog
  size and disambiguity, and context budget vs. usage, produce a 0-100
  pressure score and band per constraint, name which of Ch1's three cyclic
  trade-offs are active (complexity->tools->context, tools->context->complexity,
  context->complexity->tools), and give the minimal-but-sufficient
  recommendation for each stressed constraint. Use before scaling an agent's
  tools/steps/context to see which corner of the triangle will break first.
  NOT for model-quality issues (Ch1: the triangle is architectural), NOT for
  agents under ~10 tools with short chains where no corner is under pressure.
osmani-pattern: Reviewer
ghosh-layer: Reasoning
chapter-source: "Agentic GraphRAG (O'Reilly) Ch1 — Defining Agentic AI — The Agent Constraint Triangle"
references:
  - "Anthropic 'Effective Context Engineering for Agents' (bloated tool sets / disambiguation principle / attention-budget framing)"
  - "Chroma research team — needle-in-a-haystack benchmarking and context rot (recall degrades as tokens increase; a gradient, not a cliff)"
---

# Agent Constraint Triangle Scorer

## Overview

Ch1 names a fundamental challenge in building agents: the **agent constraint
triangle**, "three interconnected constraints that create an inherently
difficult operational problem":

1. **Complexity management** — multistep planning and reasoning. "As tasks
   require more steps and deeper analysis, cognitive load increases
   exponentially," producing "compounding errors as the step count increases."
2. **Tool orchestration** — translating natural language into precisely
   structured API calls. The named failure mode is "bloated tool sets that
   cover too much functionality or lead to ambiguous decision points about
   which tool to use." Anthropic's principle: "If a human engineer can't
   definitively say which tool should be used in a given situation, an AI
   agent can't be expected to do better."
3. **Context utilization** — organizing a fixed context window, "the model's
   attention budget." Chroma's needle-in-a-haystack research names *context
   rot*: "as the number of tokens in the context window increases, the model's
   ability to accurately recall information from that context decreases" — "a
   performance gradient," not "a hard cliff."

The chapter's key point is that these "don't exist in isolation but form a
system of competing trade-offs. When improving performance along one
dimension, you typically create additional pressure on the others." It names
three cyclic pressures:

- **complexity → tools → context**
- **tools → context → complexity**
- **context → complexity → tools**

The governing principle: "the smallest possible set of high-signal tokens that
maximizes the likelihood of some desired outcome" — minimal-but-sufficient
complexity decomposition, minimal-but-complete tool coverage, and
minimal-but-adequate context retention.

This skill scores a configuration against that triangle. The scoring curves are
transparent heuristics that embody the chapter's qualitative claims (exponential
complexity load, ambiguity-dominated tool pressure, context-rot gradient); they
are not chapter-cited benchmarks, and the production seam is documented at each
`lib` function.

## When to Use

- Deciding whether to add tools, lengthen reasoning chains, or grow context on
  an existing agent — and wanting to see which corner breaks first
- Diagnosing an agent that degrades as you scale it up
- Comparing two agent configurations (batch mode) to pick the less constrained
- Teaching why "add more tools / more steps / more context" is not free

Phrases: "which constraint will break", "is my agent overloaded", "constraint
triangle", "too many tools", "context is full", "score this agent config".

## When NOT to Use

- **Model-quality complaints** (hallucination, refusals) — Ch1 is explicit that
  the triangle is an architectural operational problem, not model quality.
- **Small agents** (under ~10 tools, short chains, low context fill) — no
  corner is under pressure; the score will read BALANCED and buys you nothing.
- **As a tool selector.** This scores the tool-orchestration *pressure*; use
  `rag-mcp-tool-selection` (Ch6) to actually filter the registry.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | steps / tools / disambiguity / window / used | `lib.score(config)` | per-constraint pressure + band | each pressure in 0-100; dominant_constraint is the max |
| 2 | complexity input | `lib.score_complexity(steps)` | complexity pressure | monotonic increasing in steps (exponential load) |
| 3 | tool input | `lib.score_tool_orchestration(count, disambiguable)` | tool pressure | ambiguous set scores higher than disambiguable at equal count |
| 4 | context input | `lib.score_context_utilization(window, used)` | context pressure | monotonic increasing in fill ratio (rot gradient) |
| 5 | full report | read `active_pressure_cycles` | Ch1 trade-off cycles fired by any high (>60) constraint | each cycle names a source constraint + edge + cascade |
| 6 | full report | read `recommendations` + `overall_band` | minimal-but-sufficient action per stressed constraint | OVERCONSTRAINED only when all three >60 or any >85 |
| 7 | list of configs | `lib.score_batch(configs)` | configs ranked by peak pressure | most-constrained config ranked first |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "Context windows are huge now — I'll just add every tool and all context." | Ch1: the three constraints "form a system of competing trade-offs." Adding tools consumes context for their definitions and adds selection ambiguity (tools→context→complexity). Bigger windows do not exempt you from the cycle. |
| "More reasoning steps make the agent smarter." | Ch1: "cognitive load increases exponentially ... compounding errors as the step count increases." Past a point, more steps lower reliability. Score complexity before lengthening the chain. |
| "The tool set is fine — the model just needs a better prompt." | Anthropic's principle (Ch1): if a human engineer can't say which tool to use, the agent can't either. That is tool-orchestration pressure from ambiguity, not a prompt problem. Set `--ambiguous` and see the score jump. |
| "Compact aggressively to free context — no downside." | Ch1's context→complexity→tools cycle: aggressive compaction "can inadvertently discard subtle but critical context whose importance only becomes apparent later," forcing more tool calls to reconstruct it. |
| "One corner is high but the others are fine, so we're OK." | The triangle is coupled. A single high corner fires a pressure cycle onto the other two; `active_pressure_cycles` shows which. Relieve the source, don't just watch the symptom. |

## Red Flags

- **All three corners critical (OVERCONSTRAINED).** You are past minimal-but-
  sufficient on every axis. Cut steps, filter tools, and retrieve selectively
  together — fixing one corner in isolation pushes pressure to the next.
- **Tool pressure high while `tools_disambiguable=true`.** The catalog is
  simply too large; filter it (RAG-MCP) rather than rewriting descriptions.
- **Context pressure high with short chains and few tools.** The task is
  stuffing raw data into the prompt; move to selective retrieval before it hits
  the rot gradient.
- **Score reads BALANCED but the agent still fails.** The failure is likely
  outside the triangle (model quality, a retrieval failure) — use
  `context-failure-classifier` or `enterprise-readiness-scorer` instead.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 8/8:
   - complexity/tool/context pressures are monotonic in their drivers
   - the bloated-MCP config is OVERCONSTRAINED and fires a pressure cycle
   - the balanced config is BALANCED with the dominant corner correct
   - batch ranks the most-constrained config first
2. **Verify CLI help.** `python cli.py --help` exits 0 and prints the SKILL.md
   description.
3. **Inspect one scenario.** `python cli.py scenario latency-spike` should show
   the bloated agent OVERCONSTRAINED and the balanced agent BALANCED on the
   same DevOps investigation.

## Security Posture

- **Prompt injection.** This skill consumes only numeric/boolean configuration
  (step counts, tool counts, token counts) — no free-text tool descriptions or
  documents enter it, so there is no injection surface in `lib.py`.
- **Data exfiltration.** No network calls, no file writes outside the explicit
  `--configs` path. `--json` output goes to stdout; the caller owns downstream
  piping.
- **Privilege escalation.** No shell invocation, no `eval`, no dynamic import.
  The only file read is the config JSON path the caller supplies (default: the
  bundled sample).
- **Misuse boundary.** The pressure scores are an operational planning aid, not
  an authorization control. Do not gate real permissions on this score; use
  `capability-authorization-gate` (Ch3) for authority decisions.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly, by Anthony Alcaraz and Sam Julien), Chapter 1 —
Defining Agentic AI, "The Agent Constraint Triangle" section. The three
constraints, the three cyclic trade-offs, and the minimal-high-signal-tokens
principle are the chapter's; the tool-disambiguation principle and the
attention-budget framing are anchored in Anthropic's "Effective Context
Engineering for Agents," and context rot in Chroma's needle-in-a-haystack
research, both named in the chapter.
