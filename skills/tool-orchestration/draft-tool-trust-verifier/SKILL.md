---
name: draft-tool-trust-verifier
description: |
  Establish trust in a tool by verification, not by its self-description. Flags
  marketing-gamed tool descriptions ("industry-leading", "trusted by Fortune
  500"), requires structured testable capabilities instead of free-text claims,
  tracks a performance-based trust score (neutral start, successes up, failures
  and slow calls down), and runs the DRAFT loop — gather boundary-probing
  experience, learn the gap between documentation and reality, rewrite an
  AI-optimized spec — until the doc converges with actual behavior. Use when a
  tool registry ingests third-party or provider-authored descriptions that may
  be optimized for discovery over accuracy. NOT for tools you authored and
  fully control, NOT a functional test framework (it discovers doc-vs-reality
  gaps, it does not assert business correctness), NOT a security scanner.
osmani-pattern: Reviewer
ghosh-layer: Workflow
chapter-source: "Agentic Graph RAG (O'Reilly) Ch6 — Tool Orchestration"
---

# DRAFT Tool-Trust Verifier

## Overview

Tool discovery that depends on descriptions has a failure mode the chapter names
directly: providers optimize descriptions for DISCOVERY, not accuracy. "Most
effective solution." "Trusted by Fortune 500." "Industry-leading performance."
When every tool claims to be the best, keyword-gamed descriptions defeat the
retrieval algorithms — surfacing the best marketers rather than the best tools.
At scale (thousands of tools) you cannot manually verify claims.

The chapter's answer is verification-based trust, on two mechanisms:

1. **Structured, verifiable capabilities.** A tool does not get to claim it
   "analyzes customer sentiment with unparalleled accuracy." It declares the
   capability `sentiment_analysis` with specific input and output types that can
   be tested.
2. **Performance-based trust scores.** Every tool begins neutral. Successful
   executions raise trust; failures, high latency, or degradations lower it. The
   orchestrator learns to prioritize tools that are consistently reliable.

Baidu's **DRAFT** (Documentation Refinement through Automated Feedback and
Testing) operationalizes this as a continuous learning loop that mirrors how a
developer learns a new API:

- **Experience Gathering** — an explorer probes tool boundaries, seeks edge
  cases, maps failure modes, and enforces diversity to avoid redundant tests.
- **Learning from Experience** — analyze the gap between documentation and
  reality (claims "any text input" but fails on Unicode; undocumented
  payload-size latency). Systematic discovery of true capabilities, not error
  logging.
- **Documentation Rewriting** — generate an AI-optimized spec reflecting the
  discovered reality: parameter types, ranges, error conditions, real
  performance. Iterate until the doc converges with actual behavior.

DRAFT sidesteps the trust problem: why worry about providers gaming descriptions
when your system discovers the truth anyway? This parallels Writer's gateway,
which rewrites descriptions preemptively (before deployment) rather than
iteratively (after observing failures) — both treat tool descriptions as an
active interface, not static metadata.

## When to Use

- A tool registry ingests provider-authored or third-party descriptions
- Retrieval keeps surfacing "best-marketed" tools that then underperform
- You want a trust score to rank functionally-equivalent tools by reliability
- You are onboarding a new tool and its documentation is human-friendly prose,
  not an agent-parseable spec

Phrases that invoke this skill: "verify what this tool does", "the tool
description is gamed", "trust score", "DRAFT", "rewrite the tool docs",
"doc vs reality".

## When NOT to Use

- **Tools you authored and fully control** — you already know the true behavior;
  write the structured spec directly.
- **As a functional test framework.** DRAFT discovers doc-vs-reality gaps
  (constraints, error conditions, performance); it does not assert business
  correctness. Keep your unit/integration tests.
- **As a security scanner.** It measures capability and reliability, not
  vulnerability. Pair with `agent-shield` / SkillSpector for security.
- **When there is no gap to find** — a tool whose docs already match its behavior
  converges immediately; DRAFT adds nothing.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Tool JSON (claimed_description + declared_capabilities + behavior) | `lib.load_tool_under_test(path)` | Tool dict | Has `claimed_description` and a `behavior` model |
