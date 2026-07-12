# Chapter 2 — Architecture Foundations

- **Skills folder:** `skills/architecture/` (3 skills)
- **Notebook:** `notebooks/ch2-architecture-foundations.ipynb`
- **Prev:** [Chapter 1](./01-defining-agentic-ai.md) &nbsp;|&nbsp; **Next:** [Chapter 3](./03-knowledge-representation.md)

## Role in the architecture

The foundation every later chapter extends: the **dual graph** (vertical knowledge graph = what is true; horizontal workflow graph = what the agent does) and the **harness** (nodes split by tool surface, each with a constrained context scope). This chapter's notebook is also the repo's map (see its Section 0).

## In the running DevOps investigation

The on-call request is routed across the two graphs, the investigation is split into constrained harness nodes by tool surface, and the agent's initial state is mapped across the eight pillars of readiness.

## Skills

| Skill | What it does | CLI |
|-------|--------------|-----|
| `dual-graph-router` | Route an incoming request to the VERTICAL knowledge graph (what the agent knows — a single relationship/temporal traversal), the HORIZONTAL workflow graph (how the agent acts — a decomposed multi-step process), BOTH (a workflow whose nodes query the knowledge graph and write results back), or UNROUTABLE (neither fits — ask for clarification). | `python skills/architecture/dual-graph-router/cli.py --help` |
| `eight-pillar-readiness-map` | Map an agentic-graph system's current capabilities across the eight pillars of Agentic GraphRAG Ch2 (knowledge representation, memory, reasoning, planning, tool orchestration, structured output, self-evolution, optimization), respect the chapter's layering (each pillar depends on the ones before it), flag dependency violations (a higher pillar claimed present while a lower one it requires is missing), report which of the five Chapter-1 flaws remain unsolved (per Table 2-1), and recommend the next pillar to build. | `python skills/architecture/eight-pillar-readiness-map/cli.py --help` |
| `harness-node-splitter` | Split a workflow description into constrained harness nodes using the chapter's rule "nodes differ by tool surface, not by prompt." Given candidate operations each with a declared tool set, merge the ones whose tool surfaces overlap >= 80% (prompt variations of one role) and split the ones with distinct tool surfaces (different roles), then emit the per-node constrained context scope the harness enforces (tool surface + memory reads/writes + input/output contract). | `python skills/architecture/harness-node-splitter/cli.py --help` |

## Run it

```bash
# every skill self-documents
python skills/architecture/dual-graph-router/cli.py --help

# the chapter walkthrough against moto-mocked AWS
jupyter notebook notebooks/ch2-architecture-foundations.ipynb
```
