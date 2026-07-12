---
name: tool-primitive-selector
description: |
  Choose how to expose an agent capability — a command-line interface (CLI) vs
  a Model Context Protocol server (MCP) vs a Skill — by profiling the capability
  along the chapter's dimensions and scoring three primitives across six feature
  axes, per Ch6 "Choosing the Right Primitive: CLIs, MCPs, and Skills". The
  chapter's frame: three primitives, three audiences on a personal-to-enterprise
  gradient, and CONVERGENCE not competition — a single capability is often
  exposed as more than one (the Google Workspace CLI ships a CLI surface, an MCP
  server mode, AND 100+ skills). CLI = deterministic composable command surface
  for the individual developer in build mode; MCP = runtime-discoverable governed
  endpoint with per-agent access control for teams / enterprise / background
  agents; SKILL = encoded judgment (what to do, in what order) for the model
  itself, authored first regardless. Use when deciding how to wrap a capability,
  or justifying a CLI-vs-MCP-vs-Skill choice in a design doc. NOT for RETRIEVING
  which tools to load at runtime (that is rag-mcp-tool-selection), NOT for
  picking a specific vendor product, NOT when the platform already mandates a
  primitive (just adopt it).
osmani-pattern: Decision-Table
ghosh-layer: Meta
chapter-source: "Agentic Graph RAG (O'Reilly) Ch6 — Tool Orchestration — Choosing the Right Primitive: CLIs, MCPs, and Skills"
references:
  - "Jiquan Ngiam — three-primitives-three-audiences taxonomy + personal-to-enterprise gradient self-report"
  - "Dharmesh Shah — CLI training-data density advantage over MCP"
  - "CLI-Anything (HK Univ. of Data Science) — the wrap-everything argument (structured I/O, self-description, determinism)"
  - "Armand Ruiz / Addy Osmani — Google Workspace CLI + ADK McpToolset convergence (one tool, three interfaces)"
---

# Tool Primitive Selector

## Overview

You have three distinct ways to give an agent a capability, and Ch6 is explicit
that they are **converging, not competing**. The Google Workspace CLI is one
tool with three interfaces: a CLI surface, a built-in MCP server mode, and 100+
prebuilt skills. So the question is rarely "which one?" but "which PRIMARY
primitive, and what else should this ALSO be exposed as?"

Each primitive answers a different question for a different audience:

- **CLI** answers *"how does the agent PERFORM this operation?"* Deterministic
  command surface, Unix-pipe composable (`curl|jq|grep` beats four MCP calls),
  self-describing via `--help`, invokable with no model in the loop. Models have
  internalized CLI grammar from millions of Stack Overflow answers and man pages.
  Costs ~400 tokens after dynamic discovery. Audience: the individual developer
  in build mode / CI, on a machine they trust.
- **MCP** answers *"how does the agent CONNECT to this service securely?"*
  Model-callable server with schemas, runtime-discoverable, OAuth + scoped
  per-agent access control through gateways. Static schemas cost 23K-50K tokens
  before any reasoning, which is why runtime retrieval is mandatory at scale.
  Audience: enterprise teams, non-developer users, and unsupervised background
  agents that cannot be granted broad access.
- **SKILL** answers *"WHAT should the agent do, and in what order?"* Encoded
  judgment / procedure the model reads. Natural language, no install, ~100
  tokens, works for everyone. It is the meta-layer that makes the other two
  effective. Author it first regardless.

The selector profiles a capability along the chapter's four dimensions — who
runs it, when, where, what access — plus a composability need, then scores the
three primitives across six feature axes (deterministic surface,
runtime-discoverable, access control, encodes judgment, personal fit, enterprise
fit). It returns a primary recommendation AND an `also_expose_as` list, and
places the audience on the personal-to-enterprise gradient with its governance
implication.

## When to Use

- Deciding whether to wrap a new capability as a CLI, an MCP server, or a Skill
- Justifying a CLI-vs-MCP-vs-Skill choice in an architecture / design doc
- Locating a capability on the personal-to-enterprise gradient and naming the
  governance it implies (OS-level trust vs per-agent access control)
- Capturing convergence: which secondary interfaces a capability should ALSO ship

Phrases: "CLI vs MCP vs skill", "how should I expose this tool", "which
primitive", "should this be an MCP server or a CLI", "personal-to-enterprise
gradient", "per-agent access control", "convergence not competition".

## When NOT to Use

- **Retrieving which tools to load at runtime.** That is the *other* Ch6 skill,
  `rag-mcp-tool-selection` — it filters a large registry of already-existing
  tools for a query. This skill decides how to WRAP a capability in the first
  place. Different question; no overlap.
- **Picking a specific product.** This selects the primitive class, not
  Neo4j-vs-Neptune or one MCP vendor over another.
- **A platform-mandated primitive.** If the org standardizes on MCP gateways or
  the deployment is CLI-only, adopt it; the scoring is moot.
