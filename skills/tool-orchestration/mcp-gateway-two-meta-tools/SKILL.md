---
name: mcp-gateway-two-meta-tools
description: |
  Build a gateway that exposes any-size tool registry through just two
  meta-tools: search(query) and execute(tool_name, **params). Tool
  descriptions stay outside the prompt entirely — the agent's prompt
  cost is constant regardless of registry size. Use when you need
  per-tenant tool segmentation, per-agent access policies, or are
  scaling to hundreds-of-tools where even top-k injection (rag-mcp-
  tool-selection) bloats prompts. NOT for cases under 30 tools where
  RAG-MCP top-K injection is simpler. NOT a security layer on its own
  — bring an IAM/RBAC source-of-truth for the access_filter.
osmani-pattern: Generator
ghosh-layer: Workflow
chapter-source: "Agentic Graph RAG (O'Reilly) Ch6 — Tool Orchestration"
---

# MCP Gateway — Two-Meta-Tool Architecture

## Overview

Writer's production enterprise MCP gateway pattern. RAG-MCP retrieves top-K
tools and injects descriptions into the prompt. The Gateway pattern keeps
descriptions entirely *outside* the prompt — the agent sees exactly two
tools regardless of how many the gateway manages.

```
Agent ─── search(query)   ───▶ [tool_name_1, tool_name_2, ...]
       └── execute(name)  ───▶ {tool, params, result}
```

The book cites Writer running this at "hundreds of connectors and thousands
of possible tool calls" without prompt bloat. Phil Fersht's research (HFS /
Cognizant) found 73% of organizations deploying agentic AI run multi-agent
systems averaging 12 agents per system, with governance frameworks failing
once the count exceeds five. The gateway is the enforcement point where
tool access policies scale with agent proliferation.

## When to Use

- Tool registry exceeds ~30 tools and even RAG-MCP top-K injection bloats
- Multi-tenant agents where each customer should see only their tools
- Per-agent access policies (CS agent sees CRM, finance agent sees reports)
- Compliance domains where the prompt must not name unauthorized tools
- Migrating from individual MCP servers to one gateway endpoint

## When NOT to Use

- Tool registry has fewer than 30 tools — use `rag-mcp-tool-selection` instead
- One-off scripts with hardcoded tool flow
- As the only security layer — gateway is *enforcement*, IAM/RBAC is *source-of-truth*
- For multi-tool workflow planning — see Baidu COLT (Ch6) for tool-graph retrieval

## Process

| Step | Input | Action | Output | Verification |
|------|-------|--------|--------|--------------|
| 1 | Tool registry JSON | `Gateway.from_registry_file(path)` | Gateway instance | `len(gateway.registry) > 0` |
| 2 | (Optional) Role-based access policy | `Gateway(registry=..., access_filter=fn)` or `example_access_filter_devops` | Gateway scoped to one role | `len(gateway._visible()) < len(gateway.registry)` for restricted roles |
| 3 | Backend bindings (boto3 / HTTP / MCP forward) | `gateway.register_executor("tool_name", fn)` per tool | Wired gateway | Each `execute` call returns real backend results, not dry-run |
| 4 | User query | `gateway.search(query, top_k=5)` | List of `{name, score}` — descriptions NOT included | Result is JSON-serializable; no tool descriptions leaked |
| 5 | Selected tool name + parameters | `gateway.execute(tool_name, **params)` | `{tool, params, result}` | Access filter raises `PermissionError` for out-of-scope tools |
| 6 | Constant-prompt budget check | `gateway.agent_prompt(query)` | Prompt string | `len(prompt)` does NOT scale with registry size |

## Rationalizations

| Agent rationalization | Documented rebuttal |
|-----------------------|---------------------|
| "RAG-MCP top-K injection is good enough." | True at 30-100 tools. Falls over at thousands per the chapter's Writer / HFS anchors. Gateway is the next architectural step, not a competing option. |
| "The agent needs to see descriptions to decide." | The agent calls `search` first, gets ranked names, then can inspect one via a discovery tool if needed. Net cost is two round-trips for ambiguous cases vs one bloated prompt always. |
| "Access policies should live in the agent's system prompt." | System-prompt rules degrade under adversarial input (the chapter cites IBM AI Engineer talk + Microsoft Core AI Platform research). Gateway-enforced policies are mechanical, not prompted. |
| "Per-tenant separation isn't worth the complexity." | At scale every multi-tenant SaaS hits this — see Writer's anchor. Defer at small scale, but design the gateway so the access_filter seam exists from day one. |

## Red Flags

- `Gateway.search` returns full tool descriptions — leakage breaks the constant-prompt invariant
- `execute` succeeds for tools that `access_filter` should have rejected — IAM/gateway-policy mismatch
- Agent prompt grows with registry size — gateway is being bypassed somewhere
- One tool wins every `search` call — index has degenerate semantic-hooks; fix the registry, not the retriever

## Non-Negotiable Verification

1. **Constant-prompt invariant.** `len(gateway.agent_prompt(q))` must be identical for a 30-tool registry and a 300-tool registry. If it grows, the gateway is leaking descriptions.
2. **Access enforcement.** With `access_filter=example_access_filter_devops`, calling `gateway.execute("secrets_manager_get_secret_value", ...)` MUST raise `PermissionError` — secrets are not in the devops topic set.
3. **Search returns names not descriptions.** Inspect `gateway.search(q)` output — every element is `{name, score}`, no `description` key present.
4. **CLI `--help` exits 0.** Multi-harness invariant: the skill must be runnable from any CLI harness.

## Security Posture

- **Prompt injection.** Tool descriptions never enter the prompt — major reduction in injection surface vs RAG-MCP. The `search` call still uses the description-text for retrieval, so a malicious description biases retrieval but never reaches the LLM verbatim.
- **Data exfiltration.** `execute` calls user-registered executors with `**params`. Validate params at the executor boundary (this skill does not — it's a substrate primitive).
- **Privilege escalation.** Access filter is the enforcement seam. Wire it to your IAM/RBAC source-of-truth. Do not trust the agent to enforce its own permissions.

## Composition

- **Pairs with** `rag-mcp-tool-selection` (sibling Ch6 skill) — gateway uses the same retriever internally (`lib.score_tool` swap point) but exposes a different API shape to the agent.
- **Pairs with** AAuth identity primitives (Posta canonical) for per-agent access tokens flowing through `access_filter`.
- **Inputs** can be **outputs** of `enhance_tool_representation` (Toolshed pattern, Ch6) — richer per-tool descriptions improve `search` retrieval without affecting agent prompt cost.

## Source Attribution

Distilled from *Agentic Graph RAG* (O'Reilly), Chapter 6 — Tool Orchestration. Specific references:

- Writer's production enterprise MCP gateway (three-layer architecture: OpenAPI/Postman ingestion + Palmyra X5 description refinement + two-meta-tool surface)
- Phil Fersht's HFS / Cognizant research on multi-agent governance failure above 5 agents
- Microsoft Core AI Platform research on prompt bloat at MCP scale
