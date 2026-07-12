---
name: hierarchical-orchestration-router
description: |
  Expose ONE orchestrator to the agent instead of thousands of tools. Classifies
  a query into a department domain (Sales / Finance / Operations); routes to that
  domain's orchestrator when confidence exceeds 0.8, else orchestrates
  cross-domain. Within a domain, clusters tools by FUNCTION so an overloaded or
  failing tool fails over to a functionally-equivalent alternative from the same
  cluster (a Search Toolkit, a Metrics Toolkit), adapting parameters. Use when
  tool and agent counts have grown past a flat registry and you need routing,
  fault isolation, and no single point of failure. NOT for a single-domain
  system with a handful of tools (routing overhead buys nothing), NOT a
  replacement for tool retrieval within a domain (compose with
  rag-mcp-tool-selection there), NOT a security boundary (per-domain access
  control is a separate layer).
osmani-pattern: Inversion
ghosh-layer: Orchestration
chapter-source: "Agentic GraphRAG (O'Reilly) Ch6 — Tool Orchestration"
---

# Hierarchical Orchestration Router

## Overview

Discovery and retrieval find the right tool. Orchestration coordinates them at
scale. As tool counts grow from dozens to hundreds and agent counts from one to
many, you need infrastructure that routes requests, manages failover, and
enforces governance. This skill composes three ideas from the chapter's
"Orchestration at Scale" section.

**Inversion — one orchestrator, not thousands of tools.** Instead of exposing
every tool to the agent, expose exactly one: an intelligent orchestrator that
handles all complexity. The agent asks for an outcome; the orchestrator decides
how to achieve it. This is what lets traditional SaaS answer "why did we lose
deals last quarter?" in seconds instead of through menus and reports.

**Hierarchical routing.** Organizations don't just have more tools — they have
multiple MCP servers across departments (Sales, Finance, Operations), each
managing hundreds of tools. The router classifies a query into a domain by
semantics. High confidence (> 0.8) routes to that domain's orchestrator; low
confidence means the query spans domains, so it invokes cross-domain
orchestration (chapter Example 6-11). This buys fault isolation (a logistics
outage does not stop sales), scalable governance (global vs domain-local
policies), and progressive disclosure (users see only capabilities relevant to
their context).

**Functional clustering for resilience.** Within a domain, tools with similar
function are clustered for intelligent failover. Baidu's AI Search Paradigm
embeds tools by what they DO (DRAFT-refined docs + usage patterns), then
K-means++ groups them into functional toolkits. When the primary tool is
overloaded, the orchestrator seamlessly switches to a functionally-equivalent
alternative from the same cluster — a "Search Toolkit" of Baidu AI Search / ArXiv
MCP / Perplexity / OpenAI WebSearch — adapting parameters as it fails over. No
single point of failure.

## When to Use

- Multiple departments/domains each own many tools (or MCP servers)
- Queries arrive that may belong to one domain or span several
- You need failover: when one tool is overloaded, route to an equivalent
- You are turning a legacy multi-tool surface into a single natural-language entry

Phrases that invoke this skill: "route this query", "which domain owns this",
"cross-domain", "one orchestrator", "fail over to an equivalent tool",
"functional clustering", "hierarchical orchestration".

## When NOT to Use

- **A single-domain system with a handful of tools** — routing overhead exceeds
  benefit; use `rag-mcp-tool-selection` directly.
- **As tool retrieval within a domain** — this routes to a domain and names the
  functional clusters; picking the specific tool inside a domain is
  `rag-mcp-tool-selection` / the gateway.
- **As a security boundary** — per-domain access control (which agent may reach
  which domain) is a separate authentication layer; this is coordination.
