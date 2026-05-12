---
name: rag-mcp-tool-selection
description: |
  Select the top-K tools from a registry of 30+ MCP / AWS / internal-API tools
  for a given natural-language query, replacing MCP's tools/list dump with a
  RAG-style filter that reduces prompt tokens 50-90%. Three-step pipeline:
  retrieve / validate / format. Use when the agent has access to many tools
  and prompt bloat is killing response quality. NOT for cases with under 10
  tools (just include them all), NOT a replacement for an MCP server (this
  filters what an MCP server exposes), NOT for one-off scripts where the
  toolset is known and fixed.
osmani-pattern: Generator
ghosh-layer: Primitive
chapter-source: "Agentic Graph RAG (O'Reilly) Ch5/Ch6 — Tool Orchestration"
---

# RAG-MCP Tool Selection

## Overview

The Model Context Protocol's `tools/list` operation returns every tool an agent
has access to. At enterprise scale this consumes the context window before the
agent has done any reasoning. The book's worked anchor is Block's Goose agent —
12,000 employees, 60+ MCP servers — where employees enabled every server
"just in case" and tool descriptions ate the entire prompt budget.

The chapter cites measurable degradation from the RAG-MCP research:

| Tools available | Selection accuracy (baseline LLM) |
|-----------------|------------------------------------|
| 10              | Near-perfect |
| 100             | Begins to degrade |
| 1,000           | Below 40% |

RAG-MCP replaces `tools/list` with a semantic search over tool metadata.
Reported benchmarks: 50-70% prompt-token reduction, selection accuracy
13.62% → 43.13%, response time -60%. This skill is the smallest unit of
that pattern — a function you can run before any LLM call to filter the
tools you actually inject.

## When to Use

Trigger contexts:
- Building an MCP-based agent with 30+ tools exposed
- A user asks the agent something that could match many tools, you want top-K
- Migrating an existing single-shot prompt to MCP and the prompt is too big
- Authoring a new tool registry — you want to verify each tool is findable

Phrases that should invoke this skill: "filter the tools", "which tools should
the agent use", "the prompt is too big", "RAG-MCP", "tool selection",
"reduce prompt bloat".

## When NOT to Use

- **Under 10 tools.** The book is explicit: with 10 tools the model achieves
  near-perfect selection. Filtering buys you nothing and adds latency.
- **Fixed-pipeline scripts** where the tool sequence is hardcoded — no
  retrieval needed.
- **As a replacement for an MCP server.** This skill picks WHICH tools an
  MCP server should expose for a query; it does not replace the server.
- **As a quality gate.** Use the SkillNet five-dimension framework (Ch6)
  for skill-quality evaluation, not this skill.
- **For multi-tool workflow planning.** This returns top-K tools by query
  similarity, not a dependency graph of tools. For collaborative-tool
  retrieval, see Baidu's COLT (Ch6) — out of scope here.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Tool registry JSON (Toolshed five-component shape per tool) | `lib.load_registry(path)` | List of tool dicts | `len(registry) > 0`; each tool has `name`, `description`, `synthetic_queries`, `key_topics` |
| 2 | User query string | `lib.retrieve(query, registry, top_k=5)` | Top-K scored tools (sorted by descending score) | At least one tool with score > 0; otherwise registry has no relevant coverage |
| 3 | Top-K scored tools | `lib.validate(scored, query)` | Filtered list (drops obvious-but-wrong matches) | Validated count ≤ top-K; verify domain-token overlap |
| 4 | Validated tools | `lib.invoke_prompt(validated, query)` | Formatted prompt-injection string | String contains only the validated tool descriptions (no full registry leakage) |
| 5 | Baseline + filtered prompts | `lib.approximate_token_count(...)` on both | Reduction percentage | Reduction > 50% for registries with 30+ tools; if not, registry is too small or retrieval is broken |
| 6 | Selected tool names | (your agent runtime) calls the chosen tool via boto3 / MCP / etc. | Tool call result | Tool call returns shaped data; if AccessDenied or signature error, the wrong tool was picked |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|--------------------|
| "I'll just send all tools — context windows are big now." | The Block / Goose anchor in Ch5 is 60+ MCP servers exposing thousands of tools. Context windows expand; tool catalogs expand faster. The architectural shape is permanent. |
| "Word-overlap retrieval is too simple — I should use embeddings first." | Production should use embeddings. The seam in `lib.score_tool` is one function. Replace it; the contract (returns float, higher = more relevant) is stable. The spike validates the *pipeline*, not the retriever. |
| "Validation can be skipped — top-K retrieval is enough." | The chapter explicitly notes the false-positive failure mode: a tool that seems relevant by description keywords but serves a different purpose. The validate step is cheap (domain-token check); leaving it out re-introduces a known failure mode. |
| "I should pick top-1 instead of top-3 — fewer tools = less bloat." | SkillsBench finding cited in Ch6: 2-3 focused skills per task is optimal. Top-1 forces a brittle commitment; top-3-to-5 gives the LLM room to pick the right one and reason about adjacent options. |
| "The token-reduction percentage doesn't matter if accuracy is high." | The chapter pairs both metrics: 50-70% token reduction AND 13.62% → 43.13% accuracy. They compose. Optimizing one without the other defeats the architectural intent. |

