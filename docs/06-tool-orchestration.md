# Chapter 6 — Tool Orchestration

- **Skills folder:** `skills/tool-orchestration/` (8 skills)
- **Notebook:** `notebooks/ch6-tool-orchestration.ipynb`
- **Prev:** [Chapter 5](./05-reasoning-planning.md) &nbsp;|&nbsp; **Next:** [Chapter 7](./07-self-evolution.md)

## Role in the architecture

Executes the horizontal graph as tools. RAG-MCP selects the top-K tools instead of dumping the whole registry, a two-meta-tool gateway keeps descriptions out of the prompt, information-flow-control secures chained tools, and trust is established by verification not self-description.

## In the running DevOps investigation

From 30+ AWS/MCP tools, only the ones relevant to a latency probe (CloudWatch, X-Ray, logs) are selected; they are invoked through the gateway; data flow between chained tools is policy-checked.

## Skills

| Skill | What it does | CLI |
|-------|--------------|-----|
| `draft-tool-trust-verifier` | Establish trust in a tool by verification, not by its self-description. | `python skills/tool-orchestration/draft-tool-trust-verifier/cli.py --help` |
| `federated-context-governance` | Govern agent-configuration drift once tool orchestration scales from one developer to a team. | `python skills/tool-orchestration/federated-context-governance/cli.py --help` |
| `hierarchical-orchestration-router` | Expose ONE orchestrator to the agent instead of thousands of tools. | `python skills/tool-orchestration/hierarchical-orchestration-router/cli.py --help` |
| `information-flow-control-gate` | A deterministic security-policy layer for chained tools. | `python skills/tool-orchestration/information-flow-control-gate/cli.py --help` |
| `mcp-gateway-two-meta-tools` | Build a gateway that exposes any-size tool registry through just two meta-tools: search(query) and execute(tool_name, **params). | `python skills/tool-orchestration/mcp-gateway-two-meta-tools/cli.py --help` |
| `rag-mcp-tool-selection` | Select the top-K tools from a registry of 30+ MCP / AWS / internal-API tools for a given natural-language query, replacing MCP's tools/list dump with a RAG-style filter that reduces prompt tokens 50-90%. | `python skills/tool-orchestration/rag-mcp-tool-selection/cli.py --help` |
| `skill-quality-evaluator` | Score a skill against SkillNet's five quality dimensions (safety, completeness, executability, maintainability, cost_awareness), compute a safety/executability-weighted composite, and gate skill retrieval so an agent pul | `python skills/tool-orchestration/skill-quality-evaluator/cli.py --help` |
| `tool-primitive-selector` | Choose how to expose an agent capability — | `python skills/tool-orchestration/tool-primitive-selector/cli.py --help` |

## Run it

```bash
# every skill self-documents
python skills/tool-orchestration/draft-tool-trust-verifier/cli.py --help

# the chapter walkthrough against moto-mocked AWS
jupyter notebook notebooks/ch6-tool-orchestration.ipynb
```