| 2 | Tool dict | `lib.verify_claims(tool)` | Marketing-phrase flags + structured-capability count | Gamed phrases flagged; `verifiable` True only if every capability has name+input_types+output_types |
| 3 | Execution history | `lib.TrustScore().record(success, latency_ms)` per call | Evolving trust score | Neutral 0.5 start; successes up, failures + slow calls down |
| 4 | Tool + probe set | `lib.gather_experience(tool, probes)` | Observations (success/latency/error) | Duplicate probes deduped (diversity enforced) |
| 5 | Tool + observations | `lib.learn_from_experience(tool, obs)` | Doc-vs-reality gap report | Discovered error conditions + `gap_over_promises_any_text` |
| 6 | Tool + learning | `lib.rewrite_documentation(tool, learning)` | AI-optimized refined spec | Refined spec lists real constraints + performance, drops marketing |
| 7 | Tool + probes | `lib.run_draft(tool, probes)` | Full gather→learn→rewrite result | Refined spec's error_conditions match discovered failures |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|---------------------|
| "The tool description says it handles any text input — trust it." | DRAFT's worked example is exactly this: a tool claims "any text input" but fails on Unicode. Descriptions are gamed for discovery; probe the boundary before trusting the claim. |
| "Free-text capability descriptions are fine." | The chapter requires structured, enumerable capabilities with input/output types precisely because free text cannot be tested. `verify_claims` flags a capability with null input_types as unverifiable. |
| "One trust score for the tool is enough — reliability is fixed." | Trust is performance-based and evolves: successes up, failures and slow calls down. A tool that degrades (technical debt, maintenance windows) must lose trust over time, not keep a stale score. |
| "Just log the errors when the tool fails." | Learning-from-experience is systematic discovery of TRUE capabilities, not error logging. It converts observed failures into refined constraints (max length, ASCII-only) that reshape future selection. |
| "Rewriting docs is the provider's job." | Raw provider docs are written for humans and cause tool-calling errors when used as-is (Writer's finding). The rewrite — preemptive or iterative — is what makes the description an accurate agent interface. |

## Red Flags

- **A capability with `input_types: null` marked verifiable.** The structured-
  capability check is broken; unverifiable free-text is passing.
- **DRAFT reports `converged: true` on a tool with known undocumented limits.**
  The probe set is not diverse enough — it never hit the boundary. Add edge-case
  probes (empty, oversized, non-ASCII).
- **Trust score never moves.** `record` is not being called on real execution
  outcomes; the score is decorative.
- **Refined spec still contains marketing language.** The rewrite copied the
  claim instead of assembling from observations.
- **CLI `--help` exits non-zero.** SKILL.md / CLI mismatch; multi-harness invariant broken.

## Non-Negotiable Verification

1. **Run the benchmark battery.**
   ```
   python cli.py benchmark
   ```
   Confirm marketing phrases are flagged, capabilities are NOT fully verifiable
   (the sample's second capability has null input_types), the three undocumented
   constraints are discovered, and a flaky-tool history drives trust below 0.5.

2. **Prove the gap is discovered, not assumed.**
   ```
   python cli.py learn
   ```
   The claim says "any text input"; the learning report must show
   `gap_over_promises_any_text: True` with the discovered error conditions.

3. **Prove the refined spec drops marketing.**
   ```
   python cli.py rewrite
   ```
   The refined description states real constraints and performance; it contains
   none of the flagged marketing phrases.

4. **JSON round-trips.**
   ```
   python cli.py draft --json | python -c "import json,sys; json.load(sys.stdin)"
   ```

## Security Posture

- **Prompt injection.** A gamed description can embed instructions. This skill
  never trusts the description for behavior — it probes the tool. The
  `# TODO(production):` seam in `TrustScore.record` marks where SLO-weighted
  penalties and observation decay go; the explorer's probe issuance is the
  production seam where real (sandboxed) calls replace `_simulate`.
- **Data exfiltration.** No network calls in `lib.py`; behavior is simulated
  from declarative rules. In production, run the explorer's probes in a
  sandbox so boundary-probing cannot trigger real side effects.
- **Privilege escalation.** DRAFT probes should be read-only / idempotent —
  boundary exploration must not invoke destructive tool operations. Gate probe
  generation behind the same sensitive-action policy as `information-flow-control-gate`.

## Composition

- **Feeds** `skill-quality-evaluator` and retrieval: the DRAFT-refined
  description improves `search` accuracy, and the trust score is a ranking
  signal for functionally-equivalent tools.
- **Feeds** `hierarchical-orchestration-router` functional clustering — DRAFT-
  refined representations are what the clusterer embeds ("embed tools based on
  what they do, not what they claim").
- **Pairs with** `information-flow-control-gate` — DRAFT learns what a tool does;
  IFC governs what data may flow into it.
- **Parallels** the MCP Gateway's preemptive description rewrite (Palmyra X5);
  DRAFT is the iterative, post-observation form of the same insight.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly), Chapter 6 — Tool Orchestration,
sections "The Trust Problem: When Tools Game the System", "Verification-based
trust", and "DRAFT: Learning what tools actually do". Named references:

- Baidu AI Search Paradigm — DRAFT (Documentation Refinement through Automated
  Feedback and Testing); three-phase loop
- Writer enterprise MCP gateway — preemptive description rewrite (Palmyra X5),
  the same insight applied before deployment rather than after