- **A capability whose value is purely procedural knowledge with no callable
  surface.** It is a Skill by definition — you do not need to score it, though
  running the selector will confirm it.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Capability profile (audience, invocation, access-control, needs-model, composability) | `lib.score_primitives(cap)` | `[(primitive, score), ...]` sorted desc | weighted dot-product of capability weights and per-primitive axis scores |
| 2 | Same | `lib.recommend_primitive(cap)` | `{recommended, also_expose_as, scores, rationale}` | deterministic_command → cli; runtime discovery + access control → mcp; judgment → skill |
| 3 | An audience | `lib.gradient_position(audience)` | `{position, tool_mix, governance, primitive_bias}` | individual = personal/cli-biased; enterprise = mcp-biased + per-agent access control |
| 4 | A governed enterprise deterministic capability | `lib.recommend_primitive(cap)` | `also_expose_as` contains the convergent second interface | enterprise deterministic surfaces BOTH mcp (primary) and cli |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "MCP is the modern standard — wrap everything as an MCP server." | MCP schemas cost 23K-50K tokens before the agent reasons, and CLI-based composition is the path of least resistance for build-mode work (models trained on far more CLI examples than MCP). MCP is decisive for *governed, unsupervised, enterprise* access — not a universal default. Profile the audience first. |
| "It's just a CLI vs MCP choice, pick one and move on." | That is the competition frame the chapter rejects. The Google Workspace CLI is one tool with three interfaces. The selector returns `also_expose_as` precisely because a deterministic capability can ALSO be a governed MCP endpoint, and a governed capability can ALSO ship a CLI. Convergence, not either/or. |
| "Skills are just docs — skip them and give the agent the tool." | Skills encode the judgment for using the other two effectively; the chapter's tip says author them *first regardless*. Without the Skill, the agent has the CLI/MCP but not the when-and-in-what-order. That is why skills stay constant across the whole personal-to-enterprise gradient. |
| "This capability is deterministic, so it must be a CLI — access control is someone else's problem." | Access control is exactly what tips a deterministic capability from CLI to MCP up the gradient. A CLI runs through the OS permission model, a blunt instrument for agent-level scoping. When an enterprise needs per-agent least-privilege (`allowed_tools`), the same deterministic capability becomes an MCP endpoint — with the CLI kept as the developer-facing surface. |
| "The gradient is preference — a good dev can run CLIs at any scale." | The chapter calls the CLI-to-MCP shift *structural, not preference*. A solo developer can trust a CLI pipeline on their own machine; an enterprise running agents on cron schedules cannot grant those agents the same broad access. The governance requirement, not taste, moves the capability. |

## Red Flags

- **Everything recommends `skill`.** You have set every capability's invocation
  to `judgment_guidance`. Re-profile: does the capability have a callable
  surface (CLI/MCP) or is it genuinely pure procedure? If everything is
  judgment, nothing is being executed.
- **Enterprise capability recommends `cli` with no `also_expose_as`.** An
  enterprise / background-agent capability with real access-control needs should
  surface an MCP endpoint. If it did not, the `needs_per_agent_access_control`
  flag is probably unset — re-check the governance requirement.
- **A deterministic, composable capability recommends `mcp` for a solo dev.**
  Mismatch: for the individual / build-mode end of the gradient, a CLI is the
  path of least resistance. Re-check the audience.
- **`also_expose_as` is empty for a capability everyone agrees is "one tool,
  three interfaces."** The convergence is not being captured. Confirm the
  invocation and audience flags reflect the real deployment.

## Non-Negotiable Verification

1. **Run the benchmark battery.** `python cli.py benchmark` must report 10/10:
   - individual + deterministic_command → cli
   - enterprise + runtime discovery + access control → mcp
   - judgment_guidance → skill for every audience
   - convergence: enterprise governed deterministic surfaces both mcp (primary)
     and cli (in `also_expose_as`)
   - high Unix-pipe composability tips an individual to cli
   - gradient: individual = personal/cli-biased, enterprise = mcp-biased with
     per-agent access-control governance
   - `also_expose_as` never duplicates the recommended primitive
2. **Run both scenarios.** `python cli.py scenario enterprise-deploy-tool`
   recommends mcp with cli also-exposed; `python cli.py scenario
   code-review-procedure` recommends skill.
3. **Verify CLI help.** `python cli.py --help` exits 0 and prints this
   SKILL.md description (CLAUDE.md CLI mandate).

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, forthcoming) Ch6 — Tool
Orchestration, section "Choosing the Right Primitive: CLIs, MCPs, and Skills"
and its subsections (the wrap-everything argument, three-primitives-three-
audiences, the personal-to-enterprise gradient, per-agent access control,
convergence-not-competition). Key voices named in the chapter: Jiquan Ngiam
(the three-audience taxonomy + self-reported personal-vs-work setups), Dharmesh
Shah (CLI training-data density), CLI-Anything from the HK University of Data
Science (structured I/O + self-description + determinism), and Armand Ruiz /
Addy Osmani (the Google Workspace CLI + ADK McpToolset convergence — one tool,
three interfaces). This is the Decision-Table primitive at the Meta layer:
it selects how to expose a capability; it does not implement the capability.
