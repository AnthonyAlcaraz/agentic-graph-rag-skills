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
| `dual-graph-router` | Route an incoming request to the VERTICAL knowledge graph (what the agent knows — | `python skills/architecture/dual-graph-router/cli.py --help` |
| `eight-pillar-readiness-map` | Map an agentic-graph system's current capabilities across the eight pillars of Agentic Graph RAG Ch2 (knowledge representation, memory, reasoning, planning, tool orchestration, structured output, self-evolution, optimiza | `python skills/architecture/eight-pillar-readiness-map/cli.py --help` |
| `harness-node-splitter` | Split a workflow description into constrained harness nodes using the chapter's rule "nodes differ by tool surface, not by prompt." Given candidate operations each with a declared tool set, merge the ones whose tool surf | `python skills/architecture/harness-node-splitter/cli.py --help` |

## Run it

```bash
# every skill self-documents
python skills/architecture/dual-graph-router/cli.py --help

# the chapter walkthrough against moto-mocked AWS
jupyter notebook notebooks/ch2-architecture-foundations.ipynb
```