## Red Flags

- **Token reduction below 30%.** The registry is too small (under ~15 tools) for the filter to pay its way. Either skip the filter or grow the registry.
- **Top scored tool has score < 0.1 across many queries.** Tool descriptions are too generic; rewrite them or add synthetic queries (Toolshed pattern).
- **Same tool wins every query.** Either the registry has a "swiss army knife" tool with too-broad descriptions, or the retriever is degenerate. Inspect tool tokens and de-duplicate semantic hooks.
- **CLI `--help` exits non-zero.** SKILL.md / CLI mismatch; the multi-harness invariant is broken.
- **No domain-token overlap between validated tools and query.** Validation is collapsing to top-K-only (it should drop description-keyword false positives).

## Non-Negotiable Verification

Before shipping a downstream agent built on this skill:

1. **Run the benchmark battery.**
   ```
   python cli.py benchmark
   ```
   Confirm avg reduction > 50% across 8 scenarios. The shipped registry
   `sample-aws-tools.json` produces 88.2% avg.

2. **Inspect at least one filtered prompt visually.**
   ```
   python cli.py show-prompt "your query here"
   ```
   Confirm the selected tools are the *right* tools (not just plausible by
   description). The spike documented one known failure mode: the query
   "audit who changed the production database" picks `dynamodb_scan` over
   `cloudtrail_lookup_events` because the simple word-overlap scoring rewards
   semantic-hook density. Production should swap to embeddings.

3. **JSON output round-trips.**
   ```
   python cli.py select "..." --json | python -c "import json,sys; json.load(sys.stdin)"
   ```
   No exception means the CLI is harness-portable.

4. **Domain test against the DevOps latency scenario.** Run the bundled
   notebook `notebooks/spike-a-rag-mcp-tool-selection.ipynb`. Confirm the
   `moto`-mocked CloudWatch Logs Insights call returns shaped data and the
   reduction percentage prints.

## Security Posture

- **Prompt injection.** Tool registry descriptions are author-controlled
  content. If you ingest descriptions from untrusted sources (auto-scraped
  API docs, community contributions), sanitize before indexing — a malicious
  description could embed instructions that bias retrieval. The Toolshed
  five-component representation makes the injection surface explicit; treat
  `description` and `synthetic_queries` as untrusted strings until validated.
- **Data exfiltration.** This skill emits the filtered prompt back to the
  caller. No external network calls in `lib.py`. CLI `--json` output is
  printed to stdout; the caller is responsible for downstream piping.
- **Privilege escalation.** No shell invocation, no concatenated input to
  shell, no file writes outside the registry path. The registry path comes
  from `--registry` flag or the bundled default — both are explicit.

## Composition

- **Composes with** Anthropic `agent-skills` Generator pattern at the
  Osmani layer and Ghosh Primitive layer. The output (a filtered prompt
  string + selected tool list) is consumable by any orchestration layer
  above.
- **Composes with** the MCP Gateway pattern (Writer's two-meta-tool design,
  Ch5) — the gateway can call this skill internally to decide which of its
  registered tools to surface.
- **Replaces, does not compose with,** raw `tools/list` MCP calls when the
  registry exceeds ~15 tools.
- **Pairs with** evaluation discipline from `agentic-graph/self-evolution/`
  skills (forthcoming) — measure top-K accuracy on a labeled query set
  before deploying.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly, AnthonyAlcaraz / forthcoming),
Chapter 5/6 — Tool Orchestration. Key references named in the chapter:

- RAG-MCP framework (selection-accuracy and token-reduction benchmarks)
- Block / Goose enterprise anchor (12,000 employees, 60+ MCP servers)
- Toolshed (Zhu et al.) — five-component enhanced tool representation
- COLT (Baidu) — collaborative tool retrieval graph (out of scope, see Ch6)
- Anthropic Agent Skills specification — `SKILL.md` format
- Microsoft Core AI Platform research on prompt bloat at MCP scale
- Writer enterprise MCP gateway — two-meta-tool architecture

This skill is the smallest Generator-pattern primitive from that chapter,
suitable as a starting point for any agent that needs to filter a large
tool registry before invocation.