- **When there is no failover set** — a domain with one tool per function has no
  functionally-equivalent alternative; the skill correctly reports a single
  point of failure rather than inventing one.

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Orchestration config JSON (domains + tools) | `lib.load_config(path)` | Config dict | Has `domains` (with keywords + tools) and `tools` (with key_topics) |
| 2 | Query + domains | `lib.identify_domain(query, domains)` | Best domain + margin confidence [0,1] | Single-domain query → confidence near 1.0; spanning query → near 0.5 |
| 3 | Query + domains + threshold | `lib.route_request(query, domains, threshold=0.8)` | `{routing: domain\|cross_domain, ...}` | confidence ≥ 0.8 → domain; < 0.8 → cross_domain with spanning domains |
| 4 | Tools | `lib.cluster_tools(tools)` | Functional toolkits (clusters) | Tools sharing a function land in one cluster; unrelated tools do not |
| 5 | Tools + failed tool | `lib.failover(tools, failed_tool)` | Alternative from the same cluster (highest reliability first) | Alternative shares the failed tool's function; single-member cluster reports SPOF |
| 6 | Query + config | `lib.orchestrate(query, config)` | Single-entry result (routing + available clusters) | The agent sees ONE call; complexity is hidden behind it |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|------------------------|---------------------|
| "Just expose all the tools and let the model pick." | At department scale that is the prompt-bloat crisis (Ch6 opening). Inversion exposes one orchestrator; the model reasons about outcome, not tool catalog. |
| "Route everything to the single best-matching domain." | A query about how inventory affects financial projections spans Operations and Finance. Forcing it into one domain returns a partial answer. The 0.8 confidence threshold is what detects the cross-domain case. |
| "Lower the confidence threshold so more queries route directly." | Below 0.8 the router deliberately treats the query as cross-domain — that is the feature, not a miss. Lowering it re-introduces the single-domain partial-answer failure for spanning queries. |
| "One tool per function is simpler than a cluster." | It is also a single point of failure. Functional clustering exists so an overloaded primary fails over to an equivalent — the chapter's resilience-through-redundancy point. |
| "Failover can pick any other available tool." | Failover must pick a FUNCTIONALLY-EQUIVALENT tool (same cluster). Routing a search query to a metrics tool because it was idle defeats the purpose. |

## Red Flags

- **Every query routes cross-domain.** The domain keywords are too generic or
  overlap heavily; sharpen them so a clear match scores near 1.0.
- **A cross-domain query routes to a single domain with high confidence.** The
  confidence metric is not margin-based; a spanning query must depress confidence.
- **Functionally-unrelated tools land in one cluster.** The clustering key
  (shared function) is too coarse — tighten `key_topics` so groups do not bridge.
- **Failover returns a tool from a different function.** The cluster lookup is
  broken; the alternative must be a same-cluster peer.
- **CLI `--help` exits non-zero.** SKILL.md / CLI mismatch; multi-harness invariant broken.

## Non-Negotiable Verification

1. **Run the benchmark battery.**
   ```
   python cli.py benchmark
   ```
   Confirm single-domain queries route to the correct domain at high confidence,
   the spanning query is detected as cross-domain (< 0.8), and failover of
   `baidu_ai_search` lands on a same-cluster search tool.

2. **Prove functional clustering is clean.**
   ```
   python cli.py cluster
   ```
   Confirm the Search / Metrics / Logs toolkits are distinct (metrics tools do
   not merge with logs tools).

3. **Prove the single-point-of-failure report.**
   Add a tool with a unique function to the config and run
   `python cli.py failover <that-tool>` — it must report no alternative, not
   invent a cross-function one.

4. **JSON round-trips.**
   ```
   python cli.py orchestrate "..." --json | python -c "import json,sys; json.load(sys.stdin)"
   ```

## Security Posture

- **Prompt injection.** Domain keywords and tool topics are author-controlled;
  treat them as untrusted if sourced from external registries. Routing decisions
  are deterministic given the config — a malicious keyword set could misroute, so
  the config is a governed artifact.
- **Data exfiltration.** No network calls in `lib.py`. The `# TODO(production):`
  seams in `identify_domain` (embedding classifier) and `cluster_tools`
  (K-means++ over embeddings) mark where real ML backends attach.
- **Privilege escalation.** Cross-domain routing must still honor per-domain
  access control — routing a query to Finance does not grant the agent Finance
  tools; that gate is `mcp-gateway-two-meta-tools` / IAM. This skill decides
  WHERE a query goes, not WHETHER the agent may go there.

## Composition

- **Sits above** `rag-mcp-tool-selection` / `mcp-gateway-two-meta-tools`: the
  router picks the domain; those pick the tool within it.
- **Consumes** `draft-tool-trust-verifier` output: functional clustering embeds
  tools "by what they do, not what they claim" (DRAFT-refined representations),
  and the `reliability` failover ordering is a performance-based trust score.
- **Feeds** the Enterprise AI OS control plane — the router is the semantic-search
  + action-governance step in the chapter's `EnterpriseAIOS.handle_agent_request`.
- **Pairs with** `federated-context-governance` — hierarchical routing needs a
  coherent per-domain context to route into.

## Source Attribution

Distilled from *Agentic GraphRAG* (O'Reilly), Chapter 6 — Tool Orchestration,
"Orchestration at Scale": "The Intelligent Orchestrator", "Hierarchical
Orchestration: When Scale Demands Structure" (Example 6-11), and "Functional
Clustering: Resilience Through Redundancy". Named references:

- MCP Gateway hierarchical orchestration — Enterprise Orchestrator → domain →
  tools; identify_domain confidence 0.8 routing threshold
- Baidu AI Search Paradigm — functional clustering via K-means++ over
  usage-pattern embeddings; Search Toolkit failover example
